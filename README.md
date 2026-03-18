# 🎵 Music Pipeline — Web App (localhost)

A complete Flask web app to bulk process and download songs from CSV/Excel.

---

## 🚀 Quick Start

### Step 1 — Install Python requirements

```bash
pip install flask pandas openpyxl
```

### Step 2 — Install a download tool (pick one)

```bash
pip install spotdl     # Recommended — Spotify-based, auto metadata + art
pip install yt-dlp     # Free — YouTube Music, widest coverage
pip install deemix     # FLAC quality — needs Deezer ARL token
```

### Step 3 — Run the server

```bash
python app.py
```

### Step 4 — Open in browser

```
http://localhost:5000
```

---

## 📁 Project Structure

```
music_pipeline_app/
├── app.py                  ← Flask server (run this)
├── requirements.txt        ← Python dependencies
├── sample_songs.csv        ← Test data (20 songs)
├── templates/
│   └── index.html          ← Main UI
├── static/
│   ├── css/style.css       ← Styles
│   └── js/app.js           ← Frontend logic
├── uploads/                ← Temp file uploads (auto-cleaned)
└── downloads/              ← Output folder (songs saved here)
```

---

## 🔧 How It Works

1. **Upload** — Upload your CSV or Excel file with Track Name & Artist Name columns
2. **Review** — Edit the generated songs list, remove duplicates, sort
3. **Tool Setup** — Choose SpotDL / yt-dlp / Deemix + quality (128k → FLAC)
4. **Download** — Watch real-time progress as songs download to `./downloads/`
5. **Results** — Download all songs as a ZIP or retry failed ones

---

## 📋 CSV Format

| Track Name | Artist Name |
|-----------|-------------|
| Blinding Lights | The Weeknd |
| Shape of You | Ed Sheeran |

Column names are auto-detected (case-insensitive).

---

## 🛠 Tool Comparison

| Tool | Source | Max Quality | Free | Notes |
|------|--------|-------------|------|-------|
| SpotDL | Spotify/YT | 320k MP3 | ✅ | Best metadata, auto album art |
| yt-dlp | YouTube Music | 320k MP3 | ✅ | Widest song coverage |
| Deemix | Deezer | FLAC | ⚠️ | Needs ARL token from Deezer |

---

## ⚠️ Notes

- Songs are saved to `downloads/music_TIMESTAMP/` on your machine
- Failed songs are saved to `failed_songs.txt` for retry
- Deemix requires a Deezer account ARL token: login → F12 → Application → Cookies → `arl`
- Respect copyright laws in your region
