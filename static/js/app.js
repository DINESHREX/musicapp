/* ─── State ─── */
let songs = [];
let currentJob = null;
let selectedTool = 'spotdl';

const SAMPLE = `Blinding Lights – The Weeknd
Shape of You – Ed Sheeran
Levitating – Dua Lipa
Stay – The Kid LAROI
As It Was – Harry Styles
Heat Waves – Glass Animals
Watermelon Sugar – Harry Styles
Peaches – Justin Bieber
Good 4 U – Olivia Rodrigo
drivers license – Olivia Rodrigo
Montero (Call Me By Your Name) – Lil Nas X
Save Your Tears – The Weeknd
Butter – BTS
Dynamite – BTS
Permission to Dance – BTS
Bad Guy – Billie Eilish
Happier Than Ever – Billie Eilish
Therefore I Am – Billie Eilish
Shivers – Ed Sheeran
Bad Habits – Ed Sheeran`;

/* ─── Navigation ─── */
function goTo(n) {
  document.querySelectorAll('.panel').forEach((p, i) => p.classList.toggle('active', i === n));
  document.querySelectorAll('.step-btn').forEach((b, i) => b.classList.toggle('active', i === n));
  if (n === 1) refreshStats();
  if (n === 2) checkAllTools();
  if (n === 4) populateResults();
}

function markDone(n) {
  const btn = document.getElementById(`sbtn${n}`);
  const num = document.getElementById(`snum${n}`);
  if (btn) { btn.classList.add('done'); }
  if (num) { num.textContent = '✓'; }
}

/* ─── Toast ─── */
function toast(msg, dur = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), dur);
}

/* ─── Tab switch ─── */
function switchTab(type) {
  ['file', 'paste', 'sample'].forEach(t => {
    document.getElementById(`input_${t}`).style.display = t === type ? 'block' : 'none';
    document.getElementById(`tab_${t}`).classList.toggle('active', t === type);
  });
}

/* ─── File Upload ─── */
function handleUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  uploadFile(file);
}

// Drag & Drop
document.addEventListener('DOMContentLoaded', () => {
  const zone = document.getElementById('drop_zone');
  if (!zone) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });
});

function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);

  const zone = document.getElementById('drop_zone');
  zone.innerHTML = '<div class="drop-icon">⏳</div><p>Processing...</p>';

  fetch('/api/upload', { method: 'POST', body: form })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        zone.innerHTML = `<div class="drop-icon">❌</div><p>${data.error}</p><span>Try again</span>`;
        return;
      }
      songs = data.songs;
      document.getElementById('songs_editor').value = songs.join('\n');

      const resultEl = document.getElementById('upload_result');
      const msgEl = document.getElementById('upload_ok_msg');
      msgEl.innerHTML = `<span>✓</span><div>Loaded <strong>${data.total}</strong> songs from <strong>${file.name}</strong>. Track col: <code>${data.track_col}</code>, Artist col: <code>${data.artist_col}</code>. Skipped: ${data.skipped}.</div>`;
      resultEl.style.display = 'block';

      zone.innerHTML = `<div class="drop-icon">✅</div><p>${file.name}</p><span>${data.total} songs loaded</span>`;
      markDone(0);
      toast(`✅ ${data.total} songs loaded`);
    })
    .catch(e => {
      zone.innerHTML = `<div class="drop-icon">❌</div><p>Upload failed: ${e.message}</p><span>Try again</span>`;
    });
}

function parsePaste() {
  const raw = document.getElementById('paste_area').value.trim();
  if (!raw) { toast('⚠️ Nothing pasted'); return; }

  songs = raw.split('\n').map(l => {
    l = l.trim();
    if (!l) return null;
    if (l.includes(',') && !l.includes('–')) {
      const parts = l.split(',');
      return `${parts[0].trim()} – ${(parts[1] || '').trim()}`;
    }
    return l;
  }).filter(l => l && l.includes('–'));

  document.getElementById('songs_editor').value = songs.join('\n');
  document.getElementById('upload_result').style.display = 'block';
  document.getElementById('upload_ok_msg').innerHTML = `<span>✓</span><div><strong>${songs.length}</strong> songs parsed from pasted text.</div>`;
  markDone(0);
  toast(`✅ ${songs.length} songs parsed`);
}

function loadSample() {
  songs = SAMPLE.trim().split('\n');
  document.getElementById('songs_editor').value = songs.join('\n');
  document.getElementById('upload_result').style.display = 'block';
  document.getElementById('upload_ok_msg').innerHTML = `<span>✓</span><div>Loaded <strong>${songs.length}</strong> sample songs.</div>`;
  markDone(0);
  toast('✅ Sample data loaded');
  setTimeout(() => goTo(1), 500);
}

/* ─── Review ─── */
function refreshStats() {
  const lines = document.getElementById('songs_editor').value.trim().split('\n').filter(l => l.trim());
  songs = lines;
  const dupes = lines.length - new Set(lines).size;
  document.getElementById('r_total').textContent = lines.length;
  document.getElementById('r_dupes').textContent = dupes;
  document.getElementById('r_ready').textContent = lines.length - dupes;
}

function dedupeList() {
  const lines = [...new Set(document.getElementById('songs_editor').value.trim().split('\n').filter(l => l.trim()))];
  document.getElementById('songs_editor').value = lines.join('\n');
  refreshStats();
  toast('✅ Duplicates removed');
}

function sortList() {
  const lines = document.getElementById('songs_editor').value.trim().split('\n').filter(l => l.trim()).sort();
  document.getElementById('songs_editor').value = lines.join('\n');
  refreshStats();
  toast('✅ List sorted A–Z');
}

function downloadSongsTxt() {
  const content = document.getElementById('songs_editor').value;
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'songs.txt'; a.click();
  URL.revokeObjectURL(url);
}

/* ─── Tool selection ─── */
function selectTool(tool) {
  selectedTool = tool;
  ['spotdl', 'ytdlp', 'deemix'].forEach(t => {
    const id = t === 'ytdlp' ? 'yt-dlp' : t;
    document.getElementById(`tc_${t}`).classList.toggle('selected', id === tool);
  });
}

function checkAllTools() {
  const tools = [
    { key: 'spotdl',  id: 'spotdl' },
    { key: 'yt-dlp',  id: 'ytdlp'  },
    { key: 'deemix',  id: 'deemix' },
    { key: 'ffmpeg',  id: 'ffmpeg' },
  ];

  tools.forEach(({ key, id }) => {
    // Sidebar badges
    const badge = document.getElementById(`badge_${id}`);
    // Dep status board
    const ds = document.getElementById(`ds_${id}`);
    // Tool card status (spotdl/ytdlp/deemix only)
    const ts = document.getElementById(`ts_${id}`);

    if (badge) { badge.textContent = '…'; badge.className = 'badge badge-gray'; }
    if (ds) { ds.textContent = 'Checking…'; ds.className = 'dep-status checking'; }
    if (ts) { ts.textContent = 'Checking…'; ts.className = 'tool-status'; }

    fetch('/api/check-tool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool: key })
    })
    .then(r => r.json())
    .then(data => {
      const installed = data.installed;
      const ver = data.version ? `v${data.version.split('\n')[0].trim()}` : '';

      if (badge) {
        badge.textContent = installed ? '✓ Ready' : '✗ Missing';
        badge.className = installed ? 'badge badge-ok' : 'badge badge-err';
      }
      if (ds) {
        ds.textContent = installed ? (ver || '✓ Installed') : '✗ Not installed';
        ds.className = `dep-status ${installed ? 'ok' : 'missing'}`;
      }
      if (ts) {
        ts.textContent = installed ? `✅ ${ver || 'ready'}` : '❌ Not installed';
        ts.className = `tool-status ${installed ? 'ok' : 'missing'}`;
      }
    })
    .catch(() => {
      if (badge) { badge.textContent = '?'; badge.className = 'badge badge-gray'; }
      if (ds) { ds.textContent = 'Check failed'; ds.className = 'dep-status checking'; }
    });
  });
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    toast('✅ Copied to clipboard!');
    // Flash all copy buttons briefly
    document.querySelectorAll('.cmd-copy').forEach(btn => {
      if (btn.getAttribute('onclick')?.includes(text.substring(0, 10))) {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1800);
      }
    });
  }).catch(() => {
    prompt('Copy this command:', text);
  });
}

/* ─── Download ─── */
function startDownload() {
  songs = document.getElementById('songs_editor').value.trim().split('\n').filter(l => l.trim());
  if (!songs.length) { toast('⚠️ No songs in list'); return; }

  const quality = document.querySelector('input[name="quality"]:checked')?.value || '320k';
  const fmt     = document.querySelector('input[name="format"]:checked')?.value || 'mp3';

  goTo(3);

  const totalEl   = document.getElementById('dl_total');
  const doneEl    = document.getElementById('dl_done');
  const pendEl    = document.getElementById('dl_pending');
  const failEl    = document.getElementById('dl_failed');
  const progFill  = document.getElementById('progress_fill');
  const progPct   = document.getElementById('progress_pct');
  const logEl     = document.getElementById('dl_log');
  const termTitle = document.getElementById('term_title');

  totalEl.textContent = songs.length;
  doneEl.textContent  = 0;
  pendEl.textContent  = songs.length;
  failEl.textContent  = 0;
  logEl.innerHTML = '';
  progFill.style.width = '0%';
  progPct.textContent = '0%';
  termTitle.textContent = `${selectedTool} — downloading ${songs.length} songs`;

  fetch('/api/start-download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ songs, tool: selectedTool, bitrate: quality, format: fmt })
  })
  .then(r => r.json())
  .then(data => {
    if (data.error) { appendLog(logEl, 'err', `❌ ${data.error}`); return; }
    currentJob = data.job_id;

    const es = new EventSource(`/api/stream/${data.job_id}`);
    es.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'ping') return;

      appendLog(logEl, msg.type === 'ok' ? 'ok' : msg.type === 'error' ? 'err' : msg.type === 'cmd' ? 'cmd' : 'out', msg.text);

      doneEl.textContent  = msg.done;
      failEl.textContent  = msg.failed;
      const total = msg.total;
      const prog  = total ? Math.round((msg.done + msg.failed) / total * 100) : 0;
      pendEl.textContent  = total - msg.done - msg.failed;
      progFill.style.width = prog + '%';
      progPct.textContent  = prog + '%';

      if (msg.type === 'done') {
        es.close();
        markDone(3);
        document.getElementById('dl_done_bar').style.display = 'flex';
        toast('✅ Download complete!');
      }
    };
    es.onerror = () => es.close();
  });
}

function appendLog(el, cls, text) {
  if (!text) return;
  const p = document.createElement('p');
  p.className = `line-${cls}`;
  p.textContent = text;
  el.appendChild(p);
  el.parentElement.scrollTop = el.parentElement.scrollHeight;
}

/* ─── Results ─── */
function populateResults() {
  if (!currentJob) return;
  fetch(`/api/job/${currentJob}`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('res_total').textContent  = data.total;
      document.getElementById('res_done').textContent   = data.done;
      document.getElementById('res_failed').textContent = data.failed;
      const rate = data.total ? Math.round(data.done / data.total * 100) : 0;
      document.getElementById('res_rate').textContent   = rate + '%';
      document.getElementById('res_path').textContent   = data.out_dir;

      if (data.failed > 0) {
        document.getElementById('fail_btn').style.display = 'inline-flex';
        document.getElementById('failed_card').style.display = 'block';
      }
    });
}

function downloadZip() {
  if (!currentJob) { toast('No job found'); return; }
  toast('⏳ Preparing ZIP...');
  window.location.href = `/api/download-zip/${currentJob}`;
}

function downloadFailed() {
  if (!currentJob) return;
  window.location.href = `/api/download-txt/${currentJob}`;
}

function resetAll() {
  songs = [];
  currentJob = null;
  document.getElementById('songs_editor').value = '';
  document.getElementById('paste_area').value = '';
  document.getElementById('upload_result').style.display = 'none';
  document.getElementById('drop_zone').innerHTML = '<div class="drop-icon">📂</div><p>Drop your CSV or Excel file here</p><span>or click to browse</span><input type="file" id="file_input" accept=".csv,.xlsx,.xls" onchange="handleUpload(event)" style="display:none">';
  document.querySelectorAll('.step-btn').forEach((b, i) => {
    b.classList.remove('done', 'active');
    const num = document.getElementById(`snum${i}`);
    if (num) num.textContent = i + 1;
  });
  goTo(0);
  toast('↺ Pipeline reset');
}
