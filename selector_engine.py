#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smart CSS selector discovery — heuristic DOM scoring + optional AI fallback."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Callable

from bs4 import BeautifulSoup, Tag

LogFn = Callable[[str], None]

CONTENT_HINTS = [
    "article", "content", "post", "entry", "body", "markdown",
    "detail", "story", "text", "main", "blog", "news", "rich",
    "editor", "publish", "single", "thread",
]

COMMENT_HINTS = [
    "comment", "comments", "reply", "replies", "discuss",
    "review", "feedback", "danmu", "message-list",
]

SIDEBAR_HINTS = [
    "sidebar", "side-bar", "aside", "nav", "menu", "footer", "header",
    "recommend", "related", "hot", "rank", "widget", "banner",
    "advert", "ad-", "breadcrumb", "toc", "share", "social",
    "cookie", "popup", "modal", "toolbar",
]

SKIP_TAGS = {"script", "style", "noscript", "svg", "path", "iframe", "button", "form"}

DYNAMIC_CLASS_RE = re.compile(
    r"^(css-[a-z0-9]{4,}|_[a-zA-Z0-9]{5,}|[a-f0-9]{8,}|jsx-[a-f0-9]+)$"
)


@dataclass
class SelectorConfig:
    enabled: bool = True
    use_ai: bool = True
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    min_content_chars: int = 100
    min_paragraphs: int = 2


@dataclass
class DiscoveredSelectors:
    text_selector: str = ""
    comment_selector: str = ""
    method: str = "none"
    confidence: float = 0.0
    text_score: float = 0.0
    comment_score: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _noop_log(_: str) -> None:
    pass


def _load_env_defaults(cfg: SelectorConfig) -> SelectorConfig:
    return SelectorConfig(
        enabled=cfg.enabled,
        use_ai=cfg.use_ai,
        ai_api_key=cfg.ai_api_key or os.getenv("OPENAI_API_KEY", "") or os.getenv("AI_API_KEY", ""),
        ai_base_url=cfg.ai_base_url or os.getenv("AI_BASE_URL", "https://api.openai.com/v1"),
        ai_model=cfg.ai_model or os.getenv("AI_MODEL", "gpt-4o-mini"),
        min_content_chars=cfg.min_content_chars,
        min_paragraphs=cfg.min_paragraphs,
    )


def _attr_blob(tag: Tag) -> str:
    parts = [tag.get("id") or ""]
    parts.extend(tag.get("class") or [])
    return " ".join(parts).lower()


def _is_sidebar(tag: Tag) -> bool:
    blob = _attr_blob(tag)
    return any(h in blob for h in SIDEBAR_HINTS)


def _is_dynamic_token(token: str) -> bool:
    token = token.strip()
    if not token or len(token) > 40:
        return True
    return bool(DYNAMIC_CLASS_RE.match(token))


def _stable_classes(tag: Tag, limit: int = 3) -> list[str]:
    out = []
    for cls in tag.get("class") or []:
        cls = cls.strip()
        if cls and not _is_dynamic_token(cls):
            out.append(cls)
        if len(out) >= limit:
            break
    return out


def _css_escape(value: str) -> str:
    return re.sub(r"([ !\"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])", r"\\\1", value)


def build_css_selector(tag: Tag, soup: BeautifulSoup) -> str:
    elem_id = tag.get("id")
    if elem_id and not _is_dynamic_token(elem_id):
        sel = f"#{_css_escape(elem_id)}"
        if len(soup.select(sel)) == 1:
            return sel

    classes = _stable_classes(tag)
    if classes:
        sel = tag.name + "".join(f".{_css_escape(c)}" for c in classes)
        matches = soup.select(sel)
        if len(matches) == 1:
            return sel
        if len(matches) <= 5:
            return sel

    parts: list[str] = []
    cur: Tag | None = tag
    depth = 0
    while cur and cur.name and cur.name not in ("html", "body", "[document]") and depth < 5:
        ident = cur.name
        elem_id = cur.get("id")
        if elem_id and not _is_dynamic_token(elem_id):
            ident = f"{cur.name}#{_css_escape(elem_id)}"
            parts.insert(0, ident)
            break

        classes = _stable_classes(cur, limit=1)
        if classes:
            ident = f"{cur.name}.{ _css_escape(classes[0]) }"

        parent = cur.parent
        if parent and isinstance(parent, Tag) and cur.name:
            siblings = [s for s in parent.find_all(cur.name, recursive=False) if isinstance(s, Tag)]
            if len(siblings) > 1:
                idx = siblings.index(cur) + 1
                ident = f"{ident}:nth-of-type({idx})"

        parts.insert(0, ident)
        cur = parent if isinstance(parent, Tag) else None
        depth += 1

    return " > ".join(parts) if parts else tag.name


def _link_density(tag: Tag) -> float:
    text = tag.get_text(strip=True)
    if not text:
        return 1.0
    link_text = sum(len(a.get_text(strip=True)) for a in tag.find_all("a"))
    return min(1.0, link_text / max(len(text), 1))


def _paragraph_count(tag: Tag) -> int:
    return len([p for p in tag.find_all("p") if len(p.get_text(strip=True)) > 20])


def _semantic_bonus(blob: str, hints: list[str]) -> float:
    return sum(3.0 for h in hints if h in blob)


def _score_content_block(tag: Tag) -> float:
    if tag.name in SKIP_TAGS or _is_sidebar(tag):
        return -999.0

    text = tag.get_text(strip=True, separator=" ")
    text_len = len(text)
    if text_len < 80:
        return -999.0

    blob = _attr_blob(tag)
    score = 0.0

    if tag.name in ("article", "main"):
        score += 25
    score += min(text_len / 40, 120)
    score += _paragraph_count(tag) * 8
    score += _semantic_bonus(blob, CONTENT_HINTS)
    score -= _link_density(tag) * 35
    score -= _semantic_bonus(blob, SIDEBAR_HINTS)

    if tag.find(["nav", "footer", "aside"]):
        score -= 15

    depth = len(list(tag.parents))
    if 4 <= depth <= 12:
        score += 8

    return score


def _score_comment_block(tag: Tag) -> float:
    if tag.name in SKIP_TAGS or _is_sidebar(tag):
        return -999.0

    blob = _attr_blob(tag)
    if any(h in blob for h in CONTENT_HINTS) and not any(h in blob for h in COMMENT_HINTS):
        return -999.0

    comment_children = [
        c for c in tag.find_all(["div", "li", "article"], recursive=False)
        if isinstance(c, Tag) and any(h in _attr_blob(c) for h in COMMENT_HINTS)
    ]
    if comment_children:
        return 40 + len(comment_children) * 12

    if any(h in blob for h in COMMENT_HINTS):
        text = tag.get_text(strip=True)
        if len(text) < 30:
            return -999.0
        return min(len(text) / 30, 80) + _semantic_bonus(blob, COMMENT_HINTS)

    children = [c for c in tag.find_all(recursive=False) if isinstance(c, Tag)]
    if len(children) < 3:
        return -999.0
    lengths = [len(c.get_text(strip=True)) for c in children]
    if max(lengths) < 10:
        return -999.0
    avg = sum(lengths) / len(lengths)
    variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
    if variance > avg * avg * 2:
        return -999.0
    return len(children) * 4 + min(sum(lengths) / 50, 40)


def _best_candidate(soup: BeautifulSoup, scorer, min_score: float = 15.0) -> tuple[Tag | None, float]:
    best_tag: Tag | None = None
    best_score = min_score
    seen_ids: set[int] = set()

    for tag in soup.find_all(["article", "main", "section", "div"]):
        tid = id(tag)
        if tid in seen_ids:
            continue
        seen_ids.add(tid)

        score = scorer(tag)
        if score > best_score:
            best_score = score
            best_tag = tag

    return best_tag, best_score


def _validate_text_selector(soup: BeautifulSoup, selector: str, cfg: SelectorConfig) -> tuple[bool, float]:
    if not selector:
        return False, 0.0
    try:
        nodes = soup.select(selector)
    except Exception:
        return False, 0.0
    if not nodes:
        return False, 0.0

    text = " ".join(n.get_text(strip=True, separator=" ") for n in nodes)
    p_count = sum(len(n.find_all("p")) for n in nodes)
    p_count = max(p_count, len([p for p in text.split(". ") if len(p.strip()) > 30]))
    score = len(text) + p_count * 50
    ok = len(text) >= cfg.min_content_chars and p_count >= cfg.min_paragraphs
    return ok, score


def _validate_comment_selector(soup: BeautifulSoup, selector: str) -> tuple[bool, float]:
    if not selector:
        return False, 0.0
    try:
        nodes = soup.select(selector)
    except Exception:
        return False, 0.0
    texts = [n.get_text(strip=True) for n in nodes if 5 < len(n.get_text(strip=True)) < 2000]
    return len(texts) >= 1, len(texts) * 10


def _simplify_html(html: str, max_chars: int = 18000) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "noscript", "svg", "iframe", "link", "meta"]):
        tag.decompose()

    body = soup.body or soup
    for tag in body.find_all(True):
        attrs = dict(tag.attrs)
        tag.attrs = {}
        if tag.name in ("a", "img"):
            for key in ("href", "src", "class", "id"):
                if key in attrs:
                    tag.attrs[key] = attrs[key]
        elif "class" in attrs or "id" in attrs:
            if "id" in attrs:
                tag.attrs["id"] = attrs["id"]
            if "class" in attrs:
                tag.attrs["class"] = attrs["class"]

    text = str(body)
    if len(text) > max_chars:
        return text[:max_chars] + "\n<!-- truncated -->"
    return text


def _ai_discover_selectors(html: str, cfg: SelectorConfig, log: LogFn) -> DiscoveredSelectors:
    if not cfg.ai_api_key:
        log("[Selector] AI fallback skipped — no API key (set OPENAI_API_KEY or pass ai_api_key).")
        return DiscoveredSelectors()

    simplified = _simplify_html(html)
    prompt = f"""You are an expert web scraping engineer. Analyze this HTML and return CSS selectors.

Rules:
1. text_selector must target the MAIN article/body content only (not nav, sidebar, footer, ads).
2. comment_selector must target individual comment/review items (not the whole page). Use empty string if no comments.
3. Prefer stable selectors: #id, semantic class names, article/main tags. Avoid dynamic hashed classes.
4. Return ONLY valid JSON, no markdown.

HTML:
{simplified}

Return JSON:
{{"text_selector": "...", "comment_selector": "...", "reasoning": "brief explanation"}}"""

    url = cfg.ai_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.ai_model,
        "messages": [
            {"role": "system", "content": "You output only valid JSON for CSS selector discovery."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.ai_api_key}",
        },
        method="POST",
    )

    try:
        log(f"[Selector] Calling AI model {cfg.ai_model} ...")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return DiscoveredSelectors(
            text_selector=str(parsed.get("text_selector", "")).strip(),
            comment_selector=str(parsed.get("comment_selector", "")).strip(),
            method="ai",
            reasoning=str(parsed.get("reasoning", "")).strip(),
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()[:200]
        log(f"[Selector] AI request failed ({exc.code}): {body}")
    except Exception as exc:
        log(f"[Selector] AI request failed: {exc}")

    return DiscoveredSelectors()


def discover_selectors(html: str, cfg: SelectorConfig, log: LogFn = _noop_log) -> DiscoveredSelectors:
    cfg = _load_env_defaults(cfg)
    soup = BeautifulSoup(html, "lxml")
    result = DiscoveredSelectors()

    text_tag, text_score = _best_candidate(soup, _score_content_block)
    if text_tag:
        result.text_selector = build_css_selector(text_tag, soup)
        result.text_score = text_score
        log(f"[Selector] Heuristic text candidate: {result.text_selector!r} (score={text_score:.0f})")

    comment_tag, comment_score = _best_candidate(soup, _score_comment_block, min_score=10.0)
    if comment_tag:
        comment_children = [
            c for c in comment_tag.find_all(["div", "li"], recursive=False)
            if isinstance(c, Tag) and any(h in _attr_blob(c) for h in COMMENT_HINTS)
        ]
        if comment_children:
            parent_sel = build_css_selector(comment_tag, soup)
            child_name = comment_children[0].name
            child_classes = _stable_classes(comment_children[0], limit=1)
            if parent_sel and child_classes:
                result.comment_selector = f"{parent_sel} .{child_classes[0]}"
            elif parent_sel:
                result.comment_selector = f"{parent_sel} > {child_name}"
            else:
                result.comment_selector = build_css_selector(comment_children[0], soup)
        else:
            result.comment_selector = build_css_selector(comment_tag, soup)
        result.comment_score = comment_score
        log(f"[Selector] Heuristic comment candidate: {result.comment_selector!r} (score={comment_score:.0f})")

    ok_text, val_text = _validate_text_selector(soup, result.text_selector, cfg)
    ok_comment, val_comment = _validate_comment_selector(soup, result.comment_selector)

    if ok_text:
        result.confidence = min(0.95, 0.5 + val_text / 2000)
        result.method = "heuristic"
    elif result.text_selector and val_text >= 80:
        result.confidence = 0.45
        result.method = "heuristic"
        ok_text = True
    else:
        result.text_selector = ""
        result.confidence = 0.0

    if not ok_comment:
        result.comment_selector = ""

    need_ai = cfg.use_ai and (not ok_text or (comment_tag and not ok_comment))
    if need_ai and cfg.ai_api_key:
        ai_result = _ai_discover_selectors(html, cfg, log)
        if ai_result.text_selector:
            ai_ok, ai_val = _validate_text_selector(soup, ai_result.text_selector, cfg)
            if ai_ok and ai_val >= val_text:
                result.text_selector = ai_result.text_selector
                result.text_score = ai_val
                ok_text = True
                log(f"[Selector] AI text selector accepted: {result.text_selector!r}")

        if ai_result.comment_selector:
            ai_c_ok, ai_c_val = _validate_comment_selector(soup, ai_result.comment_selector)
            if ai_c_ok and ai_c_val >= val_comment:
                result.comment_selector = ai_result.comment_selector
                result.comment_score = ai_c_val
                log(f"[Selector] AI comment selector accepted: {result.comment_selector!r}")

        if ai_result.text_selector or ai_result.comment_selector:
            result.method = "hybrid" if result.method == "heuristic" else "ai"
            result.reasoning = ai_result.reasoning
            if ok_text:
                result.confidence = min(0.98, 0.6 + val_text / 2000)

    if result.text_selector or result.comment_selector:
        log(f"[Selector] Final — text: {result.text_selector!r}, comment: {result.comment_selector!r}, method: {result.method}")
    else:
        log("[Selector] Could not discover reliable selectors.")

    return result


def _content_quality(result: dict) -> int:
    text = " ".join(result.get("text_paragraphs") or [])
    return len(text) + len(result.get("text_paragraphs") or []) * 40


def enhance_with_auto_selectors(
    raw: dict,
    result: dict,
    text_sel: str,
    comment_sel: str,
    cfg: SelectorConfig,
    parse_fn: Callable[..., dict],
    log: LogFn = _noop_log,
) -> dict:
    """Re-parse with discovered selectors when manual ones are missing or weak."""
    if not cfg.enabled:
        return result

    weak = _content_quality(result) < cfg.min_content_chars + cfg.min_paragraphs * 40
    has_manual_text = bool(text_sel.strip())
    has_manual_comment = bool(comment_sel.strip())

    if has_manual_text and has_manual_comment and not weak:
        log("[Selector] Skipped — user provided selectors and results look good.")
        return result

    if has_manual_text and not weak and not has_manual_comment:
        log("[Selector] Using manual text selector; discovering comments only.")
    elif not has_manual_text and not weak:
        log("[Selector] Running discovery to find optimal selectors ...")
    else:
        log("[Selector] Content weak or selectors missing — running smart discovery ...")

    discovered = discover_selectors(raw["html"], cfg, log)

    if not discovered.text_selector and not discovered.comment_selector:
        result["discovered_selectors"] = discovered.to_dict()
        return result

    new_text_sel = text_sel.strip() or discovered.text_selector
    new_comment_sel = comment_sel.strip() or discovered.comment_selector

    refined = parse_fn(raw, new_text_sel, new_comment_sel)
    if _content_quality(refined) >= _content_quality(result) - 50:
        if _content_quality(refined) > _content_quality(result):
            log("[Selector] Re-extraction improved results — applying discovered selectors.")
        else:
            log("[Selector] Applying discovered selectors.")
        refined["discovered_selectors"] = discovered.to_dict()
        refined["applied_selectors"] = {
            "text_selector": new_text_sel,
            "comment_selector": new_comment_sel,
        }
        return refined

    log("[Selector] Discovered selectors did not improve results — keeping original.")
    result["discovered_selectors"] = discovered.to_dict()
    return result
