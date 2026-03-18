"""
Music Pipeline — Flask Web App
Run: python app.py
Open: http://localhost:5000
"""

import os
import sys
import csv
import json
import uuid
import time
import queue
import shutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    send_file, Response, stream_with_context
)
import pandas as pd

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Global job store: job_id → {status, songs, output_dir, log_queue, ...}
jobs = {}


# ─────────────────────────── ROUTES ───────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload CSV/Excel and parse song list."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ('.csv', '.xlsx', '.xls'):
        return jsonify({'error': f'Unsupported format: {ext}. Use .csv or .xlsx'}), 400

    save_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
    file.save(save_path)

    try:
        if ext == '.csv':
            df = pd.read_csv(save_path)
        else:
            df = pd.read_excel(save_path)

        cols_lower = {c.lower(): c for c in df.columns}

        track_candidates  = ['track name','track','song','title','song name','name']
        artist_candidates = ['artist name','artist','artists','performer','band']

        track_col  = next((cols_lower[c] for c in track_candidates  if c in cols_lower), None)
        artist_col = next((cols_lower[c] for c in artist_candidates if c in cols_lower), None)

        if not track_col or not artist_col:
            return jsonify({
                'error': 'Could not detect columns',
                'columns': list(df.columns)
            }), 422

        songs = []
        skipped = 0
        for _, row in df.iterrows():
            t = str(row[track_col]).strip() if pd.notna(row[track_col]) else ''
            a = str(row[artist_col]).strip() if pd.notna(row[artist_col]) else ''
            if not t or not a or t == 'nan' or a == 'nan':
                skipped += 1
                continue
            t = t.split(' (feat.')[0].split(' [feat.')[0].strip()
            songs.append(f"{t} – {a}")

        os.remove(save_path)
        return jsonify({
            'songs': songs,
            'total': len(songs),
            'skipped': skipped,
            'track_col': track_col,
            'artist_col': artist_col
        })

    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({'error': str(e)}), 500


@app.route('/api/check-tool', methods=['POST'])
def check_tool():
    """Check if a CLI tool is installed."""
    data = request.get_json()
    tool = data.get('tool', 'spotdl')

    def run_check(cmd):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                ver = (result.stdout or result.stderr).strip().split('\n')[0]
                return True, ver
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return False, None

    if tool == 'ffmpeg':
        ok, ver = run_check(['ffmpeg', '-version'])
        return jsonify({'installed': ok, 'version': ver})

    # Try as Python module first (works on Anaconda), then as CLI
    module_map = {'spotdl': 'spotdl', 'yt-dlp': 'yt_dlp', 'deemix': 'deemix'}
    mod = module_map.get(tool)

    if mod:
        ok, ver = run_check([sys.executable, '-m', mod, '--version'])
        if ok:
            return jsonify({'installed': True, 'version': ver})

    # Fallback: direct CLI
    ok, ver = run_check([tool, '--version'])
    return jsonify({'installed': ok, 'version': ver})


@app.route('/api/install-tool', methods=['POST'])
def install_tool():
    """Install a tool via pip (streams output)."""
    data = request.get_json()
    tool = data.get('tool', 'spotdl')

    pip_packages = {
        'spotdl': 'spotdl',
        'yt-dlp': 'yt-dlp',
        'deemix': 'deemix',
    }

    if tool not in pip_packages:
        return jsonify({'error': 'Unknown tool'}), 400

    def generate():
        cmd = [sys.executable, '-m', 'pip', 'install', pip_packages[tool], '--upgrade']
        yield f"data: $ {' '.join(cmd)}\n\n"

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            yield f"data: {line.rstrip()}\n\n"
        proc.wait()

        if proc.returncode == 0:
            yield f"data: ✅ {tool} installed successfully!\n\n"
            yield "data: __DONE__\n\n"
        else:
            yield f"data: ❌ Installation failed (exit {proc.returncode})\n\n"
            yield "data: __ERROR__\n\n"

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream')


@app.route('/api/start-download', methods=['POST'])
def start_download():
    """Start a background download job."""
    data = request.get_json()
    songs  = data.get('songs', [])
    tool   = data.get('tool', 'spotdl')
    bitrate = data.get('bitrate', '320k')
    fmt    = data.get('format', 'mp3')

    if not songs:
        return jsonify({'error': 'No songs provided'}), 400

    job_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(app.config['DOWNLOAD_FOLDER'], f"music_{timestamp}")
    os.makedirs(out_dir, exist_ok=True)

    # Write songs.txt
    songs_file = os.path.join(out_dir, 'songs.txt')
    with open(songs_file, 'w', encoding='utf-8') as f:
        for s in songs:
            f.write(s + '\n')

    log_q = queue.Queue()
    jobs[job_id] = {
        'status':    'running',
        'songs':     songs,
        'done':      [],
        'failed':    [],
        'out_dir':   out_dir,
        'songs_file': songs_file,
        'tool':      tool,
        'bitrate':   bitrate,
        'format':    fmt,
        'log_queue': log_q,
        'started':   time.time(),
    }

    thread = threading.Thread(
        target=run_download_job,
        args=(job_id,),
        daemon=True
    )
    thread.start()

    return jsonify({'job_id': job_id, 'out_dir': out_dir})


@app.route('/api/stream/<job_id>')
def stream_job(job_id):
    """SSE endpoint: stream log lines for a job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    def generate():
        job = jobs[job_id]
        q   = job['log_queue']

        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get('type') == 'done':
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/job/<job_id>')
def job_status(job_id):
    """Get job status summary."""
    if job_id not in jobs:
        return jsonify({'error': 'Not found'}), 404
    job = jobs[job_id]
    return jsonify({
        'status':  job['status'],
        'total':   len(job['songs']),
        'done':    len(job['done']),
        'failed':  len(job['failed']),
        'out_dir': job['out_dir'],
    })


@app.route('/api/download-zip/<job_id>')
def download_zip(job_id):
    """Zip the output folder and send it."""
    # Try in-memory job store first
    out_dir = None
    if job_id in jobs:
        out_dir = jobs[job_id]['out_dir']

    # Fallback: find latest folder in downloads/
    if not out_dir or not os.path.exists(out_dir):
        dl_base = app.config['DOWNLOAD_FOLDER']
        folders = [
            os.path.join(dl_base, f) for f in os.listdir(dl_base)
            if os.path.isdir(os.path.join(dl_base, f))
        ]
        if folders:
            out_dir = max(folders, key=os.path.getmtime)

    if not out_dir or not os.path.exists(out_dir):
        return jsonify({'error': 'Output folder not found. Check downloads/ manually.'}), 404

    zip_path = out_dir + '_songs'
    shutil.make_archive(zip_path, 'zip', out_dir)

    return send_file(
        zip_path + '.zip',
        as_attachment=True,
        download_name=f"music_{job_id}.zip"
    )


@app.route('/api/download-txt/<job_id>')
def download_failed_txt(job_id):
    """Download failed_songs.txt for retry."""
    if job_id not in jobs:
        return jsonify({'error': 'Not found'}), 404
    job = jobs[job_id]
    failed = job.get('failed', [])
    content = '\n'.join(failed)
    from io import BytesIO
    buf = BytesIO(content.encode('utf-8'))
    return send_file(buf, as_attachment=True,
                     download_name='failed_songs.txt',
                     mimetype='text/plain')


# ─────────────────────── DOWNLOAD ENGINE ───────────────────────

# Tuning constants
YTDLP_WORKERS    = 4    # parallel yt-dlp threads
YTDLP_TIMEOUT    = 45   # seconds per song before skip
SPOTDL_THREADS   = 6    # spotdl parallel threads
SPOTDL_TIMEOUT   = 300  # total spotdl batch timeout (seconds per ~20 songs)


def run_download_job(job_id):
    job = jobs[job_id]
    q   = job['log_queue']
    songs      = job['songs']
    tool       = job['tool']
    bitrate    = job['bitrate']
    fmt        = job['format']
    out_dir    = job['out_dir']
    songs_file = job['songs_file']

    def log(msg_type, text, song=None, idx=None):
        q.put({'type': msg_type, 'text': text, 'song': song, 'idx': idx,
               'done': len(job['done']), 'failed': len(job['failed']),
               'total': len(songs)})

    log('info', f"🚀 Starting {tool} — {len(songs)} songs")
    log('info', f"   Quality: {bitrate} | Format: {fmt}")
    log('info', f"   Output:  {out_dir}")
    if tool == 'yt-dlp':
        log('info', f"   Workers: {YTDLP_WORKERS} parallel | Timeout: {YTDLP_TIMEOUT}s/song")
    elif tool == 'spotdl':
        log('info', f"   Threads: {SPOTDL_THREADS} parallel")
    log('info', "")

    try:
        if tool == 'spotdl':
            _run_spotdl(job, log)
        elif tool == 'yt-dlp':
            _run_ytdlp_parallel(job, log)
        elif tool == 'deemix':
            _run_deemix(job, log)
    except Exception as e:
        log('error', f"❌ Fatal error: {e}")

    # Write failed list
    if job['failed']:
        failed_path = os.path.join(out_dir, 'failed_songs.txt')
        with open(failed_path, 'w', encoding='utf-8') as f:
            for s in job['failed']:
                f.write(s + '\n')

    elapsed = round(time.time() - job['started'], 1)
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    log('info', "")
    log('info', f"✅ Done in {mins}m {secs}s — {len(job['done'])} downloaded, {len(job['failed'])} failed")
    job['status'] = 'done'
    log('done', '__DONE__')


def _run_spotdl(job, log):
    """
    SpotDL bulk download — fastest method.
    Uses multiple threads, processes all songs in one command.
    Estimated speed: ~15-20 songs/minute with 6 threads.
    """
    songs_file = job['songs_file']
    out_dir    = job['out_dir']
    bitrate    = job['bitrate']
    fmt        = job['format']
    songs      = job['songs']
    total      = len(songs)

    cmd = [
        sys.executable, '-m', 'spotdl', 'download',
        songs_file,
        '--bitrate',      bitrate,
        '--format',       fmt,
        '--output',       out_dir,
        '--threads',      str(SPOTDL_THREADS),
        '--log-level',    'INFO',
    ]

    log('cmd', '$ ' + ' '.join(cmd))
    log('info', f"⚡ SpotDL processing {total} songs with {SPOTDL_THREADS} threads...")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1
    )

    done_count = 0
    fail_count = 0

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue

        # Detect downloaded songs
        if any(kw in line for kw in ('Downloaded', 'Saved', '✓', 'complete')):
            done_count += 1
            job['done'].append(line)
            log('ok', f"✅ [{done_count}/{total}] {line}", idx=done_count - 1)

        # Detect skipped/failed
        elif any(kw in line for kw in ('Skipping', 'Failed', 'Error', 'Could not')):
            fail_count += 1
            job['failed'].append(line)
            log('error', f"❌ {line}")

        # Rate limit hit — warn user
        elif 'rate' in line.lower() and 'limit' in line.lower():
            log('error', f"⚠️  Rate limit hit! Pausing 30s... ({line})")
            time.sleep(30)

        # Progress info
        elif any(kw in line for kw in ('Downloading', 'Converting', 'Processing')):
            log('info', f"   {line}")

        else:
            log('out', line)

    proc.wait()

    # Count actual files downloaded as ground truth
    actual = len([f for f in os.listdir(out_dir)
                  if f.endswith(('.mp3', '.m4a', '.flac', '.opus', '.webm'))])
    if actual > done_count:
        job['done'] = list(range(actual))  # pad count
        log('ok', f"   ✅ Verified: {actual} files in output folder")


def _run_ytdlp_parallel(job, log):
    """
    yt-dlp parallel download using ThreadPoolExecutor.
    Downloads YTDLP_WORKERS songs simultaneously.
    Each song has a hard YTDLP_TIMEOUT second timeout — auto-skips if stuck.
    Estimated speed: ~8-12 songs/minute with 4 workers.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout

    songs   = job['songs']
    out_dir = job['out_dir']
    bitrate = job['bitrate']
    fmt     = job['format']
    quality = bitrate.replace('k', '')
    total   = len(songs)

    # Thread-safe counter lock
    lock = threading.Lock()

    def download_one(args):
        idx, song = args
        query    = f"ytsearch1:{song}"    # standard YouTube search, works on all yt-dlp versions
        out_tmpl = os.path.join(out_dir, '%(title)s.%(ext)s')

        cmd = [
            sys.executable, '-m', 'yt_dlp',
            '--extract-audio',
            '--audio-format',     fmt,
            '--audio-quality',    quality,
            '--output',           out_tmpl,
            '--embed-thumbnail',
            '--add-metadata',
            '--no-playlist',
            '--quiet',
            '--no-warnings',
            '--socket-timeout',   '15',       # network timeout per request
            '--retries',          '2',        # retry twice on network error
            '--fragment-retries', '2',
            query
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=YTDLP_TIMEOUT      # hard kill if stuck
            )
            success = result.returncode == 0
            err = result.stderr.strip()[:120] if result.stderr else ''
            return idx, song, success, err
        except subprocess.TimeoutExpired:
            return idx, song, False, f'Timed out after {YTDLP_TIMEOUT}s — skipped'
        except Exception as e:
            return idx, song, False, str(e)[:100]

    log('info', f"⚡ Launching {YTDLP_WORKERS} parallel workers...")

    with ThreadPoolExecutor(max_workers=YTDLP_WORKERS) as executor:
        futures = {executor.submit(download_one, (i, s)): (i, s)
                   for i, s in enumerate(songs)}

        completed = 0
        for future in as_completed(futures):
            try:
                idx, song, success, err = future.result(timeout=YTDLP_TIMEOUT + 10)
            except Exception as e:
                orig_idx, orig_song = futures[future]
                idx, song, success, err = orig_idx, orig_song, False, str(e)

            completed += 1

            with lock:
                if success:
                    job['done'].append(song)
                    log('ok',
                        f"✅ [{completed}/{total}] {song}",
                        song=song, idx=idx)
                else:
                    job['failed'].append(song)
                    log('error',
                        f"❌ [{completed}/{total}] {song}" +
                        (f" — {err}" if err else ""),
                        song=song, idx=idx)


def _run_deemix(job, log):
    """Deemix: requires ARL token. Sequential but reliable for FLAC."""
    songs   = job['songs']
    out_dir = job['out_dir']
    bitrate = job['bitrate']

    quality_map = {'128k': '128', '256k': '256', '320k': '320', 'flac': 'flac'}
    q_flag = quality_map.get(bitrate, '320')

    log('warn', '⚠️  Deemix requires a valid Deezer ARL token in ~/.config/deemix/')
    log('info', '')

    for idx, song in enumerate(songs):
        log('info', f"[{idx+1}/{len(songs)}] {song}", song=song, idx=idx)
        cmd = ['deemix', '-b', q_flag, '-p', out_dir, song]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                job['done'].append(song)
                log('ok', f"  ✅ {song}", song=song, idx=idx)
            else:
                job['failed'].append(song)
                log('error', f"  ❌ {song}", song=song, idx=idx)
        except subprocess.TimeoutExpired:
            job['failed'].append(song)
            log('error', f"  ⏱ Timeout: {song} — skipped", song=song, idx=idx)
        time.sleep(0.3)


# ───────────────────────────── MAIN ─────────────────────────────

if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════╗
║      🎵  Music Pipeline — Local Server       ║
╠══════════════════════════════════════════════╣
║  URL:  http://localhost:5000                 ║
║  Stop: Ctrl + C                              ║
╚══════════════════════════════════════════════╝
""")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)