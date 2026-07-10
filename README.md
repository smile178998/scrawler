# 🕷 Modern Web Scraper

A desktop web scraping tool powered by **Playwright (real Chromium engine)**, wrapped in a clean, light-themed Tkinter GUI. Unlike traditional `requests` + `BeautifulSoup` scrapers, this tool renders pages through an actual browser — so it handles JavaScript-heavy SPAs, lazy-loaded content, and dynamic sites out of the box.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

![Screenshot](image.png)

---

## ✨ Features

| | |
|---|---|
| 🌐 **Real browser engine** | Built on Playwright + Chromium — fully executes JavaScript, works with SPAs (React/Vue/etc.) |
| 📄 **Body text extraction** | Auto-detects the main content region across common site layouts, or use a custom CSS selector |
| 💬 **Comment extraction** | Heuristic keyword-based detection of comment sections, overridable with a custom selector |
| 🎬 **Video link extraction** | Detects `<video>`/`<source>` tags and common video-platform iframe embeds |
| 🖼 **Image extraction** | Collects image resources on the page (up to 50) |
| 🏷 **Metadata extraction** | Pulls all `<meta>` tags into structured output |
| 🍪 **Cookie support** | Inject a cookie string to carry your own session/login state |
| 🕵️ **Lightweight anti-detection** | Masks common automation fingerprints (`navigator.webdriver`, etc.), randomizes UA/viewport/timing — uses [`playwright-stealth`](https://pypi.org/project/playwright-stealth/) if installed, falls back to a built-in patch otherwise |
| 📜 **Auto-scroll** | Optionally scrolls the page to trigger lazy-loaded content |
| 💾 **Export** | Save results as `.txt` or structured `.json` |
| 🎨 **Clean GUI** | Notion/Linear-inspired light interface with a live log panel |

---

## 📦 Installation

**Requirements**
- Python 3.10+
- A desktop environment (Tkinter needs a display) on Windows / macOS / Linux

**Steps**

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# 2. Install dependencies
pip install playwright beautifulsoup4 lxml playwright-stealth

# 3. Install the Chromium browser used by Playwright
python -m playwright install chromium
```

> 💡 `playwright-stealth` is optional — the tool falls back to a built-in fingerprint patch if it isn't installed.
> 💡 Tkinter usually ships with Python. On Linux, if it's missing: `sudo apt install python3-tk`.

---

## 🚀 Usage

```bash
python scraper.py
```

1. Enter the target URL in **Target URL**, then press Enter or click **▶ Scrape**.
2. Optionally configure **Advanced Options**:

   | Option | Description |
   |---|---|
   | Text selector | CSS selector for the article body (blank = auto-detect) |
   | Comment selector | CSS selector for comments (blank = heuristic keyword detection) |
   | Cookie | `key1=value1; key2=value2` — carries your own session/login state |
   | JS wait (ms) | How long to wait after page load for JS to finish rendering; raise for slow SPAs |
   | Auto-scroll | Scrolls the page automatically to trigger lazy-loaded content |

3. Review results across tabs: 📄 Body Text · 💬 Comments · 🎬 Videos · 🖼 Images · 🏷 Meta/JSON · 📡 Log
4. Export with **💾 Save TXT** / **💾 Save JSON**.

---

## 🗂 Example Output (JSON)

```json
{
  "url": "https://example.com/article/123",
  "title": "Article Title",
  "text_paragraphs": ["Paragraph 1", "Paragraph 2", "..."],
  "comments": ["Comment 1", "Comment 2", "..."],
  "videos": ["https://example.com/video.mp4"],
  "images": ["https://example.com/img1.jpg"],
  "meta": { "description": "...", "og:title": "..." }
}
```

---

## ⚙️ How It Works

```
┌────────────┐    ┌───────────────────┐    ┌────────────────┐    ┌──────────────┐
│  URL +     │ →  │ Playwright renders │ →  │ BeautifulSoup   │ →  │  Structured   │
│  options   │    │ page in Chromium   │    │ parses HTML/DOM │    │  results      │
└────────────┘    └───────────────────┘    └────────────────┘    └──────────────┘
```

- **Fetch layer** (`browser_fetch`) — launches headless Chromium, injects cookies and anti-detection patches, waits for rendering, then pulls HTML, plain text, and video links
- **Parse layer** (`parse_content`) — uses BeautifulSoup + lxml to extract body text, comments, images, and metadata from the rendered HTML
- **UI layer** (`ScraperApp`) — Tkinter GUI; scraping runs on a background thread and communicates with the main thread via a queue, so the interface never freezes

---

## ⚠️ Usage Notice

- Only scrape content you're **authorized to access** — public pages, your own sites, or sites whose terms permit automated access.
- Check each target site's `robots.txt` and terms of service, and keep your request rate reasonable — don't use this for high-volume, high-frequency scraping.
- Do not use it against pages requiring authentication, or containing private/sensitive personal data, without proper authorization.
- The built-in anti-detection features only mask common automation fingerprints — they are **not** designed and should **not** be used to defeat enterprise bot-mitigation systems (Cloudflare, DataDome, PerimeterX, etc.) or CAPTCHAs.
- The cookie feature is meant only for carrying your own session state, not for accessing other people's accounts.
- Intended for learning and legitimate personal use. Users are solely responsible for any consequences arising from misuse.

---

## 🛠 Tech Stack

| Component | Purpose |
|---|---|
| [Playwright](https://playwright.dev/python/) | Headless browser automation, JS-rendered pages |
| [playwright-stealth](https://pypi.org/project/playwright-stealth/) *(optional)* | Reduces common automation fingerprints |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) + `lxml` | HTML parsing and content extraction |
| Tkinter | Desktop GUI |

---

## 📄 License

Open-sourced under the [MIT License](LICENSE). Feel free to use and modify it.

## 🤝 Contributing

Issues and pull requests are welcome — especially better content-extraction rules or support for more site layouts.