#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download scraped images and videos to local disk."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable

LogFn = Callable[[str], None]

DOWNLOADS_ROOT = Path(__file__).resolve().parent / "downloads"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _safe_name(text: str, max_len: int = 60) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (text or "").strip())
    text = re.sub(r"\s+", " ", text)
    return text[:max_len].strip("._ ") or "scrape"


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        return "https:" + url
    return url


def _guess_ext(url: str, content_type: str = "", default: str = ".bin") -> str:
    path = url.split("?", 1)[0]
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].split("@")[0].lower()
        if 2 < len(ext) <= 6:
            return ext
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "mp4" in ct:
        return ".mp4"
    if ".m4s" in url.lower():
        return ".m4s"
    return default


def _headers_for(url: str, referer: str = "") -> dict[str, str]:
    headers = {"User-Agent": DEFAULT_UA}
    if referer:
        headers["Referer"] = referer
    elif "bilibili" in url or "hdslb.com" in url or "akamaized.net" in url:
        headers["Referer"] = "https://www.bilibili.com/"
    return headers


def _download_url(
    url: str,
    dest: Path,
    headers: dict[str, str],
    log: LogFn,
    timeout: int = 120,
) -> Path | None:
    url = _normalize_url(url)
    if not url.startswith(("http://", "https://")):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
        if not dest.suffix or dest.suffix == ".bin":
            dest = dest.with_suffix(_guess_ext(url, content_type, ".bin"))
        dest.write_bytes(data)
        log(f"[Download] Saved {dest.name} ({len(data):,} bytes)")
        return dest
    except Exception as exc:
        log(f"[Download] Failed — {exc}")
        return None


def _pick_best_stream(streams: list[dict]) -> dict | None:
    if not streams:
        return None
    return max(streams, key=lambda s: int(s.get("bandwidth") or 0))


def _try_ffmpeg_merge(
    video_path: Path, audio_path: Path, out_path: Path, log: LogFn
) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log("[Download] ffmpeg not found — video and audio saved separately.")
        return None
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        log(f"[Download] Merged MP4: {out_path.name}")
        return out_path
    except Exception as exc:
        log(f"[Download] ffmpeg merge failed: {exc}")
        return None


def _entry(base_dir: Path, file_path: Path, url: str, **extra) -> dict:
    rel = file_path.relative_to(base_dir).as_posix()
    return {
        "url": url,
        "path": str(file_path),
        "web_path": f"/downloads/{rel}",
        **extra,
    }


def _download_bilibili_video(
    bili: dict,
    vid_dir: Path,
    base_dir: Path,
    title: str,
    referer: str,
    log: LogFn,
) -> list[dict]:
    video_streams = bili.get("video_streams") or []
    audio_streams = bili.get("audio_streams") or []
    if not video_streams:
        return []

    v_stream = _pick_best_stream(video_streams)
    if not v_stream or not v_stream.get("url"):
        return []

    v_file = _download_url(
        v_stream["url"],
        vid_dir / "video_track.m4s",
        _headers_for(v_stream["url"], referer),
        log,
        timeout=300,
    )
    if not v_file:
        return []

    a_stream = _pick_best_stream(audio_streams)
    if a_stream and a_stream.get("url"):
        a_file = _download_url(
            a_stream["url"],
            vid_dir / "audio_track.m4s",
            _headers_for(a_stream["url"], referer),
            log,
            timeout=300,
        )
        if a_file:
            merged = vid_dir / f"{_safe_name(title, 40)}.mp4"
            merged_path = _try_ffmpeg_merge(v_file, a_file, merged, log)
            if merged_path:
                return [_entry(base_dir, merged_path, v_stream["url"], type="merged_mp4")]

    # Single stream (durl / video-only) or merge unavailable
    ext = v_file.suffix or ".m4s"
    final = vid_dir / f"{_safe_name(title, 40)}{ext}"
    if v_file != final:
        v_file.rename(final)
        v_file = final
    return [_entry(base_dir, v_file, v_stream["url"], type="video_only")]


def _download_generic_videos(
    urls: list[str],
    vid_dir: Path,
    base_dir: Path,
    referer: str,
    log: LogFn,
) -> list[dict]:
    saved: list[dict] = []
    for i, raw in enumerate(urls, 1):
        url = _normalize_url(raw)
        if not url.startswith(("http://", "https://")) or url.startswith("blob:"):
            continue
        if url.lower().endswith(".m4s"):
            continue
        dest = _download_url(
            url,
            vid_dir / f"video_{i}",
            _headers_for(url, referer),
            log,
            timeout=300,
        )
        if dest:
            saved.append(_entry(base_dir, dest, url))
    return saved


def download_media(
    result: dict,
    log: LogFn,
    base_dir: Path | None = None,
) -> dict:
    """Download images and videos; attach a ``downloads`` block to *result*."""
    root = base_dir or DOWNLOADS_ROOT
    root.mkdir(parents=True, exist_ok=True)

    title = result.get("title") or result.get("url") or "scrape"
    folder_name = f"{_safe_name(title)}_{int(time.time())}"
    out_dir = root / folder_name
    img_dir = out_dir / "images"
    vid_dir = out_dir / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)

    referer = _normalize_url(result.get("url", ""))
    bili = result.get("bilibili") or {}

    downloaded_images: list[dict] = []
    for i, raw in enumerate(result.get("images") or [], 1):
        url = _normalize_url(raw)
        if not url.startswith(("http://", "https://")):
            continue
        dest = _download_url(
            url,
            img_dir / f"{i:03d}",
            _headers_for(url, referer),
            log,
            timeout=90,
        )
        if dest:
            downloaded_images.append(_entry(root, dest, url))

    if bili.get("video_streams"):
        downloaded_videos = _download_bilibili_video(
            bili, vid_dir, root, title, referer, log
        )
    else:
        downloaded_videos = _download_generic_videos(
            result.get("videos") or [], vid_dir, root, referer, log
        )

    result["downloads"] = {
        "dir": str(out_dir),
        "web_dir": f"/downloads/{folder_name}",
        "images": downloaded_images,
        "videos": downloaded_videos,
    }
    log(
        f"[Download] Finished — {len(downloaded_images)} image(s), "
        f"{len(downloaded_videos)} video file(s) → {out_dir}"
    )
    return result
