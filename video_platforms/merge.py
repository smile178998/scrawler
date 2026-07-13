#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge platform-specific video payloads into the standard scrape result."""

from __future__ import annotations

import re

from image_utils import collect_images, strip_bilibili_resize


def _stream_urls(payload: dict) -> list[str]:
    urls: list[str] = []
    for stream in payload.get("video_streams") or []:
        url = stream.get("url")
        if url and url not in urls and _is_http_url(url):
            urls.append(url)
    for stream in payload.get("audio_streams") or []:
        url = stream.get("url")
        if url and url not in urls and _is_http_url(url):
            urls.append(url)
    embed = payload.get("embed_url")
    if embed and embed not in urls and _is_http_url(embed):
        urls.append(embed)
    return urls


def _is_http_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith(("http://", "https://")) and not u.startswith("blob:")


def _curated_images(platform: str, payload: dict) -> list[str]:
    curated: list[str] = []
    cover = payload.get("cover")
    if cover:
        curated.append(
            strip_bilibili_resize(cover) if platform == "bilibili" else cover
        )

    author = payload.get("author") or payload.get("owner") or {}
    face = author.get("face") or author.get("avatar")
    if face:
        curated.append(
            strip_bilibili_resize(face) if platform == "bilibili" else face
        )

    for pg in payload.get("pages") or []:
        frame = pg.get("first_frame")
        if frame:
            curated.append(
                strip_bilibili_resize(frame) if platform == "bilibili" else frame
            )

    img_platform = "bilibili" if platform == "bilibili" else ""
    return collect_images(curated, limit=10, platform=img_platform)


def _stat_line(platform: str, payload: dict) -> str | None:
    stat = payload.get("stat") or {}
    if platform == "bilibili" and stat:
        return (
            f"播放 {stat.get('view', 0):,} · 点赞 {stat.get('like', 0):,} · "
            f"投币 {stat.get('coin', 0):,} · 收藏 {stat.get('favorite', 0):,} · "
            f"弹幕 {stat.get('danmaku', 0):,} · 评论 {stat.get('reply', 0):,}"
        )

    parts: list[str] = []
    if stat.get("views") or stat.get("view"):
        parts.append(f"views {int(stat.get('views') or stat.get('view') or 0):,}")
    if stat.get("likes") or stat.get("like"):
        parts.append(f"likes {int(stat.get('likes') or stat.get('like') or 0):,}")
    if parts:
        return " · ".join(parts)
    return None


def merge_platform_result(result: dict, payload: dict) -> dict:
    """Merge any platform video payload into the standard scrape result."""
    platform = payload.get("platform") or "video"
    result["platform"] = platform
    result["title"] = payload.get("title") or result.get("title", "")

    desc = (payload.get("description") or "").strip()
    if desc:
        paragraphs = [p.strip() for p in re.split(r"\n+", desc) if p.strip()]
        result["text_paragraphs"] = paragraphs or [desc]

    author = payload.get("author") or payload.get("owner") or {}
    author_name = author.get("name")
    if author_name:
        label = "UP主" if platform == "bilibili" else "Author"
        result["text_paragraphs"] = [
            f"{label}: {author_name}",
            *[
                p
                for p in result.get("text_paragraphs", [])
                if not p.startswith(f"{label}:")
            ],
        ]

    stat_line = _stat_line(platform, payload)
    if stat_line:
        result["text_paragraphs"] = [stat_line] + result.get("text_paragraphs", [])

    if payload.get("comments"):
        result["comments"] = payload["comments"]

    stream_urls = _stream_urls(payload)
    existing = result.get("videos") or []
    result["videos"] = list(dict.fromkeys(stream_urls + existing))

    images = _curated_images(platform, payload)
    if images:
        result["images"] = images

    meta = dict(result.get("meta") or {})
    meta["video_platform"] = platform
    if payload.get("video_id"):
        meta["video_id"] = str(payload["video_id"])
    if platform == "bilibili":
        meta.update({
            "bilibili_bvid": payload.get("bvid", ""),
            "bilibili_aid": str(payload.get("aid", "")),
            "bilibili_cid": str(payload.get("cid", "")),
            "bilibili_owner": author_name or "",
            "bilibili_tags": ", ".join(payload.get("tags") or []),
        })
    if payload.get("tags"):
        meta["video_tags"] = ", ".join(payload["tags"])
    result["meta"] = meta
    result["platform_data"] = payload
    return result
