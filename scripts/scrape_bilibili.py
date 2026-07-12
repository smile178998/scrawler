#!/usr/bin/env python3
"""Scrape a Bilibili video and save JSON. Cookie via BILI_COOKIE env var."""
from __future__ import annotations

import json
import os
import queue
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper_core import run_pipeline  # noqa: E402


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.bilibili.com/video/BV1yk7X6KEz4"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "output_bilibili.json"
    cookie = os.environ.get("BILI_COOKIE", "").strip()

    if not cookie:
        print("Set BILI_COOKIE environment variable with your login cookie.", file=sys.stderr)
        return 1

    log_q: queue.Queue = queue.Queue()

    def drain():
        while not log_q.empty():
            kind, payload = log_q.get_nowait()
            if kind == "log":
                print(payload)

    run_pipeline(
        url,
        "",
        "",
        cookie,
        8000,
        True,
        log_q,
        use_chrome=True,
        headless="auto",
        max_retries=2,
        simulate_human=True,
        auto_selector=False,
        auto_selector_ai=False,
        download_media=True,
    )

    result = None
    error = None
    while not log_q.empty():
        kind, payload = log_q.get_nowait()
        if kind == "log":
            print(payload)
        elif kind == "done":
            result = payload
        elif kind == "error":
            error = payload

    if error:
        print("ERROR:", error, file=sys.stderr)
        return 1
    if not result:
        print("No result.", file=sys.stderr)
        return 1

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    bili = result.get("bilibili") or {}
    print(f"\nSaved: {out}")
    print(f"platform={result.get('platform')} comments={len(result.get('comments') or [])} "
          f"videos={len(result.get('videos') or [])} images={len(result.get('images') or [])}")
    if bili:
        print(f"title={bili.get('title')} total_comments~{bili.get('comment_total')}")
    dl = result.get("downloads") or {}
    if dl:
        print(f"downloads={dl.get('dir')}")
        for v in dl.get("videos") or []:
            print(f"  video: {v.get('path')}")
        for img in dl.get("images") or []:
            print(f"  image: {img.get('path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
