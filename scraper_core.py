#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core scraping pipeline — shared by GUI and web app."""

from __future__ import annotations

import queue
import random
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

try:
    from playwright_stealth import Stealth

    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

LogFn = Callable[[str], None]

COMMENT_HINTS = [
    "comment", "comments", "reply", "replies", "discuss",
    "review", "feedback", "danmu",
]
VIDEO_EXTS = (".mp4", ".m3u8", ".flv", ".webm", ".mov", ".avi")

COMMON_CONTENT_SELECTORS = [
    "#cnblogs_post_body",
    ".postBody", ".post_body",
    "#article_content", ".article-content", ".article__content",
    ".entry-content", ".post-content", ".post-body",
    "#js_content",
    ".markdown-body",
    "#content_views",
    ".content-detail", ".detail-content",
    "article", "main",
]

SIDEBAR_HINTS = [
    "sidebar", "side-bar", "aside", "nav", "menu", "footer", "header",
    "recommend", "related", "hot", "rank", "paihang", "tuijian",
    "widget", "banner", "advert", "ad-", "breadcrumb", "toc",
    "share", "social", "tag-list", "catalog",
]

BROWSER_PROFILES = [
    {
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
        "timezone": "Asia/Shanghai",
        "languages": ["zh-CN", "zh", "en-US", "en"],
        "platform": "Windows",
        "navigator_platform": "Win32",
    },
    {
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1536, "height": 864},
        "locale": "en-US",
        "timezone": "America/New_York",
        "languages": ["en-US", "en"],
        "platform": "Windows",
        "navigator_platform": "Win32",
    },
    {
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1440, "height": 900},
        "locale": "en-US",
        "timezone": "America/Los_Angeles",
        "languages": ["en-US", "en"],
        "platform": "macOS",
        "navigator_platform": "MacIntel",
    },
    {
        "ua": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1366, "height": 768},
        "locale": "en-GB",
        "timezone": "Europe/London",
        "languages": ["en-GB", "en"],
        "platform": "Linux",
        "navigator_platform": "Linux x86_64",
    },
]

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-dev-shm-usage",
]

CHALLENGE_TITLE_HINTS = [
    "just a moment",
    "attention required",
    "please wait",
    "verify you are human",
    "robot check",
    "access denied",
    "ddos protection",
]

CHALLENGE_HTML_HINTS = [
    "challenge-platform",
    "cf-turnstile",
    "cf-challenge",
    "cf-browser-verification",
    "g-recaptcha",
    "h-captcha",
    "hcaptcha.com",
    "captcha-container",
    "turnstile-wrapper",
]


@dataclass
class FetchConfig:
    url: str
    wait_ms: int = 3500
    cookie: str = ""
    scroll: bool = True
    proxy: str = ""
    use_chrome: bool = True
    headless: str = "auto"
    max_retries: int = 2
    simulate_human: bool = True
    block_resources: bool = False


def _stealth_init_script(languages: list[str], navigator_platform: str) -> str:
    langs = ", ".join(f"'{lang}'" for lang in languages)
    return f"""
(() => {{
  const patch = (obj, key, val) => {{
    try {{ Object.defineProperty(obj, key, {{ get: () => val }}); }} catch (_) {{}}
  }};
  patch(navigator, 'webdriver', undefined);
  patch(navigator, 'languages', [{langs}]);
  patch(navigator, 'platform', '{navigator_platform}');
  patch(navigator, 'hardwareConcurrency', 8);
  patch(navigator, 'deviceMemory', 8);
  patch(navigator, 'maxTouchPoints', 0);
  if (!window.chrome) window.chrome = {{ runtime: {{}} }};
  const origQuery = navigator.permissions?.query?.bind(navigator.permissions);
  if (origQuery) {{
    navigator.permissions.query = (params) => (
      params.name === 'notifications'
        ? Promise.resolve({{ state: Notification.permission }})
        : origQuery(params)
    );
  }}
  const getParam = WebGLRenderingContext.prototype.getParameter;
  WebGLRenderingContext.prototype.getParameter = function(param) {{
    if (param === 37445) return 'Intel Inc.';
    if (param === 37446) return 'Intel Iris OpenGL Engine';
    return getParam.call(this, param);
  }};
}})();
"""


def _chrome_version_from_ua(ua: str) -> str:
    match = re.search(r"Chrome/(\d+)", ua)
    return match.group(1) if match else "131"


def _build_headers(ua: str, url: str, languages: list[str], platform: str) -> dict:
    ver = _chrome_version_from_ua(ua)
    lang_header = ",".join(
        f"{lang};q={max(0.1, 1 - i * 0.1):.1f}" for i, lang in enumerate(languages)
    )
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": lang_header,
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": (
            f'"Google Chrome";v="{ver}", "Chromium";v="{ver}", "Not_A Brand";v="24"'
        ),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": f'"{platform}"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": origin + "/",
    }


def _parse_proxy(proxy: str) -> dict | None:
    proxy = proxy.strip()
    if not proxy:
        return None

    if "://" not in proxy:
        proxy = "http://" + proxy

    parsed = urlparse(proxy)
    if not parsed.hostname:
        raise ValueError(f"Invalid proxy address: {proxy}")

    default_port = 1080 if parsed.scheme.startswith("socks") else 8080
    port = parsed.port or default_port
    result: dict[str, str] = {"server": f"{parsed.scheme}://{parsed.hostname}:{port}"}

    if parsed.username:
        result["username"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password

    return result


def _parse_cookies(cookie: str, url: str) -> list[dict]:
    if not cookie.strip():
        return []

    parsed = urlparse(url)
    page_url = f"{parsed.scheme}://{parsed.netloc}/"
    cookies = []

    for part in cookie.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value, "url": page_url})

    return cookies


def _is_challenge_page(html: str, title: str) -> bool:
    title_lower = title.lower()
    if any(hint in title_lower for hint in CHALLENGE_TITLE_HINTS):
        return True
    html_lower = html.lower()
    return any(hint in html_lower for hint in CHALLENGE_HTML_HINTS)


def _content_quality(html: str, inner_text: str) -> int:
    if _is_challenge_page(html, ""):
        return 0
    text_len = len(inner_text.strip())
    score = min(text_len, 5000)
    if text_len < 80:
        score -= 500
    return score


def _build_strategies(cfg: FetchConfig) -> list[tuple[bool, int]]:
    wait = cfg.wait_ms

    if cfg.headless == "visible":
        return [(False, wait)]

    if cfg.headless == "hidden":
        return [(True, wait)]

    auto_plan = [
        (True, wait),
        (True, wait + 3000),
        (False, wait + 5000),
        (False, wait + 8000),
    ]
    return auto_plan[: max(1, cfg.max_retries + 1)]


def _simulate_human(page: Page, viewport: dict) -> None:
    width = viewport["width"]
    height = viewport["height"]
    for _ in range(random.randint(2, 4)):
        x = random.randint(80, max(120, width - 80))
        y = random.randint(80, max(120, height - 80))
        page.mouse.move(x, y, steps=random.randint(8, 20))
        page.wait_for_timeout(random.randint(80, 220))
    page.mouse.wheel(0, random.randint(120, 360))
    page.wait_for_timeout(random.randint(150, 400))


def _human_scroll(page: Page) -> None:
    steps = random.randint(5, 8)
    for _ in range(steps):
        delta = page.evaluate(
            "() => Math.max("
            "document.body?.scrollHeight || 0, "
            "document.documentElement?.scrollHeight || 0"
            f") / {steps}"
        )
        page.evaluate(f"window.scrollBy(0, {delta})")
        page.wait_for_timeout(random.randint(300, 900))
        if random.random() < 0.3:
            page.mouse.wheel(0, random.randint(-200, 200))
            page.wait_for_timeout(random.randint(200, 500))
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(random.randint(200, 500))


def _wait_for_challenge(page: Page, log: LogFn, timeout_ms: int = 45000) -> bool:
    log("[Browser] Challenge page detected — waiting for auto-resolution ...")
    deadline = time.time() + timeout_ms / 1000
    viewport = page.viewport_size or {"width": 1280, "height": 900}

    while time.time() < deadline:
        if not _is_challenge_page(page.content(), page.title()):
            log("[Browser] Challenge appears resolved.")
            return True
        page.wait_for_timeout(1500)
        if random.random() < 0.4:
            _simulate_human(page, viewport)

    log("[Browser] Challenge wait timed out.")
    return False


def _setup_resource_blocking(page: Page) -> None:
    blocked = ("image", "media", "font", "stylesheet")

    def handler(route):
        if route.request.resource_type in blocked:
            route.abort()
        else:
            route.continue_()

    page.route("**/*", handler)


def _launch_browser(pw: Playwright, cfg: FetchConfig, headless: bool, log: LogFn) -> Browser:
    launch_kwargs: dict = {
        "headless": headless,
        "args": BROWSER_ARGS,
    }

    proxy = _parse_proxy(cfg.proxy)
    if proxy:
        launch_kwargs["proxy"] = proxy
        log(f"[Browser] Using proxy: {proxy['server']}")

    if cfg.use_chrome:
        try:
            browser = pw.chromium.launch(channel="chrome", **launch_kwargs)
            log("[Browser] Launched system Chrome.")
            return browser
        except Exception as exc:
            log(f"[Browser] System Chrome unavailable ({exc}) — using Chromium.")

    browser = pw.chromium.launch(**launch_kwargs)
    log("[Browser] Launched bundled Chromium.")
    return browser


def _create_context(
    browser: Browser,
    profile: dict,
    url: str,
    cookie: str,
    log: LogFn,
) -> BrowserContext:
    viewport = profile["viewport"]
    languages = profile["languages"]
    ctx = browser.new_context(
        user_agent=profile["ua"],
        viewport=viewport,
        screen={"width": viewport["width"], "height": viewport["height"]},
        locale=profile["locale"],
        timezone_id=profile["timezone"],
        color_scheme="light",
        device_scale_factor=1,
        has_touch=False,
        is_mobile=False,
        java_script_enabled=True,
        ignore_https_errors=True,
        extra_http_headers=_build_headers(
            profile["ua"], url, languages, profile["platform"]
        ),
    )
    ctx.add_init_script(
        _stealth_init_script(languages, profile["navigator_platform"])
    )

    cookies = _parse_cookies(cookie, url)
    if cookies:
        ctx.add_cookies(cookies)
        log(f"[Browser] Injected {len(cookies)} cookie(s).")

    return ctx


def _extract_page_data(page: Page, url: str) -> dict:
    html = page.content()
    title = page.title()
    inner = page.evaluate("document.body ? document.body.innerText : ''")

    video_urls = list(page.evaluate("""
        () => {
            const vids = [];
            document.querySelectorAll('video, video source').forEach(el => {
                if (el.src) vids.push(el.src);
                if (el.currentSrc) vids.push(el.currentSrc);
            });
            document.querySelectorAll('iframe').forEach(el => {
                const s = el.src || '';
                if (s && (s.includes('video') || s.includes('player') ||
                          s.includes('embed') || s.includes('youtube') ||
                          s.includes('bilibili') || s.includes('vimeo'))) {
                    vids.push(s);
                }
            });
            return [...new Set(vids.filter(Boolean))];
        }
    """))

    return {
        "html": html,
        "inner_text": inner,
        "title": title,
        "url": page.url or url,
        "video_urls_from_dom": video_urls,
    }


def _attempt_fetch(
    pw: Playwright,
    cfg: FetchConfig,
    profile: dict,
    headless: bool,
    wait_ms: int,
    log: LogFn,
) -> dict:
    browser: Browser | None = None
    try:
        browser = _launch_browser(pw, cfg, headless, log)
        ctx = _create_context(browser, profile, cfg.url, cfg.cookie, log)
        page = ctx.new_page()

        if HAS_STEALTH:
            _stealth.apply_stealth_sync(page)
        if cfg.block_resources:
            _setup_resource_blocking(page)
            log("[Browser] Blocking images/fonts/styles for faster load.")

        log(f"[Browser] Navigating to {cfg.url} ...")
        page.goto(cfg.url, wait_until="domcontentloaded", timeout=60_000)

        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        if cfg.simulate_human:
            _simulate_human(page, profile["viewport"])

        if _is_challenge_page(page.content(), page.title()):
            _wait_for_challenge(page, log, timeout_ms=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass

        if cfg.scroll:
            log("[Browser] Scrolling page to trigger lazy-loaded content ...")
            _human_scroll(page)

        jittered_wait = max(500, int(wait_ms * random.uniform(0.9, 1.2)))
        log(f"[Browser] Waiting ~{jittered_wait} ms for JavaScript to settle ...")
        page.wait_for_timeout(jittered_wait)

        data = _extract_page_data(page, cfg.url)
        log(f"[Browser] Done. Title: {data['title']!r}")
        return data
    finally:
        if browser is not None:
            browser.close()


def browser_fetch(
    url: str,
    wait_ms: int,
    cookie: str,
    scroll: bool,
    log_q: queue.Queue,
    **kwargs,
) -> dict:
    def log(msg: str):
        log_q.put(("log", msg))

    cfg = FetchConfig(
        url=url,
        wait_ms=wait_ms,
        cookie=cookie,
        scroll=scroll,
        proxy=str(kwargs.get("proxy", "")).strip(),
        use_chrome=bool(kwargs.get("use_chrome", True)),
        headless=str(kwargs.get("headless", "auto")),
        max_retries=int(kwargs.get("max_retries", 2)),
        simulate_human=bool(kwargs.get("simulate_human", True)),
        block_resources=bool(kwargs.get("block_resources", False)),
    )

    if HAS_STEALTH:
        log("[Browser] playwright-stealth enabled.")
    else:
        log("[Browser] Tip: pip install playwright-stealth for stronger evasion.")

    try:
        strategies = _build_strategies(cfg)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    best: dict | None = None
    best_score = -1
    last_error: Exception | None = None

    with sync_playwright() as pw:
        for attempt, (headless, attempt_wait) in enumerate(strategies):
            profile = random.choice(BROWSER_PROFILES)
            mode = "headless" if headless else "visible"
            log(f"[Browser] Attempt {attempt + 1}/{len(strategies)} ({mode}) ...")

            try:
                data = _attempt_fetch(pw, cfg, profile, headless, attempt_wait, log)
                score = _content_quality(data["html"], data["inner_text"])
                log(f"[Browser] Content quality score: {score}")

                if score > best_score:
                    best = data
                    best_score = score

                if score >= 800 and not _is_challenge_page(data["html"], data["title"]):
                    log("[Browser] Good content captured — stopping retries.")
                    break

                if attempt < len(strategies) - 1:
                    log("[Browser] Retrying with alternate strategy ...")
                    time.sleep(random.uniform(1.5, 3.0))

            except Exception as exc:
                last_error = exc
                log(f"[Browser] Attempt failed: {exc}")
                if attempt < len(strategies) - 1:
                    time.sleep(random.uniform(2.0, 4.0))

    if best is None:
        raise last_error or RuntimeError("All fetch attempts failed")

    if _is_challenge_page(best["html"], best["title"]):
        log("[Warn] Page may still be behind bot protection — content could be incomplete.")

    return best


def _is_sidebar(tag) -> bool:
    cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
    cls = cls.lower()
    return any(h in cls for h in SIDEBAR_HINTS)


def _image_src(img, base: str) -> str | None:
    for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-url"):
        value = img.get(attr)
        if value and not value.startswith("data:"):
            return urljoin(base, value.strip())

    srcset = img.get("srcset")
    if srcset:
        first = srcset.split(",")[0].strip().split()
        if first:
            return urljoin(base, first[0])

    return None


def parse_content(data: dict, text_sel: str, comment_sel: str) -> dict:
    soup = BeautifulSoup(data["html"], "lxml")
    base = data["url"]
    title = data["title"] or _bs_title(soup)

    paragraphs = _extract_text(soup, text_sel)
    comments = _extract_comments(soup, comment_sel)

    videos = list(data["video_urls_from_dom"])
    for anchor in soup.find_all("a", href=True):
        if anchor["href"].lower().endswith(VIDEO_EXTS):
            videos.append(urljoin(base, anchor["href"]))
    videos = _dedup(videos)

    images = []
    for img in soup.find_all("img"):
        src = _image_src(img, base)
        if src and src not in images:
            images.append(src)
    images = images[:50]

    meta = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or ""
        content = tag.get("content", "")
        if name and content:
            meta[name] = content

    return {
        "url": base,
        "title": title,
        "text_paragraphs": paragraphs,
        "comments": comments,
        "videos": videos,
        "images": images,
        "meta": meta,
    }


def _bs_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else "(no title)"


def _extract_text(soup: BeautifulSoup, sel: str) -> list:
    if sel:
        nodes = soup.select(sel)
        result = [
            n.get_text(strip=True, separator=" ")
            for n in nodes
            if n.get_text(strip=True)
        ]
        if result:
            return result

    container = None
    for css in COMMON_CONTENT_SELECTORS:
        node = soup.select_one(css)
        if node and len(node.get_text(strip=True)) > 200:
            container = node
            break
    if container is None:
        container = soup.find("article") or soup

    paras = [
        p.get_text(strip=True, separator=" ")
        for p in container.find_all(
            ["p", "h2", "h3", "h4", "h5", "li", "pre", "code", "blockquote"]
        )
        if len(p.get_text(strip=True)) > 1 and not _is_sidebar(p)
    ]

    if len(paras) < 3:
        seen, paras = set(), []
        for div in container.find_all("div"):
            if _is_sidebar(div):
                continue
            text = div.get_text(strip=True, separator=" ")
            if len(text) > 50 and text not in seen:
                seen.add(text)
                paras.append(text)
        paras = paras[:60]

    return paras


def _extract_comments(soup: BeautifulSoup, sel: str) -> list:
    if sel:
        return [
            n.get_text(strip=True, separator=" ")
            for n in soup.select(sel)
            if n.get_text(strip=True)
        ]

    seen, results = set(), []
    for tag in soup.find_all(["div", "li", "section"]):
        if _is_sidebar(tag):
            continue
        cls = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if any(h in cls.lower() for h in COMMENT_HINTS):
            txt = tag.get_text(strip=True, separator=" ")
            if txt and 5 < len(txt) < 2000 and txt not in seen:
                seen.add(txt)
                results.append(txt)
    return results[:200]


def _dedup(lst: list) -> list:
    seen, out = set(), []
    for item in lst:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def run_pipeline(
    url: str,
    text_sel: str,
    comment_sel: str,
    cookie: str,
    wait_ms: int,
    scroll: bool,
    log_q: queue.Queue,
    **kwargs,
):
    try:
        raw = browser_fetch(url, wait_ms, cookie, scroll, log_q, **kwargs)
        result = parse_content(raw, text_sel, comment_sel)
        log_q.put(("done", result))
    except Exception as exc:
        log_q.put(("error", str(exc)))
