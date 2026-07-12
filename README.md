# Modern Web Scraper

A Playwright-powered web scraper with a FastAPI web UI. It launches a real Chromium/Chrome browser, renders JavaScript-heavy pages, and extracts structured content (body text, comments, videos, images, and metadata).

**Language / 语言：** **English** | [简体中文](README_zh-CN.md)

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Demo

![Usage demo](demo.gif)

*Enter a URL → open Advanced Options → start scrape → view Text, Log, and Selectors tabs.*

![Screenshot](image.png)

## Features

### Content extraction
- Real browser rendering (Playwright) — supports JS, SPAs, and lazy-loaded content
- Auto-detect body text + optional CSS selector override
- Heuristic comment extraction + optional CSS selector override
- Video and image link extraction (including lazy-load attributes like `data-src`)
- Smart image filtering — skips icons, UI sprites, and junk thumbnails
- Metadata extraction from `<meta>` tags
- Export results to TXT or JSON

### Platform support: Bilibili
- Auto-detects `bilibili.com` video pages
- Extracts title, description, UP owner, stats (views, likes, coins, etc.)
- Parses `__INITIAL_STATE__` and `__playinfo__` for **DASH video/audio stream URLs**
- Curated images only: cover, UP avatar, first-frame preview (no recommendation clutter)
- Partial comment extraction; full comments require login Cookie

### Smart auto-selector
- **Heuristic DOM scoring** — finds main content and comment blocks without manual CSS selectors
- **Stable CSS generation** — prefers `#id` and semantic classes; skips dynamic hashed classes
- **AI fallback** — OpenAI-compatible APIs (OpenAI, DeepSeek, Ollama) when heuristics fail
- **Selector validation** — re-extracts content and keeps the best result
- **Selectors tab** in the UI — shows method, confidence, and discovered selectors; apply to form with one click

### Anti-detection & reliability
- **System Chrome** support (more realistic fingerprint than bundled Chromium)
- **playwright-stealth** + built-in fingerprint patches (webdriver, WebGL, headers)
- Randomized browser profiles (UA, viewport, locale, timezone)
- Human-like behavior simulation (mouse movement, scrolling)
- Cloudflare / WAF challenge page detection with auto-wait
- Multi-strategy retry: headless → extended wait → visible browser fallback
- HTTP/SOCKS5 **proxy** support (with optional auth)
- Cookie injection for authenticated sessions
- Configurable JS wait time and auto-scroll

---

## Project structure

```
spaider_crawler/
├── app.py              # FastAPI web server + SSE API
├── scraper_core.py     # Playwright pipeline + content parsing
├── selector_engine.py  # Smart CSS selector discovery (heuristic + AI)
├── bilibili_parser.py  # Bilibili video metadata + stream extraction
├── image_utils.py      # Image URL normalization and junk filtering
├── requirements.txt
├── payload.json        # Example API request body
├── demo.gif            # Usage demo animation for README
├── .env.example        # AI API key template (copy to .env)
├── templates/
│   └── index.html      # Web UI
├── static/
│   ├── css/style.css
│   └── js/app.js
└── scripts/
    └── record_demo_gif.py  # Regenerate demo.gif for README
```

---

## Requirements

- Python 3.10+
- `pip` and a writable Python environment
- Google Chrome (optional, recommended for stronger anti-detection)

Dependencies are listed in `requirements.txt`.

---

## Installation

1. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

3. Install Playwright browser binaries:

```bash
python -m playwright install chromium
```

> **Tip:** Install [Google Chrome](https://www.google.com/chrome/) on your system and enable **Use system Chrome** in Advanced Options for better fingerprint evasion.

4. (Optional) Configure AI selector fallback — copy `.env.example` to `.env` and set your API key:

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

```env
OPENAI_API_KEY=sk-your-key-here
# DeepSeek: AI_BASE_URL=https://api.deepseek.com/v1  AI_MODEL=deepseek-chat
# Ollama:   AI_BASE_URL=http://127.0.0.1:11434/v1   AI_MODEL=llama3.2
```

---

## Quickstart

Start the web UI:

```bash
python app.py
```

Open `http://127.0.0.1:8000/` in your browser, enter a URL, and click **Start Scrape**.

Or run with uvicorn directly:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### Example: scrape a Bilibili video

```
https://www.bilibili.com/video/BV1yk7X6KEz4
```

Recommended settings:

| Option | Value |
|--------|-------|
| JS wait | `5000–8000` ms |
| Auto-scroll | On |
| Use system Chrome | On |
| Smart auto-selector | Optional (Bilibili uses its own parser) |
| Cookie | Paste Bilibili login cookies for full comments |

Results appear in **Text**, **Videos**, **Images**, and **Metadata** (`bilibili` object).

---

## Web UI options

| Option | Description |
|--------|-------------|
| Text / Comment selector | CSS selectors; leave empty for auto-detection |
| Cookie | Session cookies (`key1=val1; key2=val2`) |
| Proxy | `http://host:port` or `socks5://user:pass@host:port` |
| JS wait (ms) | Time to wait for JavaScript after page load (500–30000) |
| Browser mode | `Auto` / `Headless only` / `Visible browser` |
| Max retries | Number of retry attempts with alternate strategies (0–4) |
| Use system Chrome | Prefer installed Chrome over bundled Chromium |
| Simulate human | Random mouse movement and scroll behavior |
| Block resources | Skip images/fonts for speed (may trigger bot detection) |
| Smart auto-selector | DOM scoring to discover text/comment CSS selectors automatically |
| Enable AI fallback | Call LLM when heuristics fail (requires API key) |
| AI API key / base URL / model | Override env vars; supports OpenAI-compatible providers |

**Protected sites:** Browser mode = **Auto** or **Visible**, enable **Use system Chrome**, add a proxy if IP is blocked.

**Unknown layouts:** Leave CSS selectors empty, enable **Smart auto-selector**. Add an API key for hard pages.

**Bilibili videos:** Leave selectors empty; the Bilibili parser runs automatically. Add Cookie for full comments.

---

## Smart auto-selector

When text/comment CSS selectors are empty (or extraction is weak), the engine runs automatically after each scrape:

```
HTML → DOM scoring → CSS selector generation → validate → re-extract
                              ↓ (if weak)
                         AI analysis → new selectors → re-extract
```

| Method | Description |
|--------|-------------|
| `heuristic` | DOM text density, paragraph count, semantic class names |
| `ai` | LLM analyzes simplified HTML and returns selectors |
| `hybrid` | Heuristic found partial matches; AI refined the result |

Discovered selectors appear in the **Selectors** tab and in the API response under `discovered_selectors` / `applied_selectors`.

> **Note:** Bilibili URLs bypass the generic auto-selector and use `bilibili_parser.py` instead.

---

## API reference

### `GET /api/health`

Health check.

```json
{ "status": "ok" }
```

### `POST /api/scrape`

Starts a scrape job. Returns a **Server-Sent Events (SSE)** stream.

**Request body:**

```json
{
  "url": "https://example.com",
  "text_selector": "",
  "comment_selector": "",
  "cookie": "",
  "proxy": "",
  "wait_ms": 3500,
  "scroll": true,
  "use_chrome": true,
  "headless": "auto",
  "max_retries": 2,
  "simulate_human": true,
  "block_resources": false,
  "auto_selector": true,
  "auto_selector_ai": true,
  "ai_api_key": "",
  "ai_base_url": "",
  "ai_model": ""
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | *required* | Target URL |
| `text_selector` | string | `""` | CSS selector for body text |
| `comment_selector` | string | `""` | CSS selector for comments |
| `cookie` | string | `""` | Cookie string for auth |
| `proxy` | string | `""` | Proxy server URL |
| `wait_ms` | int | `3500` | JS settle time (500–30000) |
| `scroll` | bool | `true` | Auto-scroll for lazy content |
| `use_chrome` | bool | `true` | Use system Chrome if available |
| `headless` | string | `"auto"` | `"auto"`, `"hidden"`, or `"visible"` |
| `max_retries` | int | `2` | Max retry attempts (0–4) |
| `simulate_human` | bool | `true` | Simulate mouse/scroll behavior |
| `block_resources` | bool | `false` | Block images/fonts/styles |
| `auto_selector` | bool | `true` | Enable smart CSS selector discovery |
| `auto_selector_ai` | bool | `true` | Use AI when heuristics fail |
| `ai_api_key` | string | `""` | API key (falls back to `OPENAI_API_KEY` env) |
| `ai_base_url` | string | `""` | API base URL (default: OpenAI) |
| `ai_model` | string | `""` | Model name (default: `gpt-4o-mini`) |

**SSE events:**

| Event | Description |
|-------|-------------|
| `log` | Progress message |
| `done` | Final JSON result |
| `error` | Error message |

**Validation errors** return HTTP `422` with a JSON body:

```json
{
  "error": "Invalid request",
  "details": ["headless: Input should be 'auto', 'hidden' or 'visible'"]
}
```

### Example (Python)

```python
import json
import urllib.request

body = json.dumps({
    "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
    "wait_ms": 6000,
    "use_chrome": True,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/scrape",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=180) as resp:
    for line in resp.read().decode().splitlines():
        if line.startswith("data: "):
            print(line[6:])
```

### Example (PowerShell)

```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/scrape `
  -Method Post `
  -Body (Get-Content payload.json -Raw) `
  -ContentType "application/json" `
  -OutFile sse_response.txt
```

---

## API output

After a successful scrape, the `done` event contains:

```json
{
  "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
  "title": "Video title",
  "platform": "bilibili",
  "text_paragraphs": ["播放 5,574,174 · 点赞 182,118 · ...", "UP主: ...", "Description..."],
  "comments": ["user: comment text"],
  "videos": ["https://...m4s?..."],
  "images": [
    "https://i2.hdslb.com/bfs/archive/cover.jpg",
    "https://i1.hdslb.com/bfs/face/avatar.jpg"
  ],
  "meta": {
    "bilibili_bvid": "BV1yk7X6KEz4",
    "bilibili_aid": "116686023891513",
    "bilibili_cid": "38829687897"
  },
  "bilibili": {
    "bvid": "BV1yk7X6KEz4",
    "aid": 116686023891513,
    "cid": 38829687897,
    "title": "...",
    "description": "...",
    "owner": { "name": "...", "face": "..." },
    "stat": { "view": 5574174, "like": 182118, "reply": 1791 },
    "video_streams": [{ "url": "...", "width": 1920, "height": 1080 }],
    "audio_streams": [{ "url": "..." }]
  }
}
```

Results are displayed across tabs (Text / Comments / Videos / Images / **Selectors** / Metadata / Log) and can be exported to TXT or JSON.

---

## Optional: Docker (experimental)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

> Containers may need extra system libraries for Chromium (fonts, GTK, etc.) and additional flags depending on the host.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Playwright fails to launch | Run `python -m playwright install chromium` |
| Port 8000 in use | Stop other processes: `netstat -ano \| findstr :8000` (Windows) |
| Cloudflare / WAF blocks | Use **Visible** mode + system Chrome + proxy |
| Empty content on SPA | Increase JS wait time; enable auto-scroll |
| CAPTCHA appears | Switch to **Visible** mode and solve manually |
| System Chrome not found | Uncheck **Use system Chrome** or install Chrome |
| Wrong content extracted | Leave selectors empty; enable **Smart auto-selector** |
| AI selector not triggered | Set `OPENAI_API_KEY` in `.env` or paste key in UI |
| AI request fails | Check `ai_base_url` / `ai_model`; verify provider compatibility |
| Bilibili: too many junk images | Fixed in latest version — only cover/avatar/first-frame kept |
| Bilibili: few or no comments | Paste login Cookie (`SESSDATA`, `bili_jct`) in Advanced Options |
| Bilibili: video URLs expire | CDN links are signed and time-limited; download soon after scrape |
| Bilibili: `.m4s` streams | DASH segments — merge with ffmpeg to get a full MP4 file |

---

## Notes & responsible use

- Only scrape content you are authorized to access. Respect `robots.txt` and website terms of service.
- This tool is for learning and legitimate research — it cannot bypass all CAPTCHAs or commercial WAF systems.
- Use the `cookie` option only for your own session state; never use others' credentials.
- Bilibili video streams may be protected by copyright — use extracted data responsibly.

---

## License

MIT License — see [LICENSE](LICENSE).
