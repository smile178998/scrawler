#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web Scraper — FastAPI web application."""

import asyncio
import json
import os
import queue
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from scraper_core import run_pipeline
from media_downloader import DOWNLOADS_ROOT, MIME_BY_EXT

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent

DOWNLOADS_ROOT.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Modern Web Scraper", version="1.3.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/downloads/{file_path:path}")
async def serve_download(file_path: str):
    """Serve downloaded media with correct video MIME types for in-browser playback."""
    root = DOWNLOADS_ROOT.resolve()
    full = (root / file_path).resolve()
    if not str(full).startswith(str(root)) or not full.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = MIME_BY_EXT.get(full.suffix.lower())
    if not media_type:
        media_type = "image/jpeg" if full.suffix.lower() in (".jpg", ".jpeg") else "application/octet-stream"
    return FileResponse(full, media_type=media_type, filename=full.name)


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=1)
    text_selector: str = ""
    comment_selector: str = ""
    cookie: str = ""
    wait_ms: int = Field(default=3500, ge=500, le=30000)
    scroll: bool = True
    proxy: str = ""
    use_chrome: bool = True
    headless: Literal["auto", "hidden", "visible"] = "auto"
    max_retries: int = Field(default=2, ge=0, le=4)
    simulate_human: bool = True
    block_resources: bool = False
    auto_selector: bool = True
    auto_selector_ai: bool = True
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    download_media: bool = True
    use_saved_profile: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("URL is required")
        parsed = urlparse(value if "://" in value else f"https://{value}")
        if not parsed.netloc:
            raise ValueError("Invalid URL format")
        return value


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    messages = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", []) if part != "body")
        messages.append(f"{loc}: {err.get('msg', 'invalid value')}" if loc else err.get("msg", "invalid value"))
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request", "details": messages},
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(
        (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "1.3.0",
        "features": [
            "video_platforms",
            "wbi_comments",
            "download_media",
            "saved_profile",
            "stealth_fetcher",
            "dynamic_fetcher",
        ],
    }


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not urlparse(url).scheme:
        url = "https://" + url
    return url


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
    url = _normalize_url(req.url)
    log_q: queue.Queue = queue.Queue()

    def worker():
        cookie = req.cookie.strip() or os.getenv("BILI_COOKIE", "").strip()
        run_pipeline(
            url,
            req.text_selector.strip(),
            req.comment_selector.strip(),
            cookie,
            req.wait_ms,
            req.scroll,
            log_q,
            proxy=req.proxy.strip(),
            use_chrome=req.use_chrome,
            headless=req.headless,
            max_retries=req.max_retries,
            simulate_human=req.simulate_human,
            block_resources=req.block_resources,
            auto_selector=req.auto_selector,
            auto_selector_ai=req.auto_selector_ai,
            ai_api_key=req.ai_api_key.strip(),
            ai_base_url=req.ai_base_url.strip(),
            ai_model=req.ai_model.strip(),
            download_media=req.download_media,
            use_saved_profile=req.use_saved_profile,
        )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def event_stream():
        import time

        start = time.monotonic()
        while thread.is_alive() or not log_q.empty():
            emitted = False
            try:
                while True:
                    kind, payload = log_q.get_nowait()
                    emitted = True
                    data = json.dumps({"type": kind, "data": payload}, ensure_ascii=False)
                    yield f"data: {data}\n\n"
                    if kind in ("done", "error"):
                        return
            except queue.Empty:
                pass

            if thread.is_alive() and not emitted:
                elapsed = int(time.monotonic() - start)
                ping = json.dumps(
                    {"type": "ping", "data": {"elapsed": elapsed}},
                    ensure_ascii=False,
                )
                yield f"data: {ping}\n\n"
                await asyncio.sleep(1.0)
                continue

            if not thread.is_alive():
                break
            await asyncio.sleep(0.05)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import socket

    import uvicorn

    def _pick_port(preferred: int = 8000, span: int = 10) -> int:
        for port in range(preferred, preferred + span + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("0.0.0.0", port))
                    return port
                except OSError:
                    continue
        raise SystemExit(
            f"No free port between {preferred} and {preferred + span}. "
            "Close other python/uvicorn windows or run: "
            'Get-NetTCPConnection -LocalPort 8000 | % { Stop-Process -Id $_.OwningProcess -Force }'
        )

    env_port = os.getenv("PORT", "").strip()
    port = int(env_port) if env_port.isdigit() else _pick_port()
    if port != 8000:
        print(f"[Info] Port 8000 is busy — using http://127.0.0.1:{port}")
        print("[Warn] Close other python app.py windows, or run: .\\scripts\\start.ps1")
    else:
        print(f"[Info] Server ready at http://127.0.0.1:{port}")
    print(f"[Info] Open this URL in your browser ↑  (v1.3.0)")

    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
