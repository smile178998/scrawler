# Modern Web Scraper

A Playwright-powered web scraper with a FastAPI web UI. It launches a real Chromium/Chrome browser, renders JavaScript-heavy pages, and extracts structured content (body text, comments, videos, images, and metadata).

**Language / 语言：** **English** | [简体中文](README_zh-CN.md)

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![Version](https://img.shields.io/badge/version-1.3.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

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
- Smart image filtering — skips icons, UI sprites, recommendation thumbnails, and junk URLs
- Metadata extraction from `<meta>` tags
- Export results to TXT or JSON

### Video platforms (`video_platforms/`)
- Auto-detects major video sites: **Bilibili**, **YouTube**, **Vimeo**, **TikTok**, **Douyin**, **Twitter/X**, **Twitch**, **Dailymotion**, **Niconico**
- **Bilibili** — dedicated handler: `__INITIAL_STATE__`, `__playinfo__`, WBI comment pagination, DASH streams
- **Other platforms** — generic handler via Open Graph, JSON-LD, `ytInitialPlayerResponse`, and DOM `<video>` tags
- Unified result shape: `platform`, `platform_data`, curated images (cover / avatar / first-frame)
- Video platform URLs bypass the generic auto-selector automatically

### Media download & in-browser playback
- **Auto-download** images and videos to local `downloads/` folder
- Videos validated by file magic bytes — HTML error pages are rejected (no fake `.bin` / `.mp4`)
- **ffmpeg** remux: merges Bilibili DASH (`.m4s`) into browser-playable `.mp4`
- **Videos tab** — inline `<video>` player; click ▶ to watch locally saved files
- `/downloads/...` served with correct `video/mp4` MIME type

### Saved login (all sites)
- **Remember login** — persistent Chrome profile in `.chrome_profile/`
- Log in once per site in **Visible browser** mode; session reused on later scrapes
- Works for Bilibili, YouTube, forums, and any site that needs authentication
- Optional Cookie field overrides the saved session when needed

### Smart auto-selector
- **Heuristic DOM scoring** — finds main content and comment blocks without manual CSS selectors
- **Stable CSS generation** — prefers `#id` and semantic classes; skips dynamic hashed classes
- **AI fallback** — OpenAI-compatible APIs (OpenAI, DeepSeek, Ollama) when heuristics fail
- **Selector validation** — re-extracts content and keeps the best result
- **Selectors tab** in the UI — shows method, confidence, and discovered selectors; apply to form with one click

### Anti-detection & reliability
- **Stealth Fetcher** (`fetcher.py`) — fast HTTP via `curl_cffi`: browser TLS/JA3 fingerprint, realistic headers, optional HTTP/3
- **Dynamic Fetcher** (`dynamic_fetcher.py`) — full Playwright browser for JS/SPA pages; Chromium or system **Google Chrome**
- **Stealthy Fetcher** (`stealthy_fetcher.py`) — Patchright/Playwright + fingerprint spoofing; `solve_cloudflare` for Turnstile/Interstitial
- **System Chrome** support (more realistic fingerprint than bundled Chromium)
- **playwright-stealth** + built-in fingerprint patches (webdriver, WebGL, headers)
- Randomized browser profiles (UA, viewport, locale, timezone)
- Human-like behavior simulation (mouse movement, scrolling)
- Cloudflare / WAF challenge page detection with auto-wait
- Multi-strategy retry: headless → extended wait → visible browser fallback
- Navigation retry on transient network errors; dead env proxies auto-skipped
- HTTP/SOCKS5 **proxy** support (UI field or `SCRAPER_PROXY` / `HTTP_PROXY` env vars)
- **ProxyRotator** — round-robin / random / custom strategies for all Session types; per-request `proxy=` override
- **Domain / ad blocking** — `blocked_domains` + `block_ads` (~3,500 trackers) on browser fetchers
- Configurable JS wait time and auto-scroll
- **Port auto-selection** — if 8000 is busy, tries 8001+ automatically

---

## Project structure

```
spaider_crawler/
├── app.py              # FastAPI web server + SSE API + /downloads media route
├── scraper_core.py     # Playwright pipeline + content parsing
├── selector_engine.py  # Smart CSS selector discovery (heuristic + AI)
├── media_downloader.py # Auto-download images/videos; ffmpeg merge; MIME types
├── fetcher.py          # Stealth HTTP client (TLS fingerprint + HTTP/3 via curl_cffi)
├── dynamic_fetcher.py  # Playwright DynamicFetcher (Chromium / Google Chrome)
├── stealthy_fetcher.py # StealthyFetcher — fingerprint spoofing + Cloudflare solver
├── session_store.py    # Cookie / state persistence helpers
├── sessions.py         # Unified exports: FetcherSession / DynamicSession / StealthySession
├── proxy_rotator.py    # ProxyRotator — round-robin / random / custom strategies
├── request_blocking.py # Domain + ad/tracker request blocking for browser fetchers
├── ad_domains.py       # Loader for bundled ~3,500 ad/tracker domains
├── data/
│   └── ad_domains.txt  # Peter Lowe ad/tracker host list
├── video_platforms/    # Multi-platform video metadata + stream extraction
│   ├── __init__.py     # detect / extract / merge entry points
│   ├── registry.py     # Platform URL matching and dispatch
│   ├── bilibili.py     # Bilibili handler (WBI comments, DASH streams)
│   ├── generic.py      # YouTube, Vimeo, TikTok, etc.
│   └── merge.py        # Unified result merge → platform_data
├── image_utils.py      # Image URL normalization and junk filtering
├── requirements.txt
├── payload.json        # Example API request body
├── demo.gif            # Usage demo animation for README
├── .env.example        # Env template (copy to .env)
├── templates/
│   └── index.html      # Web UI
├── static/
│   ├── css/style.css
│   └── js/app.js
└── scripts/
    ├── start.ps1       # Kill stale servers, start on port 8000 (Windows)
    ├── scrape_video.py # CLI: scrape any supported video URL → JSON
    └── record_demo_gif.py
```

---

## Requirements

- Python 3.10+
- `pip` and a writable Python environment
- Google Chrome (optional, recommended for stronger anti-detection)
- **ffmpeg** (optional, recommended for merging DASH streams into playable MP4)

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

4. (Optional) Configure environment — copy `.env.example` to `.env`:

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

```env
OPENAI_API_KEY=sk-your-key-here

# Optional proxy (also readable from HTTP_PROXY / HTTPS_PROXY)
# SCRAPER_PROXY=http://127.0.0.1:7890

# Optional Bilibili cookie override (saved profile is preferred)
# BILI_COOKIE=SESSDATA=...; bili_jct=...
```

---

## Quickstart

**Windows (recommended):**

```powershell
.\scripts\start.ps1
```

**Or manually:**

```bash
python app.py
```

Open the URL printed in the terminal (usually `http://127.0.0.1:8000/`). Confirm the header shows **v1.3.0**.

Enter a URL and click **Start Scrape**.

Or run with uvicorn directly:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### Example: Bilibili video

```
https://www.bilibili.com/video/BV1yk7X6KEz4
```

| Option | Value |
|--------|-------|
| Remember login | On (log in once in Visible mode) |
| JS wait | `8000` ms |
| Auto-scroll | On |
| Use system Chrome | On |
| Auto-download | On |
| Smart auto-selector | Off (auto-disabled for video platforms) |
| Browser mode | Visible (first run / captcha) |

### Example: YouTube video

```
https://www.youtube.com/watch?v=...
```

| Option | Value |
|--------|-------|
| Remember login | On |
| JS wait | `8000` ms |
| Use system Chrome | On |
| Visible browser | On (needed for stream URLs) |
| Auto-download | On |
| Proxy | Only if required in your network |

Results appear in **Text**, **Videos** (inline player), **Images**, and **Metadata** (`platform`, `platform_data`).

### CLI scrape

```bash
python scripts/scrape_video.py "https://www.bilibili.com/video/BV1yk7X6KEz4" output.json
```

---

## Web UI options

| Option | Description |
|--------|-------------|
| Text / Comment selector | CSS selectors; leave empty for auto-detection |
| **Remember login** | Persistent `.chrome_profile/` — log in once per site in Visible mode |
| Cookie | Optional session override (`key1=val1; key2=val2`) |
| Proxy | `http://host:port` or `socks5://user:pass@host:port`; leave empty for direct connection |
| JS wait (ms) | Time to wait for JavaScript after page load (500–30000) |
| Browser mode | `Auto` / `Headless only` / `Visible browser` |
| Max retries | Number of retry attempts with alternate strategies (0–4) |
| Use system Chrome | Prefer installed Chrome over bundled Chromium |
| Simulate human | Random mouse movement and scroll behavior |
| Block resources | Skip images/fonts for speed (may trigger bot detection) |
| **Auto-download** | Save images and videos to `downloads/`; play videos in the Videos tab |
| Smart auto-selector | DOM scoring to discover text/comment CSS selectors automatically |
| Enable AI fallback | Call LLM when heuristics fail (requires API key) |
| AI API key / base URL / model | Override env vars; supports OpenAI-compatible providers |

**Protected / login sites:** Remember login + **Visible** mode + system Chrome. Add Cookie only if needed.

**Video platforms:** Leave selectors empty; `video_platforms/` runs automatically. Enable Auto-download for local playback.

**Unknown layouts:** Leave CSS selectors empty, enable **Smart auto-selector**. Add an API key for hard pages.

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

> **Note:** Known video platform URLs bypass the generic auto-selector and use `video_platforms/` instead.

---

## Stealth Fetcher (HTTP)

`fetcher.py` wraps **curl_cffi** for fast, stealthy HTTP (no browser). Use it for APIs, CDN media, and static pages.

| Feature | Detail |
|---------|--------|
| TLS fingerprint | Impersonate Chrome / Edge / Safari (`impersonate="chrome"`) |
| Headers | Matching browser headers + optional `stealthy_headers` (`Sec-Fetch-*`, Accept-Language, Referer) |
| HTTP/3 | Opt-in with `http3=True` (auto-falls back if the peer rejects QUIC) |
| Fallback | If `curl_cffi` is missing, uses `urllib` (no fingerprint spoofing) |

Media downloads already go through Fetcher. Standalone usage:

```python
from fetcher import Fetcher, FetcherSession

# One-shot GET with Chrome TLS fingerprint
r = Fetcher.get("https://example.com", stealthy_headers=True)
print(r.status_code, r.text[:200])

# Prefer HTTP/3 when the server supports it
r = Fetcher.get("https://cloudflare-http3-demo.zone", http3=True, impersonate="chrome")

# Session with cookies + proxy
with FetcherSession(proxy="http://127.0.0.1:7890", impersonate="chrome") as s:
    s.get("https://example.com/login")
    data = s.post("https://example.com/api", json_body={"q": "test"}).json()
```

---

## Dynamic Fetcher (browser)

`dynamic_fetcher.py` uses **Playwright** for pages that need JavaScript. Supports bundled **Chromium** and installed **Google Chrome**.

| Option | Meaning |
|--------|---------|
| `real_chrome=True` (or `use_chrome=True`) | Launch system Google Chrome; falls back to Chromium |
| `headless` | Hidden (default) or visible browser |
| `network_idle` / `wait` / `wait_selector` | Wait strategies after navigation |
| `page_action` / `page_setup` | Custom Playwright hooks |
| `disable_resources` | Block images/fonts/CSS for speed |
| `blocked_domains` | Set/list of hostnames to block (subdomains matched) |
| `block_ads` | Enable built-in ~3,500 ad/tracker domain blocklist |
| `proxy` / `cookies` / `extra_headers` | Session controls |

```python
from dynamic_fetcher import DynamicFetcher, DynamicSession

r = DynamicFetcher.fetch(
    "https://spa.example.com",
    real_chrome=True,
    headless=True,
    network_idle=True,
    wait=1500,
    wait_selector="main",
)
print(r.title, r.status_code, r.browser_engine)

# Reuse one browser for multiple pages
with DynamicSession(real_chrome=True, headless=True) as session:
    home = session.fetch("https://example.com")
    about = session.fetch("https://example.com/about")
```

> Prefer **Fetcher** for static/API/CDN requests; use **DynamicFetcher** when the DOM is built by JavaScript.

---

## Stealthy Fetcher (anti-bot)

`stealthy_fetcher.py` is the strongest local browser tier: **Patchright** (if installed) or Playwright, plus fingerprint spoofing and optional Cloudflare challenge automation.

| Option | Meaning |
|--------|---------|
| `solve_cloudflare=True` | Detect & clear Turnstile / interstitial (managed, interactive, non-interactive, embedded) |
| `hide_canvas=True` | Canvas noise against fingerprinting |
| `block_webrtc=True` | Stop WebRTC local IP leaks |
| `allow_webgl=True` | Keep WebGL on (recommended — many WAFs check it) |
| `real_chrome=True` | Prefer system Google Chrome |
| `humanize=True` | Mouse jitter (auto-on when solving CF) |

```python
from stealthy_fetcher import StealthyFetcher, StealthySession

r = StealthyFetcher.fetch(
    "https://protected.example",
    solve_cloudflare=True,
    hide_canvas=True,
    block_webrtc=True,
    real_chrome=True,
    headless=True,
    timeout=60000,
)
print(r.title, r.extras.get("cloudflare_solved"), r.browser_engine)

# Install stronger engine (recommended):
#   pip install patchright
#   python -m patchright install chrome
```

> Cloudflare solving presents a realistic browser and automates the UI — it does not break CAPTCHA cryptography. For hardest sites, use **Visible** mode + a clean residential proxy.

---

## Session management

All three session classes keep **cookies** and a custom **`state`** dict across requests, and can persist to JSON:

| Class | Engine | Best for |
|-------|--------|----------|
| `FetcherSession` | curl_cffi HTTP | Login APIs, token refresh, CDN downloads |
| `DynamicSession` | Playwright | Multi-page JS flows, same browser context |
| `StealthySession` | Patchright/Playwright | CF-protected multi-step flows |

Shared API: `get_cookies` / `set_cookies` / `clear_cookies` / `save` / `load` / `snapshot` / `restore` / `state`.

```python
from sessions import FetcherSession, DynamicSession, StealthySession

# HTTP — cookies auto-saved on context exit
with FetcherSession(session_file=".sessions/api.json") as s:
    s.get("https://httpbin.org/cookies/set?session=abc")
    s.state["role"] = "user"
    print(s.cookies_map())

# Browser — one context, cookies survive across pages
with DynamicSession(real_chrome=True, session_file=".sessions/web.json") as s:
    s.fetch("https://example.com")
    s.set_cookies({"sid": "xyz"}, url="https://example.com")
    s.fetch("https://example.com/account")
    snap = s.snapshot()

# Resume later
with DynamicSession(real_chrome=True) as s:
    s.restore(snap, url="https://example.com")
    s.fetch("https://example.com/dashboard")
```

Or import sessions from their modules: `from fetcher import FetcherSession`, etc.

---

## Proxy rotation

Built-in ``ProxyRotator`` works with **all Session types**. Default strategy is round-robin; pass a custom callable for your own policy. Per-request ``proxy=`` always overrides the rotator.

```python
from sessions import FetcherSession, DynamicSession, ProxyRotator, random_rotation

rotator = ProxyRotator([
    "http://1.2.3.4:8080",
    {"server": "http://5.6.7.8:8080", "username": "u", "password": "p"},
])

with FetcherSession(proxy_rotator=rotator) as s:
    s.get("https://example.com/a")   # proxy #1
    s.get("https://example.com/b")   # proxy #2
    s.get("https://example.com/c")   # proxy #1 again
    # Force a specific proxy for one call:
    s.get("https://example.com/d", proxy="http://9.9.9.9:3128")
    # Direct (no proxy) for one call:
    s.get("https://example.com/e", proxy=None)
    print(s.last_proxy)

# Random strategy
rotator = ProxyRotator(proxies, strategy=random_rotation)

# Custom sticky strategy
def sticky(proxies, idx):
    return proxies[0], idx

with DynamicSession(proxy_rotator=ProxyRotator(proxies, strategy=sticky)) as s:
    s.fetch("https://example.com")
```

Failed proxies can be skipped: ``rotator.mark_failed(proxy)`` / ``rotator.reset_failures()``.

---

## Domain & ad blocking

Browser fetchers (`DynamicSession` / `StealthySession`) can abort requests before they leave the browser — no DNS/TCP for blocked hosts.

| Option | Effect |
|--------|--------|
| `blocked_domains={"tracker.net", "ads.example.com"}` | Block those domains **and all subdomains** |
| `block_ads=True` | Block ~3,500 known ad/tracker hosts (Peter Lowe list) |
| `disable_resources=True` | Also drop image/font/stylesheet/media (speed) |

```python
from dynamic_fetcher import DynamicFetcher
from stealthy_fetcher import StealthyFetcher

# Custom domains + built-in ads
r = DynamicFetcher.fetch(
    "https://news.example",
    block_ads=True,
    blocked_domains={"metrics.vendor.com", "cdn.doubleclick.net"},
)

# Stealthy session
with StealthySession(block_ads=True, blocked_domains={"evil.tracker"}) as s:
    page = s.fetch("https://protected.example")
```

Check list size: ``from ad_domains import ad_domain_count; print(ad_domain_count())``.

---

## API reference

### `GET /api/health`

Health check and version info.

```json
{
  "status": "ok",
  "version": "1.3.0",
  "features": ["video_platforms", "wbi_comments", "download_media", "saved_profile", "stealth_fetcher", "dynamic_fetcher", "stealthy_fetcher", "session_manager"]
}
```

### `GET /downloads/{path}`

Serves downloaded media files with correct MIME types (e.g. `video/mp4` for playback in the browser).

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
  "ai_model": "",
  "download_media": true,
  "use_saved_profile": true
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
| `download_media` | bool | `true` | Download images/videos to `downloads/` |
| `use_saved_profile` | bool | `true` | Use persistent `.chrome_profile/` login |

**SSE events:**

| Event | Description |
|-------|-------------|
| `log` | Progress message |
| `ping` | Heartbeat with elapsed seconds (keeps UI alive during long scrapes) |
| `done` | Final JSON result |
| `error` | Error message (human-readable) |

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
    "wait_ms": 8000,
    "use_chrome": True,
    "download_media": True,
    "use_saved_profile": True,
    "auto_selector": False,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/scrape",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=300) as resp:
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
  "videos": ["/downloads/My_Video_1234567890/videos/My_Video.mp4"],
  "images": [
    "https://i2.hdslb.com/bfs/archive/cover.jpg",
    "https://i1.hdslb.com/bfs/face/avatar.jpg"
  ],
  "meta": {
    "video_platform": "bilibili",
    "bilibili_bvid": "BV1yk7X6KEz4",
    "bilibili_aid": "116686023891513",
    "bilibili_cid": "38829687897"
  },
  "platform_data": {
    "platform": "bilibili",
    "bvid": "BV1yk7X6KEz4",
    "aid": 116686023891513,
    "title": "...",
    "description": "...",
    "owner": { "name": "...", "face": "..." },
    "stat": { "view": 5574174, "like": 182118, "reply": 1791 },
    "video_streams": [{ "url": "...", "width": 1920, "height": 1080 }],
    "audio_streams": [{ "url": "..." }],
    "comments": ["user: comment text"]
  },
  "downloads": {
    "dir": "C:\\...\\downloads\\My_Video_1234567890",
    "web_dir": "/downloads/My_Video_1234567890",
    "images": [
      { "url": "https://...", "path": "...", "web_path": "/downloads/.../images/001.jpg", "filename": "001.jpg" }
    ],
    "videos": [
      {
        "url": "https://...",
        "path": "...",
        "web_path": "/downloads/.../videos/My_Video.mp4",
        "filename": "My_Video.mp4",
        "mime": "video/mp4",
        "playable": true
      }
    ]
  }
}
```

Results are displayed across tabs (Text / Comments / **Videos** / Images / **Selectors** / Metadata / Log) and can be exported to TXT or JSON.

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
| Port 8000 in use | Run `.\scripts\start.ps1` (Windows) or use the port shown in terminal (e.g. 8001) |
| `ERR_CONNECTION_CLOSED` on navigate | Clear dead `HTTP_PROXY` env var; leave Proxy empty for direct connection; try Visible + system Chrome |
| Cloudflare / WAF blocks | Use **Visible** mode + system Chrome + proxy |
| Empty content on SPA | Increase JS wait time; enable auto-scroll |
| CAPTCHA appears | Switch to **Visible** mode, enable Remember login, solve manually once |
| System Chrome not found | Uncheck **Use system Chrome** or install Chrome |
| Wrong content extracted | Leave selectors empty; enable **Smart auto-selector** |
| AI selector not triggered | Set `OPENAI_API_KEY` in `.env` or paste key in UI |
| Video platform: generic scrape only | Enable Remember login + Visible browser; check Log for captcha |
| Video won't play (black player) | Re-scrape with Auto-download on; install **ffmpeg** for DASH merge |
| Downloaded file is HTML not video | Stream URL expired or needs login — use Visible mode + saved profile |
| Bilibili: too many junk images | Fixed — only cover / avatar / first-frame kept |
| Bilibili: few comments | Enable Remember login or paste `BILI_COOKIE` in Advanced Options |
| Bilibili / YouTube: stream URLs expire | CDN links are time-limited; download soon after scrape |
| `.m4s` streams | Install ffmpeg — auto-merged to `.mp4` when available |
| Profile locked error | Close other Chrome / scraper windows using `.chrome_profile/` |

---

## Notes & responsible use

- Only scrape content you are authorized to access. Respect `robots.txt` and website terms of service.
- This tool is for learning and legitimate research — it cannot bypass all CAPTCHAs or commercial WAF systems.
- Use the `cookie` option only for your own session state; never use others' credentials.
- Video streams may be protected by copyright — use extracted data responsibly.

---

## License

MIT License — see [LICENSE](LICENSE).
