# Modern Web Scraper 

A desktop web scraping tool powered by **Playwright (real Chromium engine)**, with a clean, light-themed Tkinter GUI. Unlike traditional `requests` + `BeautifulSoup` scrapers, this tool renders pages through an actual browser, so it can handle JavaScript-heavy SPAs, lazy-loaded content, and more.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

![Screenshot](image.png)

## ✨ Features

- 🌐 **Real browser engine** — built on Playwright + Chromium, fully executes JavaScript, works with single-page applications (SPAs)
- 📄 **Body text extraction** — built-in selectors for common site layouts (blogs, tech articles, docs, etc.), with automatic content-region detection and support for custom CSS selectors
- 💬 **Comment extraction** — heuristic keyword-based detection of comment sections, overridable with a custom selector
- 🎬 **Video link extraction** — detects `<video>` tags and common video-platform iframe embeds
- 🖼 **Image link extraction** — automatically collects image resources on the page
- 🍪 **Cookie support** — inject cookies to get past certain anti-bot checks (e.g. 403 / 521 errors)
- 📜 **Auto-scroll** — optional, triggers lazy-loaded content before scraping
- 💾 **Export results** — save output as TXT or JSON
- 🎨 **Clean GUI** — Notion / Linear–inspired light interface with a live log panel

## 📦 Installation

### Requirements
- Python 3.9+
- Desktop environment on Windows / macOS / Linux (Tkinter needs a display)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

# 2. Install dependencies
pip install playwright beautifulsoup4 lxml

# 3. Install the Chromium browser used by Playwright
python -m playwright install chromium
```

> 💡 Tkinter usually ships with Python. On Linux, if it's missing, install it with `sudo apt install python3-tk`.

## 🚀 Usage

```bash
python scraper.py
```

1. Enter the target URL in the **Target URL** field, then press Enter or click **▶ Scrape**.
2. Optionally configure options under **Advanced Options**:
   - **Text selector** — CSS selector for the article body (leave blank for auto-detection)
   - **Comment selector** — CSS selector for comments (leave blank for heuristic keyword detection)
   - **Cookie** — format as `key1=value1; key2=value2`, used to bypass login walls or anti-bot checks
   - **JS wait (ms)** — how long to wait after page load for JavaScript to finish rendering; increase for slow SPAs
   - **Auto-scroll** — automatically scrolls the page to trigger lazy-loaded content
3. Once scraping finishes, review results in the tabs:
   - 📄 Body Text · 💬 Comments · 🎬 Videos · 🖼 Images · 🏷 Meta / JSON · 📡 Log
4. Click **💾 Save TXT** / **💾 Save JSON** at the bottom to export results.

## ⚠️ Usage Notice

- Respect each target site's `robots.txt` and terms of service. Don't use this tool for high-volume, high-frequency scraping or to harvest copyrighted content commercially.
- Do not use it to scrape pages that require authentication, or that involve private or sensitive personal information, without proper authorization.
- The cookie feature should only be used for content you are personally authorized to access.
- This tool is intended for learning and legitimate personal use only. Users are solely responsible for any legal consequences arising from misuse.

## 🛠 Tech Stack

| Component | Purpose |
|-----------|---------|
| [Playwright](https://playwright.dev/python/) | Headless browser automation, JS-rendered pages |
| [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) + `lxml` | HTML parsing and content extraction |
| Tkinter | Desktop GUI |

## 📄 License

This project is open-sourced under the [MIT License](LICENSE). Feel free to use and modify it.

## 🤝 Contributing

Issues and pull requests are welcome! If you have better content-extraction rules or ideas for supporting more sites, contributions are appreciated.
