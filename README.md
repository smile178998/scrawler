# Modern Web Scraper

A Playwright-powered web scraper with a FastAPI UI, plus a three-tier programmatic fetch stack (HTTP → browser → stealth). It renders JavaScript-heavy pages and extracts structured content (text, comments, videos, images, metadata), with optional local media download and playback.

**Language / 语言：** **English** | [简体中文](README_zh-CN.md)

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![Version](https://img.shields.io/badge/version-1.3.0-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Demo

![Usage demo](demo.gif)

*Enter a URL → open Advanced Options → start scrape → view Text, Videos, Log, and Selectors tabs.*

![Screenshot](image.png)

---

## Architecture at a glance

| Layer | Module | Role |
|-------|--------|------|
| **Web UI / SSE API** | `app.py` + `scraper_core.py` | Full scrape pipeline for browsers and video sites |
| **Tier 1 — HTTP** | `fetcher.py` | Fast stealth requests (`curl_cffi`): TLS fingerprint, headers, optional HTTP/3 |
| **Tier 2 — Browser** | `dynamic_fetcher.py` | Playwright Chromium / Google Chrome for JS/SPA pages |
| **Tier 3 — Stealth** | `stealthy_fetcher.py` | Patchright/Playwright + fingerprint spoofing + Cloudflare UI flow |
| **Sessions** | `sessions.py` | `FetcherSession` / `DynamicSession` / `StealthySession` — cookies + state |
| **Proxy** | `proxy_rotator.py` | Round-robin / random / custom rotation; per-request override |
| **Blocking** | `request_blocking.py` | `blocked_domains` + `block_ads` (~3,500 trackers) |

---

## Features

### Content extraction (Web UI)
- Real browser rendering (Playwright) — JS, SPAs, lazy-loaded content
- Auto body/comment detection + optional CSS overrides
- Video & image extraction (incl. lazy-load attrs like `data-src`)
- Smart image filtering (icons, sprites, junk thumbnails)
- Metadata from `<meta>` tags; export to TXT / JSON

### Video platforms (`video_platforms/`)
- Auto-detects: **Bilibili**, **YouTube**, **Vimeo**, **TikTok**, **Douyin**, **Twitter/X**, **Twitch**, **Dailymotion**, **Niconico**
- **Bilibili** — `__INITIAL_STATE__`, `__playinfo__`, WBI comment pagination, DASH streams
- **Others** — Open Graph, JSON-LD, `ytInitialPlayerResponse`, DOM `<video>`
- Result fields: `platform`, `platform_data`, curated images (cover / avatar / first-frame)
- Known video URLs skip the generic auto-selector

### Media download & playback
- Auto-download to `downloads/`; magic-byte validation (rejects HTML error pages)
- **ffmpeg** remux for Bilibili DASH (`.m4s` → playable `.mp4`)
- **Videos** tab — inline `<video>` player via `/downloads/...` with correct MIME types

### Saved login
- Persistent Chrome profile in `.chrome_profile/`
- Log in once (Visible mode); reuse sessions for any site
- Optional Cookie field overrides the saved profile

### Smart auto-selector
- Heuristic DOM scoring + stable CSS generation
- AI fallback (OpenAI-compatible: OpenAI, DeepSeek, Ollama)
- **Selectors** tab — method, confidence, one-click apply

### Anti-bot & networking
- System Chrome + `playwright-stealth` + fingerprint patches
- Human-like mouse/scroll; challenge-page wait; multi-strategy retry
- Proxy via UI / `SCRAPER_PROXY` / `HTTP_PROXY`; dead env proxies skipped
- **ProxyRotator** for all Sessions; **domain/ad blocking** on browser fetchers
- Port auto-select if 8000 is busy (8001+)

---

## Project structure

```
spaider_crawler/
├── app.py                 # FastAPI + SSE API + /downloads
├── scraper_core.py        # Main Playwright scrape pipeline
├── selector_engine.py     # Heuristic + AI selector discovery
├── media_downloader.py    # Image/video download, ffmpeg, MIME
├── fetcher.py             # Stealth HTTP (curl_cffi)
├── dynamic_fetcher.py     # Playwright DynamicFetcher
├── stealthy_fetcher.py    # StealthyFetcher + CF challenge flow
├── session_store.py       # Cookie / state JSON helpers
├── sessions.py            # Unified session exports
├── proxy_rotator.py       # Proxy rotation strategies
├── request_blocking.py    # Domain + ad request blocking
├── ad_domains.py          # Loads bundled tracker list
├── image_utils.py         # Image URL cleanup / junk filter
├── data/ad_domains.txt    # ~3,500 ad/tracker hosts (Peter Lowe)
├── video_platforms/       # Multi-platform video extractors
├── templates/index.html
├── static/css|js/
├── scripts/start.ps1      # Windows launcher
├── scripts/scrape_video.py
├── requirements.txt
└── .env.example
```

---

## Requirements

- Python 3.10+
- Google Chrome (optional, recommended)
- **ffmpeg** (optional, for DASH → MP4)
- **patchright** (optional, stronger `StealthyFetcher`)

---

## Installation

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

Optional stealth engine:

```bash
pip install patchright
python -m patchright install chrome
```

Copy `.env.example` → `.env` if needed:

```env
OPENAI_API_KEY=sk-your-key-here
# SCRAPER_PROXY=http://127.0.0.1:7890
# BILI_COOKIE=SESSDATA=...; bili_jct=...
```

---

## Quickstart

**Windows:**

```powershell
.\scripts\start.ps1
```

**Or:**

```bash
python app.py
# python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/` (or the port printed). Header should show **v1.3.0**.

### Bilibili example

| Option | Value |
|--------|-------|
| Remember login | On (Visible, first run) |
| JS wait | `8000` ms |
| Auto-scroll / system Chrome / Auto-download | On |
| Smart auto-selector | Off (auto for video sites) |

### YouTube example

Same as above; use Visible mode for stream URLs. Set Proxy only if your network needs it.

### CLI

```bash
python scripts/scrape_video.py "https://www.bilibili.com/video/BV1yk7X6KEz4" output.json
```

---

## Web UI options

| Option | Description |
|--------|-------------|
| Text / Comment selector | CSS; empty = auto |
| Remember login | `.chrome_profile/` persistent session |
| Cookie | Optional override (`k=v; ...`) |
| Proxy | `http://` / `socks5://`; empty = direct |
| JS wait (ms) | 500–30000 after load |
| Browser mode | Auto / Headless / Visible |
| Max retries | 0–4 alternate strategies |
| Use system Chrome | Prefer installed Chrome |
| Simulate human | Mouse + scroll noise |
| Block resources | Skip images/fonts (may look bot-like) |
| Auto-download | Save media; play in Videos tab |
| Smart auto-selector / AI | Discover CSS; AI needs API key |

**Protected sites:** Remember login + Visible + system Chrome.  
**Video sites:** Leave selectors empty; enable Auto-download.

---

## Programmatic fetchers

### Tier 1 — `Fetcher` (HTTP)

```python
from fetcher import Fetcher, FetcherSession

r = Fetcher.get("https://example.com", stealthy_headers=True, impersonate="chrome")
r = Fetcher.get("https://http3-capable.example", http3=True)

with FetcherSession(session_file=".sessions/api.json") as s:
    s.get("https://example.com/login")
    s.state["user"] = "alice"
    s.post("https://example.com/api", json_body={"q": 1})
```

Uses `curl_cffi` for TLS/JA3 impersonation; falls back to `urllib` if missing.

### Tier 2 — `DynamicFetcher` (browser)

```python
from dynamic_fetcher import DynamicFetcher, DynamicSession

r = DynamicFetcher.fetch(
    "https://spa.example.com",
    real_chrome=True,
    network_idle=True,
    wait=1500,
    wait_selector="main",
    block_ads=True,
    blocked_domains={"metrics.vendor.com"},
)

with DynamicSession(real_chrome=True, session_file=".sessions/web.json") as s:
    s.fetch("https://example.com")
    s.fetch("https://example.com/account")  # cookies persist
```

### Tier 3 — `StealthyFetcher` (anti-bot)

```python
from stealthy_fetcher import StealthyFetcher, StealthySession

r = StealthyFetcher.fetch(
    "https://protected.example",
    solve_cloudflare=True,
    hide_canvas=True,
    block_webrtc=True,
    block_ads=True,
    real_chrome=True,
    timeout=60000,
)
```

> CF flow automates the challenge UI in a realistic browser — it does not cryptographically break CAPTCHAs.

### Sessions, proxy rotation, blocking

```python
from sessions import FetcherSession, DynamicSession, StealthySession
from sessions import ProxyRotator, random_rotation

# Shared API: get/set/clear cookies, save/load/snapshot/restore, state={}
with FetcherSession(session_file=".sessions/api.json") as s:
    s.set_cookies({"token": "x"}, url="https://example.com")
    s.save()

rotator = ProxyRotator([
    "http://1.2.3.4:8080",
    {"server": "http://5.6.7.8:8080", "username": "u", "password": "p"},
])
with FetcherSession(proxy_rotator=rotator) as s:
    s.get("https://example.com/a")              # #1
    s.get("https://example.com/b")              # #2
    s.get("https://example.com/c", proxy=None)  # direct this call
    print(s.last_proxy)

# Random / custom strategies also supported:
# ProxyRotator(proxies, strategy=random_rotation)
```

Do not pass both static `proxy=` and `proxy_rotator=` on the same session. Per-request `proxy=` always wins.

---

## API reference

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "1.3.0",
  "features": [
    "video_platforms", "wbi_comments", "download_media", "saved_profile",
    "stealth_fetcher", "dynamic_fetcher", "stealthy_fetcher",
    "session_manager", "proxy_rotator", "request_blocking"
  ]
}
```

### `GET /downloads/{path}`

Serves downloaded media with correct MIME types (e.g. `video/mp4`).

### `POST /api/scrape`

SSE stream. Body fields:

| Field | Default | Description |
|-------|---------|-------------|
| `url` | *required* | Target URL |
| `text_selector` / `comment_selector` | `""` | CSS overrides |
| `cookie` | `""` | Auth cookie string |
| `proxy` | `""` | Proxy URL |
| `wait_ms` | `3500` | JS settle (500–30000) |
| `scroll` | `true` | Auto-scroll |
| `use_chrome` | `true` | System Chrome |
| `headless` | `"auto"` | `auto` / `hidden` / `visible` |
| `max_retries` | `2` | 0–4 |
| `simulate_human` | `true` | Mouse/scroll |
| `block_resources` | `false` | Skip images/fonts |
| `auto_selector` / `auto_selector_ai` | `true` | Smart selectors |
| `ai_api_key` / `ai_base_url` / `ai_model` | `""` | LLM overrides |
| `download_media` | `true` | Save to `downloads/` |
| `use_saved_profile` | `true` | `.chrome_profile/` |

**SSE events:** `log`, `ping`, `done`, `error`. Validation errors → HTTP `422`.

```python
import json, urllib.request
body = json.dumps({
    "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
    "wait_ms": 8000, "use_chrome": True,
    "download_media": True, "use_saved_profile": True,
    "auto_selector": False,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/scrape", data=body,
    headers={"Content-Type": "application/json"}, method="POST",
)
with urllib.request.urlopen(req, timeout=300) as resp:
    for line in resp.read().decode().splitlines():
        if line.startswith("data: "):
            print(line[6:])
```

---

## API output (`done`)

```json
{
  "url": "https://www.bilibili.com/video/BV1yk7X6KEz4",
  "title": "Video title",
  "platform": "bilibili",
  "text_paragraphs": ["播放 ...", "UP主: ..."],
  "comments": ["user: comment"],
  "videos": ["/downloads/.../videos/video.mp4"],
  "images": ["https://.../cover.jpg"],
  "meta": { "video_platform": "bilibili", "bilibili_bvid": "BV1yk7X6KEz4" },
  "platform_data": {
    "platform": "bilibili",
    "video_streams": [{ "url": "...", "width": 1920 }],
    "audio_streams": [{ "url": "..." }],
    "comments": ["user: comment"]
  },
  "downloads": {
    "dir": ".../downloads/...",
    "web_dir": "/downloads/...",
    "images": [{ "web_path": "/downloads/.../images/001.jpg" }],
    "videos": [{ "web_path": "/downloads/.../videos/video.mp4", "playable": true, "mime": "video/mp4" }]
  }
}
```

Tabs: Text · Comments · **Videos** · Images · **Selectors** · Metadata · Log.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Playwright won't launch | `python -m playwright install chromium` |
| Port 8000 busy | Use `.\scripts\start.ps1` or the port shown (8001+) |
| `ERR_CONNECTION_CLOSED` | Clear dead `HTTP_PROXY`; try Visible + system Chrome |
| Cloudflare / WAF | Visible + Chrome + proxy; or `StealthyFetcher(solve_cloudflare=True)` |
| Empty SPA content | Increase JS wait; enable auto-scroll |
| CAPTCHA | Visible + Remember login; solve once manually |
| Video won't play | Auto-download on; install **ffmpeg** for DASH |
| Download is HTML | Need login / stream expired — Visible + saved profile |
| Few Bilibili comments | Remember login or `BILI_COOKIE` |
| Profile locked | Close other Chrome/scraper using `.chrome_profile/` |
| Patchright missing | Optional: `pip install patchright && python -m patchright install chrome` |

---

## Notes & responsible use

- Only scrape content you are authorized to access. Respect `robots.txt` and site terms.
- For learning and legitimate research — not a universal CAPTCHA/WAF bypass.
- Use your own cookies/sessions; never misuse others’ credentials.
- Video streams may be copyrighted — use data responsibly.

---

## License

[MIT](LICENSE) © 2026 Nameless
