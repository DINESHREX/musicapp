"""
MusicDL — Flask Web App
Run: python app.py
Open: http://localhost:5000
"""

import os
import sys
import json
import uuid
import time
import queue
import shutil
import threading
import subprocess
from io import BytesIO
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    send_file, Response, stream_with_context
)
import pandas as pd

app = Flask(__name__)

# ── Vercel detection: use /tmp when running on Vercel ──
IS_VERCEL = os.environ.get('VERCEL') == '1'
if IS_VERCEL:
    app.config['DOWNLOAD_FOLDER'] = '/tmp/downloads'
    app.config['UPLOAD_FOLDER']   = '/tmp/uploads'
else:
    app.config['DOWNLOAD_FOLDER'] = 'downloads'
    app.config['UPLOAD_FOLDER']   = 'uploads'

app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Global job store: job_id → {status, songs, output_dir, log_queue, ...}
jobs = {}


# ─────────────────────────── HELPERS ──────────────────────────

def _ytdlp_version():
    """Return yt-dlp version string or None."""
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'yt_dlp', '--version'],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            return r.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None


def _ffmpeg_version():
    """Return ffmpeg version string or None."""
    try:
        r = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            return r.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None


# ─────────────────────────── ROUTES ───────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── Status ──────────────────────────────────────────────────

@app.route('/api/status')
def api_status():
    """Return yt-dlp and ffmpeg version info."""
    return jsonify({
        'ytdlp':  _ytdlp_version(),
        'ffmpeg': _ffmpeg_version(),
    })


# ── File Upload ──────────────────────────────────────────────

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

        track_candidates  = ['track name', 'track', 'song', 'title', 'song name', 'name']
        artist_candidates = ['artist name', 'artist', 'artists', 'performer', 'band']

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
            t = str(row[track_col]).strip()  if pd.notna(row[track_col])  else ''
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


# ── Tool Check ───────────────────────────────────────────────

@app.route('/api/check-tool', methods=['POST'])
def check_tool():
    """Check if yt-dlp or ffmpeg is installed."""
    data = request.get_json()
    tool = data.get('tool', 'yt-dlp')

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

    # yt-dlp via Python module (works on Anaconda)
    ok, ver = run_check([sys.executable, '-m', 'yt_dlp', '--version'])
    return jsonify({'installed': ok, 'version': ver})


# ── Search ───────────────────────────────────────────────────

@app.route('/api/search', methods=['POST'])
def api_search():
    """Search YouTube for songs via yt-dlp."""
    data = request.get_json() or {}
    query = (data.get('query') or '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400

    try:
        r = subprocess.run(
            [sys.executable, '-m', 'yt_dlp',
             f'ytsearch10:{query}',
             '--dump-json', '--flat-playlist',
             '--no-warnings', '--quiet'],
            capture_output=True, text=True, timeout=20
        )
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Search timed out. Try again.'}), 504

    results = []
    for line in r.stdout.strip().splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        dur = item.get('duration') or 0
        try:
            m, s = divmod(int(float(dur)), 60)
        except (ValueError, TypeError):
            m, s = 0, 0
        vid_id = item.get('id', '')
        results.append({
            'id':        vid_id,
            'title':     item.get('title', 'Unknown'),
            'uploader':  item.get('uploader') or item.get('channel', 'Unknown'),
            'duration':  f'{m}:{s:02d}',
            'thumbnail': f'https://i.ytimg.com/vi/{vid_id}/mqdefault.jpg',
            'url':       f'https://www.youtube.com/watch?v={vid_id}',
        })
    return jsonify({'results': results})


# ── Single Download ──────────────────────────────────────────

@app.route('/api/download-single', methods=['POST'])
def api_download_single():
    """Download a single song and stream the file to the browser."""
    data = request.get_json() or {}
    url     = (data.get('url')     or '').strip()
    query   = (data.get('query')   or '').strip()
    bitrate = (data.get('bitrate') or '320k').strip()
    fmt     = (data.get('format')  or 'mp3').strip()

    if not url and not query:
        return jsonify({'error': 'url or query required'}), 400

    target  = url if url else f'ytsearch1:{query}'
    quality = bitrate.replace('k', '')

    tmp_dir = os.path.join(app.config['DOWNLOAD_FOLDER'], f'single_{uuid.uuid4().hex[:8]}')
    os.makedirs(tmp_dir, exist_ok=True)

    has_ffmpeg = _ffmpeg_version() is not None
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        target,
        '--extract-audio',
        '--audio-quality', quality,
        '--output', os.path.join(tmp_dir, '%(title)s.%(ext)s'),
        '--embed-thumbnail',
        '--add-metadata',
        '--no-playlist',
        '--socket-timeout', '20',
        '--retries', '3',
        '--quiet',
    ]
    if has_ffmpeg:
        cmd += ['--audio-format', fmt]
    else:
        cmd += ['--audio-format', 'best']

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return jsonify({'error': 'Download timed out'}), 504

    if result.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        err = (result.stderr or '').strip()[:300]
        return jsonify({'error': f'yt-dlp failed: {err}'}), 500

    # Find downloaded file
    files = list(Path(tmp_dir).glob(f'*.{fmt}'))
    if not files:
        files = list(Path(tmp_dir).glob('*.*'))
    if not files:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return jsonify({'error': 'Download succeeded but no file found'}), 500

    filepath = files[0]
    dl_name  = filepath.name

    # Schedule cleanup after send
    def _cleanup():
        time.sleep(10)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    threading.Thread(target=_cleanup, daemon=True).start()

    return send_file(
        str(filepath),
        as_attachment=True,
        download_name=dl_name
    )


# ── Bulk Download — Start ────────────────────────────────────

@app.route('/api/start-download', methods=['POST'])
def start_download():
    """Start a background bulk download job."""
    data    = request.get_json()
    songs   = data.get('songs', [])
    bitrate = data.get('bitrate', '320k')
    fmt     = data.get('format', 'mp3')

    if not songs:
        return jsonify({'error': 'No songs provided'}), 400

    job_id    = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir   = os.path.join(app.config['DOWNLOAD_FOLDER'], f'music_{timestamp}')
    os.makedirs(out_dir, exist_ok=True)

    songs_file = os.path.join(out_dir, 'songs.txt')
    with open(songs_file, 'w', encoding='utf-8') as f:
        for s in songs:
            f.write(s + '\n')

    log_q = queue.Queue()
    jobs[job_id] = {
        'status':     'running',
        'songs':      songs,
        'done':       [],
        'failed':     [],
        'out_dir':    out_dir,
        'songs_file': songs_file,
        'bitrate':    bitrate,
        'format':     fmt,
        'log_queue':  log_q,
        'started':    time.time(),
    }

    threading.Thread(
        target=run_download_job,
        args=(job_id,),
        daemon=True
    ).start()

    return jsonify({'job_id': job_id, 'out_dir': out_dir})


# ── Bulk Download — Stream SSE ───────────────────────────────

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
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ── Bulk Download — Job Status ───────────────────────────────

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


# ── Download ZIP ─────────────────────────────────────────────

@app.route('/api/download-zip/<job_id>')
def download_zip(job_id):
    """Zip the output folder and send it. Works even after server restart."""
    out_dir = None
    if job_id in jobs:
        out_dir = jobs[job_id]['out_dir']

    # Fallback: find most recently modified folder in downloads/
    if not out_dir or not os.path.exists(out_dir):
        base = app.config['DOWNLOAD_FOLDER']
        folders = [
            os.path.join(base, f) for f in os.listdir(base)
            if os.path.isdir(os.path.join(base, f))
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
        download_name=f'music_{job_id}.zip'
    )


# ── Download Failed TXT ──────────────────────────────────────

@app.route('/api/download-txt/<job_id>')
def download_failed_txt(job_id):
    """Download failed_songs.txt for retry."""
    if job_id not in jobs:
        return jsonify({'error': 'Not found'}), 404
    job     = jobs[job_id]
    content = '\n'.join(job.get('failed', []))
    buf     = BytesIO(content.encode('utf-8'))
    return send_file(buf, as_attachment=True,
                     download_name='failed_songs.txt',
                     mimetype='text/plain')


# ─────────────────────── DOWNLOAD ENGINE ────────────────────

YTDLP_WORKERS = 4   # parallel workers
YTDLP_TIMEOUT = 45  # seconds per song


def run_download_job(job_id):
    job     = jobs[job_id]
    q       = job['log_queue']
    songs   = job['songs']
    bitrate = job['bitrate']
    fmt     = job['format']
    out_dir = job['out_dir']

    def log(msg_type, text, song=None, idx=None):
        q.put({'type': msg_type, 'text': text, 'song': song, 'idx': idx,
               'done': len(job['done']), 'failed': len(job['failed']),
               'total': len(songs)})

    log('info', f'🚀 Starting yt-dlp — {len(songs)} songs')
    log('info', f'   Quality: {bitrate} | Format: {fmt}')
    log('info', f'   Output:  {out_dir}')
    log('info', f'   Workers: {YTDLP_WORKERS} parallel | Timeout: {YTDLP_TIMEOUT}s/song')
    log('info', '')

    try:
        _run_ytdlp_parallel(job, log)
    except Exception as e:
        log('error', f'❌ Fatal error: {e}')

    # Write failed list
    if job['failed']:
        failed_path = os.path.join(out_dir, 'failed_songs.txt')
        with open(failed_path, 'w', encoding='utf-8') as f:
            for s in job['failed']:
                f.write(s + '\n')

    elapsed = round(time.time() - job['started'], 1)
    mins    = int(elapsed // 60)
    secs    = int(elapsed % 60)
    log('info', '')
    log('info', f'✅ Done in {mins}m {secs}s — {len(job["done"])} downloaded, {len(job["failed"])} failed')
    job['status'] = 'done'
    log('done', '__DONE__')


def _run_ytdlp_parallel(job, log):
    """
    yt-dlp parallel download using ThreadPoolExecutor.
    Downloads YTDLP_WORKERS songs simultaneously.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    songs   = job['songs']
    out_dir = job['out_dir']
    bitrate = job['bitrate']
    fmt     = job['format']
    quality = bitrate.replace('k', '')
    total   = len(songs)
    lock    = threading.Lock()

    has_ffmpeg = _ffmpeg_version() is not None

    def download_one(args):
        idx, song = args
        query    = f'ytsearch1:{song}'
        out_tmpl = os.path.join(out_dir, '%(title)s.%(ext)s')

        cmd = [
            sys.executable, '-m', 'yt_dlp',
            '--extract-audio',
            '--audio-quality',    quality,
            '--output',           out_tmpl,
            '--embed-thumbnail',
            '--add-metadata',
            '--no-playlist',
            '--quiet',
            '--no-warnings',
            '--socket-timeout',   '15',
            '--retries',          '2',
            '--fragment-retries', '2',
        ]
        if has_ffmpeg:
            cmd += ['--audio-format', fmt]
        else:
            cmd += ['--audio-format', 'best']
        cmd.append(query)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=YTDLP_TIMEOUT
            )
            success = result.returncode == 0
            err = result.stderr.strip()[:120] if result.stderr else ''
            return idx, song, success, err
        except subprocess.TimeoutExpired:
            return idx, song, False, f'Timed out after {YTDLP_TIMEOUT}s — skipped'
        except Exception as e:
            return idx, song, False, str(e)[:100]

    log('info', f'⚡ Launching {YTDLP_WORKERS} parallel workers...')
    if not has_ffmpeg:
        log('info', '⚠️  FFmpeg not found — downloading as best available (webm/opus)')

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
                    log('ok', f'✅ [{completed}/{total}] {song}', song=song, idx=idx)
                else:
                    job['failed'].append(song)
                    log('error',
                        f'❌ [{completed}/{total}] {song}' + (f' — {err}' if err else ''),
                        song=song, idx=idx)


# ───────────────────────────── MAIN ─────────────────────────

if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════════╗
║       🎵  MusicDL — Local Server             ║
╠══════════════════════════════════════════════╣
║  URL:  http://localhost:5000                 ║
║  Stop: Ctrl + C                              ║
╚══════════════════════════════════════════════╝
""")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)