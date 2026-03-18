/* ═══════════════════════════════════════════
   MusicDL — app.js
   Tabs: Search | Single | Bulk CSV
═══════════════════════════════════════════ */

/* ── State ── */
let songs = [];
let currentJob = null;

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

/* ════════════════════════════════════════════════
   INIT
════════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  // Fetch tool status for header dots
  fetchStatus();

  // Drag & Drop on the bulk upload zone
  const zone = document.getElementById("drop_zone");
  if (zone) {
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () =>
      zone.classList.remove("drag-over"),
    );
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    });
  }
});

/* ════════════════════════════════════════════════
   HEADER STATUS
════════════════════════════════════════════════ */
function fetchStatus() {
  fetch("/api/status")
    .then((r) => r.json())
    .then((data) => {
      const dotY = document.getElementById("dot-ytdlp");
      const dotF = document.getElementById("dot-ffmpeg");
      if (dotY)
        dotY.className = "status-dot " + (data.ytdlp ? "ok" : "missing");
      if (dotF)
        dotF.className = "status-dot " + (data.ffmpeg ? "ok" : "missing");
    })
    .catch(() => {});
}

/* ════════════════════════════════════════════════
   MAIN TAB SWITCHING  (Search | Single | Bulk)
════════════════════════════════════════════════ */
function switchMainTab(tab) {
  ["search", "single", "bulk"].forEach((t) => {
    const content = document.getElementById(`tab-${t}`);
    const btn = document.getElementById(`mtab-${t}`);
    if (content) content.classList.toggle("active", t === tab);
    if (btn) btn.classList.toggle("active", t === tab);
  });
  if (tab === "bulk") checkAllTools();
}

/* ════════════════════════════════════════════════
   TOAST
════════════════════════════════════════════════ */
function toast(msg, dur = 2500) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), dur);
}

/* ════════════════════════════════════════════════
   SEARCH TAB
════════════════════════════════════════════════ */
async function doSearch() {
  const query = (document.getElementById("search-input").value || "").trim();
  if (!query) {
    toast("⚠️ Enter a search query");
    return;
  }

  const btn = document.getElementById("search-btn");
  const status = document.getElementById("search-status");
  const results = document.getElementById("search-results");

  btn.disabled = true;
  btn.textContent = "⏳";
  status.style.display = "block";
  status.textContent = "Searching YouTube…";
  results.innerHTML = "";

  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await resp.json();

    if (data.error) {
      status.textContent = "❌ " + data.error;
    } else if (!data.results || data.results.length === 0) {
      status.textContent = "🔍 No results found. Try a different query.";
    } else {
      status.style.display = "none";
      renderSearchResults(data.results);
    }
  } catch (e) {
    status.textContent = "❌ Search failed: " + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Search";
  }
}

function renderSearchResults(results) {
  const container = document.getElementById("search-results");
  container.innerHTML = results
    .map(
      (r, i) => `
    <div class="result-card">
      <img class="result-thumb" src="${r.thumbnail}" alt="" loading="lazy"
           onerror="this.style.background='#1c2030';this.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'">
      <div class="result-info">
        <p class="result-title" title="${esc(r.title)}">${esc(r.title)}</p>
        <p class="result-meta">${esc(r.uploader)} · ${esc(r.duration)}</p>
      </div>
      <button class="dl-btn" id="dlbtn-${i}"
              onclick="downloadFromSearch('${esc(r.url)}', '${esc(r.title)}', ${i})"
              title="Download">⬇</button>
    </div>
  `,
    )
    .join("");
}

async function downloadFromSearch(url, title, idx) {
  const btn = document.getElementById(`dlbtn-${idx}`);
  if (!btn || btn.disabled) return;

  btn.disabled = true;
  btn.innerHTML =
    '<span style="display:inline-block;animation:spin 1s linear infinite">⟳</span>';

  try {
    const resp = await fetch("/api/download-single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, bitrate: "320k", format: "mp3" }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: "Unknown error" }));
      toast("❌ " + (err.error || "Download failed"));
      btn.disabled = false;
      btn.innerHTML = "⬇";
      return;
    }

    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    // Try to get filename from Content-Disposition header
    const cd = resp.headers.get("Content-Disposition") || "";
    const fnMatch = cd.match(/filename\*?=['"]?([^'";\n]+)/i);
    a.download = fnMatch ? decodeURIComponent(fnMatch[1]) : title + ".mp3";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);

    btn.classList.add("done");
    btn.innerHTML = "✅";
    setTimeout(() => {
      btn.innerHTML = "⬇";
      btn.classList.remove("done");
      btn.disabled = false;
    }, 4000);
    toast("✅ Download started!");
  } catch (e) {
    toast("❌ " + e.message);
    btn.disabled = false;
    btn.innerHTML = "⬇";
  }
}

/* ════════════════════════════════════════════════
   SINGLE DOWNLOAD TAB
════════════════════════════════════════════════ */
async function downloadSingle() {
  const query = (document.getElementById("single-input").value || "").trim();
  const bitrate =
    document.querySelector('input[name="bitrate"]:checked')?.value || "320k";
  const fmt =
    document.querySelector('input[name="sformat"]:checked')?.value || "mp3";

  if (!query) {
    toast("⚠️ Enter a song name or URL");
    return;
  }

  const btn = document.getElementById("single-dl-btn");
  const status = document.getElementById("single-status");

  btn.disabled = true;
  btn.textContent = "Downloading…";
  status.style.display = "block";
  status.innerHTML =
    "⏳ Searching and downloading… this may take 30–60 seconds.";

  const body = query.startsWith("http")
    ? { url: query, bitrate, format: fmt }
    : { query, bitrate, format: fmt };

  try {
    const resp = await fetch("/api/download-single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: "Unknown error" }));
      status.innerHTML = "❌ " + (err.error || "Download failed");
      toast("❌ Download failed");
      return;
    }

    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const cd = resp.headers.get("Content-Disposition") || "";
    const fnMatch = cd.match(/filename\*?=['"]?([^'";\n]+)/i);
    a.download = fnMatch ? decodeURIComponent(fnMatch[1]) : query + "." + fmt;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);

    status.innerHTML = "✅ Download complete!";
    toast("✅ File downloaded!");
  } catch (e) {
    status.innerHTML = "❌ Error: " + e.message;
    toast("❌ " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "⬇ Download";
  }
}

/* ════════════════════════════════════════════════
   BULK — NAVIGATION
════════════════════════════════════════════════ */
function goTo(n) {
  document
    .querySelectorAll(".panel")
    .forEach((p, i) => p.classList.toggle("active", i === n));
  document
    .querySelectorAll(".step-btn")
    .forEach((b, i) => b.classList.toggle("active", i === n));
  if (n === 1) refreshStats();
  if (n === 2) checkAllTools();
  if (n === 4) populateResults();
}

function markDone(n) {
  const btn = document.getElementById(`sbtn${n}`);
  const num = document.getElementById(`snum${n}`);
  if (btn) btn.classList.add("done");
  if (num) num.textContent = "✓";
}

/* ════════════════════════════════════════════════
   BULK — INPUT TABS
════════════════════════════════════════════════ */
function switchTab(type) {
  ["file", "paste", "sample"].forEach((t) => {
    document.getElementById(`input_${t}`).style.display =
      t === type ? "block" : "none";
    document.getElementById(`tab_${t}`).classList.toggle("active", t === type);
  });
}

/* ════════════════════════════════════════════════
   BULK — FILE UPLOAD
════════════════════════════════════════════════ */
function handleUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  uploadFile(file);
}

function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);

  const zone = document.getElementById("drop_zone");
  zone.innerHTML = '<div class="drop-icon">⏳</div><p>Processing…</p>';

  fetch("/api/upload", { method: "POST", body: form })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        zone.innerHTML = `<div class="drop-icon">❌</div><p>${data.error}</p><span>Try again</span>`;
        return;
      }
      songs = data.songs;
      document.getElementById("songs_editor").value = songs.join("\n");

      document.getElementById("upload_ok_msg").innerHTML =
        `<span>✓</span><div>Loaded <strong>${data.total}</strong> songs from <strong>${file.name}</strong>. Track col: <code>${data.track_col}</code>. Skipped: ${data.skipped}.</div>`;
      document.getElementById("upload_result").style.display = "block";
      zone.innerHTML = `<div class="drop-icon">✅</div><p>${file.name}</p><span>${data.total} songs loaded</span>`;
      markDone(0);
      toast(`✅ ${data.total} songs loaded`);
    })
    .catch((e) => {
      zone.innerHTML = `<div class="drop-icon">❌</div><p>Upload failed: ${e.message}</p><span>Try again</span>`;
    });
}

function parsePaste() {
  const raw = document.getElementById("paste_area").value.trim();
  if (!raw) {
    toast("⚠️ Nothing pasted");
    return;
  }

  songs = raw
    .split("\n")
    .map((l) => {
      l = l.trim();
      if (!l) return null;
      if (l.includes(",") && !l.includes("–")) {
        const parts = l.split(",");
        return `${parts[0].trim()} – ${(parts[1] || "").trim()}`;
      }
      return l;
    })
    .filter((l) => l && l.includes("–"));

  document.getElementById("songs_editor").value = songs.join("\n");
  document.getElementById("upload_result").style.display = "block";
  document.getElementById("upload_ok_msg").innerHTML =
    `<span>✓</span><div><strong>${songs.length}</strong> songs parsed from pasted text.</div>`;
  markDone(0);
  toast(`✅ ${songs.length} songs parsed`);
}

function loadSample() {
  songs = SAMPLE.trim().split("\n");
  document.getElementById("songs_editor").value = songs.join("\n");
  document.getElementById("upload_result").style.display = "block";
  document.getElementById("upload_ok_msg").innerHTML =
    `<span>✓</span><div>Loaded <strong>${songs.length}</strong> sample songs.</div>`;
  markDone(0);
  toast("✅ Sample data loaded");
  setTimeout(() => goTo(1), 500);
}

/* ════════════════════════════════════════════════
   BULK — REVIEW
════════════════════════════════════════════════ */
function refreshStats() {
  const lines = document
    .getElementById("songs_editor")
    .value.trim()
    .split("\n")
    .filter((l) => l.trim());
  songs = lines;
  const dupes = lines.length - new Set(lines).size;
  document.getElementById("r_total").textContent = lines.length;
  document.getElementById("r_dupes").textContent = dupes;
  document.getElementById("r_ready").textContent = lines.length - dupes;
}

function dedupeList() {
  const lines = [
    ...new Set(
      document
        .getElementById("songs_editor")
        .value.trim()
        .split("\n")
        .filter((l) => l.trim()),
    ),
  ];
  document.getElementById("songs_editor").value = lines.join("\n");
  refreshStats();
  toast("✅ Duplicates removed");
}

function sortList() {
  const lines = document
    .getElementById("songs_editor")
    .value.trim()
    .split("\n")
    .filter((l) => l.trim())
    .sort();
  document.getElementById("songs_editor").value = lines.join("\n");
  refreshStats();
  toast("✅ List sorted A–Z");
}

function downloadSongsTxt() {
  const content = document.getElementById("songs_editor").value;
  const blob = new Blob([content], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "songs.txt";
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ════════════════════════════════════════════════
   BULK — TOOL CHECK
════════════════════════════════════════════════ */
function checkAllTools() {
  const tools = [
    { key: "yt-dlp", id: "ytdlp" },
    { key: "ffmpeg", id: "ffmpeg" },
  ];

  tools.forEach(({ key, id }) => {
    const ds = document.getElementById(`ds_${id}`);
    if (ds) {
      ds.textContent = "Checking…";
      ds.className = "dep-status checking";
    }

    fetch("/api/check-tool", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool: key }),
    })
      .then((r) => r.json())
      .then((data) => {
        const ok = data.installed;
        const ver = data.version ? data.version.split("\n")[0].trim() : "";
        if (ds) {
          ds.textContent = ok ? ver || "✓ Installed" : "✗ Not installed";
          ds.className = `dep-status ${ok ? "ok" : "missing"}`;
        }
        // Also update header dots
        fetchStatus();
      })
      .catch(() => {
        if (ds) {
          ds.textContent = "Check failed";
          ds.className = "dep-status checking";
        }
      });
  });
}

/* ════════════════════════════════════════════════
   BULK — START DOWNLOAD
════════════════════════════════════════════════ */
function startDownload() {
  songs = document
    .getElementById("songs_editor")
    .value.trim()
    .split("\n")
    .filter((l) => l.trim());
  if (!songs.length) {
    toast("⚠️ No songs in list");
    return;
  }

  const quality =
    document.querySelector('input[name="quality"]:checked')?.value || "320k";
  const fmt =
    document.querySelector('input[name="format"]:checked')?.value || "mp3";

  goTo(3);

  const totalEl = document.getElementById("dl_total");
  const doneEl = document.getElementById("dl_done");
  const pendEl = document.getElementById("dl_pending");
  const failEl = document.getElementById("dl_failed");
  const progFill = document.getElementById("progress_fill");
  const progPct = document.getElementById("progress_pct");
  const logEl = document.getElementById("dl_log");
  const termTitle = document.getElementById("term_title");

  totalEl.textContent = songs.length;
  doneEl.textContent = 0;
  pendEl.textContent = songs.length;
  failEl.textContent = 0;
  logEl.innerHTML = "";
  progFill.style.width = "0%";
  progPct.textContent = "0%";
  termTitle.textContent = `yt-dlp — downloading ${songs.length} songs`;

  fetch("/api/start-download", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ songs, bitrate: quality, format: fmt }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        appendLog(logEl, "err", `❌ ${data.error}`);
        return;
      }
      currentJob = data.job_id;

      const es = new EventSource(`/api/stream/${data.job_id}`);
      es.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "ping") return;

        const logCls =
          msg.type === "ok"
            ? "ok"
            : msg.type === "error"
              ? "err"
              : msg.type === "cmd"
                ? "cmd"
                : "info";
        appendLog(logEl, logCls, msg.text);

        doneEl.textContent = msg.done;
        failEl.textContent = msg.failed;
        const total = msg.total;
        const prog = total
          ? Math.round(((msg.done + msg.failed) / total) * 100)
          : 0;
        pendEl.textContent = total - msg.done - msg.failed;
        progFill.style.width = prog + "%";
        progPct.textContent = prog + "%";

        if (msg.type === "done") {
          es.close();
          markDone(3);
          document.getElementById("dl_done_bar").style.display = "flex";
          toast("✅ Download complete!");
        }
      };
      es.onerror = () => es.close();
    });
}

function appendLog(el, cls, text) {
  if (!text) return;
  const p = document.createElement("p");
  p.className = `line-${cls}`;
  p.textContent = text;
  el.appendChild(p);
  el.parentElement.scrollTop = el.parentElement.scrollHeight;
}

/* ════════════════════════════════════════════════
   BULK — RESULTS
════════════════════════════════════════════════ */
function populateResults() {
  if (!currentJob) return;
  fetch(`/api/job/${currentJob}`)
    .then((r) => r.json())
    .then((data) => {
      document.getElementById("res_total").textContent = data.total;
      document.getElementById("res_done").textContent = data.done;
      document.getElementById("res_failed").textContent = data.failed;
      const rate = data.total ? Math.round((data.done / data.total) * 100) : 0;
      document.getElementById("res_rate").textContent = rate + "%";
      document.getElementById("res_path").textContent = data.out_dir;
      if (data.failed > 0) {
        document.getElementById("fail_btn").style.display = "inline-flex";
        document.getElementById("failed_card").style.display = "block";
      }
    });
}

function downloadZip() {
  if (!currentJob) {
    toast("No active job");
    return;
  }
  toast("⏳ Preparing ZIP…");
  window.location.href = `/api/download-zip/${currentJob}`;
}

function downloadFailed() {
  if (!currentJob) return;
  window.location.href = `/api/download-txt/${currentJob}`;
}

function resetAll() {
  songs = [];
  currentJob = null;
  document.getElementById("songs_editor").value = "";
  const pa = document.getElementById("paste_area");
  if (pa) pa.value = "";
  document.getElementById("upload_result").style.display = "none";

  const zone = document.getElementById("drop_zone");
  if (zone) {
    zone.innerHTML = `<div class="drop-icon">📂</div>
      <p>Drop your CSV or Excel file here</p>
      <span>or click to browse</span>
      <input type="file" id="file_input" accept=".csv,.xlsx,.xls"
             onchange="handleUpload(event)" style="display:none">`;
    zone.onclick = () => document.getElementById("file_input").click();
  }

  document.querySelectorAll(".step-btn").forEach((b, i) => {
    b.classList.remove("done", "active");
    const num = document.getElementById(`snum${i}`);
    if (num) num.textContent = i + 1;
  });
  goTo(0);
  toast("↺ Pipeline reset");
}

/* ════════════════════════════════════════════════
   COPY HELPER
════════════════════════════════════════════════ */
function copyText(text) {
  navigator.clipboard
    .writeText(text)
    .then(() => {
      toast("✅ Copied!");
      document.querySelectorAll(".cmd-copy").forEach((btn) => {
        if (btn.getAttribute("onclick")?.includes(text.substring(0, 12))) {
          const orig = btn.textContent;
          btn.textContent = "Copied!";
          btn.classList.add("copied");
          setTimeout(() => {
            btn.textContent = orig;
            btn.classList.remove("copied");
          }, 1800);
        }
      });
    })
    .catch(() => prompt("Copy this command:", text));
}

/* ════════════════════════════════════════════════
   UTILITY
════════════════════════════════════════════════ */
function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Add spin keyframe if not already present
const style = document.createElement("style");
style.textContent =
  "@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }";
document.head.appendChild(style);
