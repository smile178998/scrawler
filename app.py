#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web Scraper — FastAPI web application."""

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from scraper_core import run_pipeline

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Modern Web Scraper", version="1.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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
    return {"status": "ok"}


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
        run_pipeline(
            url,
            req.text_selector.strip(),
            req.comment_selector.strip(),
            req.cookie.strip(),
            req.wait_ms,
            req.scroll,
            log_q,
            proxy=req.proxy.strip(),
            use_chrome=req.use_chrome,
            headless=req.headless,
            max_retries=req.max_retries,
            simulate_human=req.simulate_human,
            block_resources=req.block_resources,
        )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def event_stream():
        while thread.is_alive() or not log_q.empty():
            try:
                kind, payload = log_q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue

            data = json.dumps({"type": kind, "data": payload}, ensure_ascii=False)
            yield f"data: {data}\n\n"
            if kind in ("done", "error"):
                return

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
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
