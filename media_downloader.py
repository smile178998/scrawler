#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download scraped images and videos to local disk."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from fetcher import FetchError, fetch_bytes
from image_utils import normalize_image_url, strip_bilibili_resize

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


VIDEO_EXTS = (".mp4", ".webm", ".m4v", ".mov", ".mkv", ".m4s", ".ts")
PLAYABLE_EXTS = (".mp4", ".webm", ".m4v", ".mov", ".mkv")

MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}


def _mime_for(path: Path) -> str:
    return MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")


def _is_html_or_text(data: bytes) -> bool:
    head = data[:512].lstrip()
    lower = head.lower()
    return (
        head.startswith(b"<")
        or head.startswith(b"{")
        or b"<html" in lower
        or b"<!doctype" in lower
    )


def _is_video_bytes(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if b"ftyp" in data[:16]:
        return True
    if data[:4] == b"\x1aE\xdf\xa3":
        return True
    if data[:4] == b"RIFF" and b"AVI" in data[:16]:
        return True
    if data[0:1] == b"\x47":  # MPEG-TS sync byte
        return True
    return False


def _guess_ext(url: str, content_type: str = "", default: str = ".mp4") -> str:
    path = url.split("?", 1)[0]
    name = path.rsplit("/", 1)[-1]
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1].split("@")[0].lower()
        if ext in VIDEO_EXTS or ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return ext
    ct = (content_type or "").lower()
    if "webm" in ct:
        return ".webm"
    if "mp4" in ct or "mpeg" in ct:
        return ".mp4"
    if "quicktime" in ct:
        return ".mov"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if ".m4s" in url.lower():
        return ".m4s"
    return default


def _sniff_video_ext(data: bytes, content_type: str = "") -> str:
    head = data[:32]
    if b"ftyp" in head[:16]:
        return ".mp4"
    if head[:4] == b"\x1aE\xdf\xa3":
        return ".webm"
    if head[:4] == b"RIFF" and b"AVI " in head:
        return ".avi"
    ct = (content_type or "").lower()
    if "webm" in ct:
        return ".webm"
    if "mp4" in ct or "mpeg" in ct:
        return ".mp4"
    return ".mp4"


def _is_downloadable_video_url(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u.startswith(("http://", "https://")):
        return False
    if u.startswith("blob:") or "javascript:" in u:
        return False
    if ".m3u8" in u or ".mpd" in u:
        return False
    return True


def _video_url_score(url: str) -> int:
    u = url.lower()
    score = 0
    if "googlevideo.com" in u or "videoplayback" in u:
        score += 60
    if any(h in u for h in ("mime=video", "type=video")):
        score += 50
    if any(ext in u for ext in (".mp4", ".webm", ".m4v", ".mov")):
        score += 45
    if "video" in u or "stream" in u:
        score += 15
    if "audio" in u or "mime=audio" in u:
        score -= 30
    return score


def _try_ffmpeg_to_mp4(path: Path, log: LogFn) -> Path | None:
    """Remux m4s / mislabeled fragments into a browser-playable MP4."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        if path.suffix.lower() == ".m4s":
            log("[Download] .m4s needs ffmpeg to play in browser — install ffmpeg")
        return path if path.suffix.lower() in PLAYABLE_EXTS else None

    out = path.with_name(f"{path.stem}_play.mp4")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        if out.stat().st_size > 0:
            if path != out and path.exists():
                path.unlink(missing_ok=True)
            log(f"[Download] Ready to play: {out.name}")
            return out
    except Exception as exc:
        log(f"[Download] ffmpeg remux failed: {exc}")
    return path if path.suffix.lower() in PLAYABLE_EXTS else None


def _finalize_saved_video(path: Path, log: LogFn) -> Path | None:
    """Validate bytes, fix extension, remux to MP4 when needed."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        log(f"[Download] Cannot read {path.name}: {exc}")
        return None

    if _is_html_or_text(data):
        log(
            f"[Download] Skipped {path.name} — server returned HTML "
            "(expired URL or login required)."
        )
        path.unlink(missing_ok=True)
        return None

    if not _is_video_bytes(data):
        log(f"[Download] Skipped {path.name} — not a valid video file.")
        path.unlink(missing_ok=True)
        return None

    ext = _sniff_video_ext(data, "")
    if path.suffix.lower() != ext:
        target = path.with_suffix(ext)
        path.rename(target)
        path = target
        data = path.read_bytes()

    if path.suffix.lower() in (".m4s", ".ts", ".bin"):
        return _try_ffmpeg_to_mp4(path, log)

    if path.suffix.lower() not in PLAYABLE_EXTS:
        target = path.with_suffix(".mp4")
        path.rename(target)
        return target

    return path


def _ensure_playable_video(path: Path, log: LogFn) -> Path | None:
    return _finalize_saved_video(path, log)


def _headers_for(url: str, referer: str = "") -> dict[str, str]:
    headers = {"User-Agent": DEFAULT_UA}
    if referer:
        headers["Referer"] = referer
    elif "youtube.com" in url or "googlevideo.com" in url or "youtu.be" in url:
        headers["Referer"] = "https://www.youtube.com/"
    elif "bilibili" in url or "hdslb.com" in url or "akamaized.net" in url:
        headers["Referer"] = "https://www.bilibili.com/"
    elif "vimeo.com" in url:
        headers["Referer"] = "https://vimeo.com/"
    return headers


def _is_image_bytes(data: bytes) -> bool:
    if len(data) < 8:
        return False
    if data[:3] == b"\xff\xd8\xff":
        return True  # JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def _download_url(
    url: str,
    dest: Path,
    headers: dict[str, str],
    log: LogFn,
    timeout: int = 120,
    *,
    expect: str = "video",
) -> Path | None:
    """Download a URL via stealth Fetcher.

    ``expect`` is ``"video"`` or ``"image"`` — controls content validation.
    """
    url = _normalize_url(url)
    if not url.startswith(("http://", "https://")):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        data, content_type, status = fetch_bytes(
            url,
            headers=headers,
            timeout=float(timeout),
            impersonate="chrome",
            http3=False,
            referer=headers.get("Referer"),
        )
        if status >= 400:
            log(f"[Download] Failed — HTTP {status}")
            return None

        if _is_html_or_text(data):
            log(f"[Download] Skipped — response is HTML/text, not media.")
            return None

        if expect == "video":
            if not _is_video_bytes(data):
                log(f"[Download] Skipped — downloaded content is not a video stream.")
                return None
            ext = _sniff_video_ext(data, content_type)
            dest = dest.with_suffix(ext)
            dest.write_bytes(data)
            final = _finalize_saved_video(dest, log)
            if not final:
                return None
            log(f"[Download] Saved {final.name} ({final.stat().st_size:,} bytes)")
            return final

        # image
        if not _is_image_bytes(data):
            log(f"[Download] Skipped — downloaded content is not an image.")
            return None
        ext = _guess_ext(url, content_type, default=".jpg")
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = ".jpg"
        dest = dest.with_suffix(ext)
        dest.write_bytes(data)
        log(f"[Download] Saved {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    except (FetchError, OSError, Exception) as exc:
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
    playable = file_path.suffix.lower() in PLAYABLE_EXTS
    return {
        "url": url,
        "path": str(file_path),
        "filename": file_path.name,
        "web_path": f"/downloads/{rel}",
        "mime": _mime_for(file_path),
        "playable": playable,
        **extra,
    }


def _download_platform_video(
    platform_data: dict,
    vid_dir: Path,
    base_dir: Path,
    title: str,
    referer: str,
    log: LogFn,
) -> list[dict]:
    video_streams = platform_data.get("video_streams") or []
    audio_streams = platform_data.get("audio_streams") or []
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
                return [_entry(base_dir, merged_path, v_stream["url"], type="merged_mp4", playable=True)]

    ext = v_file.suffix or ".m4s"
    final = vid_dir / f"{_safe_name(title, 40)}{ext}"
    if v_file != final:
        v_file.rename(final)
        v_file = final
    v_file = _finalize_saved_video(v_file, log)
    if not v_file:
        return []
    return [_entry(base_dir, v_file, v_stream["url"], type="video_only", playable=True)]


def _download_generic_videos(
    urls: list[str],
    vid_dir: Path,
    base_dir: Path,
    referer: str,
    log: LogFn,
) -> list[dict]:
    saved: list[dict] = []
    candidates = sorted(
        {_normalize_url(raw) for raw in urls if _is_downloadable_video_url(raw)},
        key=_video_url_score,
        reverse=True,
    )
    for i, url in enumerate(candidates, 1):
        if url.lower().endswith(".m4s"):
            continue
        dest = _download_url(
            url,
            vid_dir / f"video_{i:02d}.mp4",
            _headers_for(url, referer),
            log,
            timeout=300,
        )
        if dest:
            entry = _entry(base_dir, dest, url, playable=True)
            if entry.get("playable"):
                saved.append(entry)
            else:
                log(f"[Download] {dest.name} saved but not browser-playable.")
    return saved


def _filter_display_videos(videos: list[str], downloaded: list[dict]) -> list[str]:
    """Prefer local playable paths; drop blob and duplicate remote URLs."""
    if downloaded:
        return [d["web_path"] for d in downloaded if d.get("web_path")]
    return [v for v in videos if _is_downloadable_video_url(v)]


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
    platform_data = result.get("platform_data") or {}

    downloaded_images: list[dict] = []
    for i, raw in enumerate(result.get("images") or [], 1):
        url = strip_bilibili_resize(normalize_image_url(raw))
        if not url.startswith(("http://", "https://")):
            continue
        dest = _download_url(
            url,
            img_dir / f"{i:03d}",
            _headers_for(url, referer),
            log,
            timeout=90,
            expect="image",
        )
        if dest:
            downloaded_images.append(_entry(root, dest, url))

    if platform_data.get("video_streams"):
        downloaded_videos = _download_platform_video(
            platform_data, vid_dir, root, title, referer, log
        )
    else:
        stream_urls = [
            s.get("url")
            for s in (platform_data.get("video_streams") or [])
            if s.get("url")
        ]
        all_urls = list(dict.fromkeys((result.get("videos") or []) + stream_urls))
        downloaded_videos = _download_generic_videos(
            all_urls, vid_dir, root, referer, log
        )

    result["videos"] = _filter_display_videos(result.get("videos") or [], downloaded_videos)
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
