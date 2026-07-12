# 🕷 Modern Web Scraper


This repository contains a Playwright-powered web scraper with a web user interface served by FastAPI (access at `http://localhost:8000/`) implemented in `app.py` + `templates/` + `static/`.

The core pipeline (`scraper_core.py`) launches a real Chromium browser (via Playwright), renders the page, and extracts structured data (body text, comments, video links, images, and meta tags).


![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

---

![Screenshot](image.png)


## Features

- Real Chromium rendering (Playwright) — executes JavaScript and supports SPAs
- Body text auto-detection + optional CSS selector override
- Heuristic comment extraction + optional CSS selector override
- Video and image link extraction
- Metadata extraction from `<meta>` tags
- Cookie injection to carry session state
- Lightweight anti-detection patches (built-in + optional `playwright-stealth`)
- Auto-scroll to trigger lazy-loaded content
- Export results to TXT or JSON

---

## Requirements

- Python 3.10+
- `pip` and a writable Python environment
- For the GUI: a display environment (Tkinter) — on headless servers prefer the web UI

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

3. Install Playwright browser binaries (required for Playwright to run):

```bash
python -m playwright install chromium
```

Notes:
- `playwright-stealth` is optional — the code falls back to a small built-in patch when it's not available.
- On Linux, you may need system packages for Chromium to run (fonts, libgtk, etc.).

---

## Quickstart

After installing requirements and Playwright binaries, start the web UI:

```bash
python app.py
# or
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser at `http://127.0.0.1:8000/` and enter a URL to scrape.

---

## Optional: Docker (experimental)

You can run the web UI inside a container. This repo does not include an official Dockerfile, but a minimal example:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Notes for Docker:
- Use a non-root user and ensure required system libraries are installed for Chromium (fonts, GTK, etc.).
- Containers running Playwright may need extra flags or capabilities depending on the host environment.

---

## Run the Web UI (FastAPI)

Start the server (development):

```bash
python app.py
# or with uvicorn directly
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/` in your browser. The web UI mirrors the desktop GUI: enter a URL, configure optional selectors/cookie/wait time/scroll, and click `Start Scrape`.

You can also call the API programmatically (`POST /api/scrape`) — it returns a Server-Sent Events (SSE) stream of logs and a final `done` event containing the JSON result.

Example (PowerShell):

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/scrape -Method Post -Body '{"url":"https://example.com","text_selector":"","comment_selector":"","cookie":"","wait_ms":2500,"scroll":true}' -ContentType "application/json"
```

Or save the response stream to a file:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/api/scrape -Method Post -Body (Get-Content payload.json -Raw) -ContentType "application/json" -OutFile sse_response.txt
```

---

## Desktop GUI Removed

The original Tkinter-based desktop GUI (`spider_gui.py`) has been removed from this repository. Use the FastAPI web UI (`app.py`) instead by following the "Run the Web UI (FastAPI)" instructions above.

---

## API Output

After a successful scrape the pipeline returns a JSON object similar to:

```json
{
  "url": "https://example.com",
  "title": "Example Domain",
  "text_paragraphs": ["Example Domain This domain is for use in documentation examples..."],
  "comments": [],
  "videos": [],
  "images": [],
  "meta": { "viewport": "width=device-width, initial-scale=1" }
}
```

When using the web UI, the results are displayed across tabs (Text / Comments / Videos / Images / Meta / Log) and can be exported to TXT or JSON.

---

## Notes & Responsible Use

- Only scrape content you are authorized to access. Respect `robots.txt` and website terms of service.
- This tool is for learning and limited, legitimate uses — it is not intended to bypass strong anti-bot protections or CAPTCHAs.
- Use the `cookie` option only to carry your own session state; do not use others' credentials.

---

## Troubleshooting

- If Playwright fails to launch, ensure the browser binaries were installed with `python -m playwright install chromium`.
- If you get frequent 500 errors, check for competing processes on port 8000 (use `netstat -ano | findstr :8000` on Windows) and ensure only one server instance is running.
- On headless servers, prefer the API/web UI usage and avoid starting the Tkinter GUI.

---

## License

This project is open-sourced under the MIT License. See `LICENSE`.

---

If you want, I can also:

- Commit these README changes to git, or
- Translate `README.md` into Chinese or another language.