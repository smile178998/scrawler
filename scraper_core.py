#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core scraping pipeline — shared by GUI and web app."""

from __future__ import annotations

import os
import queue
import random
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from video_platforms import (
    detect_video_platform,
    extract_platform_data,
    is_video_platform_url,
    merge_platform_result,
)
from image_utils import collect_images, filter_images_for_url, pick_og_image, strip_bilibili_resize
from media_downloader import download_media
from selector_engine import SelectorConfig, enhance_with_auto_selectors

try:
    from playwright_stealth import Stealth

    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

LogFn = Callable[[str], None]

PROFILE_DIR = Path(__file__).resolve().parent / ".chrome_profile"

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
    "--disable-quic",
]

CHALLENGE_TITLE_HINTS = [
    "just a moment",
    "attention required",
    "please wait",
    "verify you are human",
    "robot check",
    "access denied",
    "ddos protection",
    "验证码",
    "captcha",
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
    "geetest",
    "bilibili-captcha",
    "verifycenter",
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
    use_saved_profile: bool = True


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


NETWORK_ERROR_MARKERS = (
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_RESET",
    "ERR_TIMED_OUT",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_NETWORK_CHANGED",
    "ERR_INTERNET_DISCONNECTED",
    "ECONNRESET",
    "ETIMEDOUT",
)

PROXY_RECOMMENDED_HOSTS = (
    "youtube.com",
    "youtu.be",
    "googlevideo.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
)


def _resolve_proxy(explicit: str) -> tuple[str, str]:
    """Return (proxy_url, source). Source is 'ui', env var name, or ''."""
    explicit = (explicit or "").strip()
    if explicit:
        return explicit, "ui"
    for key in ("SCRAPER_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        val = os.getenv(key, "").strip()
        if val:
            return val, key
    return "", ""


def _proxy_endpoint_reachable(server: str, timeout: float = 2.0) -> bool:
    parsed = urlparse(server if "://" in server else f"http://{server}")
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (1080 if parsed.scheme.startswith("socks") else 8080)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _validate_proxy(proxy: str, source: str, log: LogFn) -> str:
    """Drop dead proxy settings (common when HTTP_PROXY points to a closed local port)."""
    if not proxy:
        return ""
    parsed = _parse_proxy(proxy)
    if not parsed:
        log(f"[Warn] Invalid proxy ignored: {proxy}")
        return ""
    server = parsed["server"]
    if _proxy_endpoint_reachable(server):
        return proxy
    if source == "ui":
        log(f"[Warn] Proxy {server} is not reachable — check address/port.")
        return proxy
    log(
        f"[Warn] Environment {source}={proxy!r} but nothing is listening — "
        "using direct connection. Unset HTTP_PROXY or start your proxy app."
    )
    return ""


def _site_needs_proxy(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(marker in host for marker in PROXY_RECOMMENDED_HOSTS)


def _is_network_error(exc: BaseException) -> bool:
    msg = str(exc).upper()
    return any(marker in msg for marker in NETWORK_ERROR_MARKERS)


def _format_browser_error(
    exc: BaseException, url: str = "", *, used_proxy: bool = False
) -> str:
    msg = str(exc)
    host = urlparse(url).netloc if url else "target site"
    short = msg.splitlines()[0]

    if _is_network_error(exc):
        parts = [f"Connection failed ({host}): {short}"]
        if used_proxy:
            parts.append(
                "Proxy is enabled but the tunnel closed. "
                "Clear Proxy in Advanced Options, unset HTTP_PROXY/SCRAPER_PROXY in environment, "
                "or fix the proxy address."
            )
        else:
            parts.append(
                "Try: enable Use system Chrome + Visible browser, "
                "disable VPN/antivirus temporarily, or open the URL in normal Chrome first."
            )
        return " ".join(parts)

    if "Timeout" in msg or "timeout" in msg:
        return (
            f"Page load timed out ({host}). "
            "Increase JS wait or switch Browser mode to Visible."
        )

    return msg


def _goto_page(page: Page, url: str, log: LogFn) -> None:
    """Navigate with retries — handles transient network drops."""
    last_exc: Exception | None = None
    wait_modes = ("domcontentloaded", "commit")

    for attempt in range(3):
        for wait_until in wait_modes:
            try:
                page.goto(url, wait_until=wait_until, timeout=90_000)
                if wait_until == "commit":
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=20_000)
                    except Exception:
                        pass
                return
            except Exception as exc:
                last_exc = exc
                if not _is_network_error(exc):
                    raise
                short = str(exc).split("\n", 1)[0]
                log(
                    f"[Browser] Network error ({wait_until}, "
                    f"attempt {attempt + 1}/3): {short}"
                )
                page.wait_for_timeout(1500 * (attempt + 1))

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Failed to navigate to {url}")


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


def _content_quality(html: str, inner_text: str, data: dict | None = None, url: str = "") -> int:
    if _is_challenge_page(html, ""):
        return 0
    if is_video_platform_url(url) and data and data.get("platform_data"):
        return 10_000
    text_len = len(inner_text.strip())
    score = min(text_len, 5000)
    if text_len < 80:
        score -= 500
    if is_video_platform_url(url) and not (data and data.get("platform_data")):
        score = min(score, 400)
    return score


def _fetch_success(data: dict, url: str) -> bool:
    if _is_challenge_page(data.get("html", ""), data.get("title", "")):
        return False
    if is_video_platform_url(url):
        return bool(data.get("platform_data"))
    return _content_quality(data.get("html", ""), data.get("inner_text", "")) >= 800


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


def _extract_page_data(page: Page, url: str, log: LogFn | None = None) -> dict:
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

    data = {
        "html": html,
        "inner_text": inner,
        "title": title,
        "url": page.url or url,
        "video_urls_from_dom": video_urls,
    }

    platform = detect_video_platform(url)
    if platform:
        log_fn = log or (lambda _msg: None)
        payload = extract_platform_data(page, url, log_fn)
        if payload:
            data["platform_data"] = payload
            if payload.get("title"):
                data["title"] = payload["title"]

    return data


def _fetch_on_page(
    page: Page,
    cfg: FetchConfig,
    profile: dict,
    wait_ms: int,
    log: LogFn,
) -> dict:
    if HAS_STEALTH:
        _stealth.apply_stealth_sync(page)
    if cfg.block_resources:
        _setup_resource_blocking(page)
        log("[Browser] Blocking images/fonts/styles for faster load.")

    log(f"[Browser] Navigating to {cfg.url} ...")
    _goto_page(page, cfg.url, log)

    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass

    if cfg.simulate_human:
        _simulate_human(page, profile["viewport"])

    if _is_challenge_page(page.content(), page.title()):
        if cfg.use_saved_profile:
            log("[Browser] Verification detected — complete it in the browser window if visible.")
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

    data = _extract_page_data(page, cfg.url, log)
    if is_video_platform_url(cfg.url) and not data.get("platform_data"):
        platform = detect_video_platform(cfg.url) or "video"
        log(f"[Video:{platform}] Parser missed data — waiting extra 4s and retrying ...")
        page.wait_for_timeout(4000)
        data = _extract_page_data(page, cfg.url, log)
    log(f"[Browser] Done. Title: {data['title']!r}")
    return data


def _attempt_fetch(
    pw: Playwright,
    cfg: FetchConfig,
    profile: dict,
    headless: bool,
    wait_ms: int,
    log: LogFn,
) -> dict:
    if cfg.use_saved_profile:
        ctx: BrowserContext | None = None
        try:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            viewport = profile["viewport"]
            launch_kwargs: dict = {
                "headless": headless,
                "viewport": viewport,
                "locale": profile["locale"],
                "timezone_id": profile["timezone"],
                "args": BROWSER_ARGS,
                "ignore_https_errors": True,
            }
            proxy = _parse_proxy(cfg.proxy)
            if proxy:
                launch_kwargs["proxy"] = proxy
                log(f"[Browser] Using proxy: {proxy['server']}")
            if cfg.use_chrome:
                launch_kwargs["channel"] = "chrome"
            log("[Browser] Using saved login profile — sessions persist for all sites.")
            if not headless:
                log("[Browser] Opening visible Chrome window — may take 30-60s on first run …")
            try:
                ctx = pw.chromium.launch_persistent_context(
                    str(PROFILE_DIR), **launch_kwargs
                )
            except Exception as exc:
                err = str(exc)
                if "ProcessSingleton" in err or "already in use" in err.lower():
                    log(
                        "[Browser] Profile locked — close other Chrome/scraper windows, "
                        "then retry. Falling back to temporary browser."
                    )
                else:
                    log(f"[Browser] Profile launch failed ({exc}) — using temporary browser.")
                fallback = FetchConfig(
                    url=cfg.url,
                    wait_ms=cfg.wait_ms,
                    cookie=cfg.cookie,
                    scroll=cfg.scroll,
                    proxy=cfg.proxy,
                    use_chrome=cfg.use_chrome,
                    headless=cfg.headless,
                    max_retries=cfg.max_retries,
                    simulate_human=cfg.simulate_human,
                    block_resources=cfg.block_resources,
                    use_saved_profile=False,
                )
                return _attempt_fetch(pw, fallback, profile, headless, wait_ms, log)

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            if cfg.cookie.strip():
                cookies = _parse_cookies(cfg.cookie, cfg.url)
                if cookies:
                    ctx.add_cookies(cookies)
                    log(f"[Browser] Also injected {len(cookies)} extra cookie(s).")

            return _fetch_on_page(page, cfg, profile, wait_ms, log)
        finally:
            if ctx is not None:
                ctx.close()

    browser: Browser | None = None
    try:
        browser = _launch_browser(pw, cfg, headless, log)
        ctx = _create_context(browser, profile, cfg.url, cfg.cookie, log)
        page = ctx.new_page()
        return _fetch_on_page(page, cfg, profile, wait_ms, log)
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

    proxy, source = _resolve_proxy(str(kwargs.get("proxy", "")).strip())
    proxy = _validate_proxy(proxy, source, log)
    if proxy and source == "ui":
        parsed = _parse_proxy(proxy)
        if parsed:
            log(f"[Browser] Using proxy: {parsed['server']}")
    elif proxy and source not in ("", "ui"):
        parsed = _parse_proxy(proxy)
        if parsed:
            log(f"[Browser] Using proxy from {source}: {parsed['server']}")

    cfg = FetchConfig(
        url=url,
        wait_ms=wait_ms,
        cookie=cookie,
        scroll=scroll,
        proxy=proxy,
        use_chrome=bool(kwargs.get("use_chrome", True)),
        headless=str(kwargs.get("headless", "auto")),
        max_retries=int(kwargs.get("max_retries", 2)),
        simulate_human=bool(kwargs.get("simulate_human", True)),
        block_resources=bool(kwargs.get("block_resources", False)),
        use_saved_profile=bool(kwargs.get("use_saved_profile", True)),
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
                score = _content_quality(data["html"], data["inner_text"], data, cfg.url)
                log(f"[Browser] Content quality score: {score}")

                if score > best_score:
                    best = data
                    best_score = score

                if _fetch_success(data, cfg.url):
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

    if best is None and cfg.proxy and last_error and _is_network_error(last_error):
        log("[Browser] Proxy/direct failed — final retry without proxy ...")
        cfg = FetchConfig(
            url=cfg.url,
            wait_ms=cfg.wait_ms,
            cookie=cfg.cookie,
            scroll=cfg.scroll,
            proxy="",
            use_chrome=cfg.use_chrome,
            headless=cfg.headless,
            max_retries=cfg.max_retries,
            simulate_human=cfg.simulate_human,
            block_resources=cfg.block_resources,
            use_saved_profile=cfg.use_saved_profile,
        )
        with sync_playwright() as pw:
            profile = random.choice(BROWSER_PROFILES)
            headless = cfg.headless == "hidden"
            log(f"[Browser] Direct retry ({'headless' if headless else 'visible'}) ...")
            try:
                data = _attempt_fetch(pw, cfg, profile, headless, cfg.wait_ms, log)
                best = data
                best_score = _content_quality(data["html"], data["inner_text"], data, cfg.url)
            except Exception as exc:
                last_error = exc
                log(f"[Browser] Direct retry failed: {exc}")

    if best is None:
        raise last_error or RuntimeError("All fetch attempts failed")

    if _is_challenge_page(best["html"], best["title"]):
        log("[Warn] Page may still be behind bot protection — content could be incomplete.")
    elif is_video_platform_url(cfg.url) and not best.get("platform_data"):
        platform = detect_video_platform(cfg.url) or "video"
        log(
            f"[Warn] {platform} parser did not extract video data. "
            "Use saved login / Cookie, Visible browser, and increase JS wait."
        )

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
    videos = [v for v in videos if v and not str(v).startswith("blob:")]

    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or ""
        content = tag.get("content", "")
        if name and content:
            meta[name] = content

    images = []
    for img in soup.find_all("img"):
        src = _image_src(img, base)
        if src:
            images.append(src)
    plat = "bilibili" if detect_video_platform(base) == "bilibili" else ""
    images = collect_images(images, platform=plat)
    if plat:
        og = pick_og_image(meta, platform=plat)
        images = filter_images_for_url(base, images, limit=5)
        if og:
            images = collect_images([og] + images, limit=5, platform=plat)

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
    def log(msg: str):
        log_q.put(("log", msg))

    try:
        raw_proxy, proxy_source = _resolve_proxy(str(kwargs.get("proxy", "")).strip())
        proxy = _validate_proxy(raw_proxy, proxy_source, log)
        kwargs["proxy"] = proxy

        if kwargs.get("use_saved_profile", True):
            log("[Browser] Saved profile ON — sign in once per site (Visible mode); Cookie optional.")

        if proxy_source in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "SCRAPER_PROXY"):
            log(f"[Browser] Proxy loaded from environment ({proxy_source}).")

        video_mode = is_video_platform_url(url)
        if video_mode:
            platform = detect_video_platform(url) or "video"
            if platform == "bilibili":
                cookie = (cookie or "").strip() or os.getenv("BILI_COOKIE", "").strip()
            wait_ms = max(int(wait_ms), 8000)
            kwargs["auto_selector"] = False
            kwargs["auto_selector_ai"] = False
            log(f"[Video:{platform}] Using platform parser (auto-selector disabled, wait ≥ 8s).")
            if cookie:
                log("[Video] Login cookie detected.")
            elif kwargs.get("use_saved_profile", True):
                log("[Video] Using saved Chrome profile — works for all video sites.")
            else:
                log("[Video] Tip: enable saved profile or paste Cookie for login & comments.")

        raw = browser_fetch(url, wait_ms, cookie, scroll, log_q, **kwargs)
        result = parse_content(raw, text_sel, comment_sel)
        warnings: list[str] = []

        if raw.get("platform_data"):
            platform = raw["platform_data"].get("platform") or detect_video_platform(url) or "video"
            log(f"[Video:{platform}] Merging platform-specific data into results ...")
            result = merge_platform_result(result, raw["platform_data"])
        elif video_mode:
            warnings.append(
                f"{detect_video_platform(url) or 'Video'} parser failed — page may be a captcha "
                "or missing login. Try: Remember login + Visible browser + JS wait 8000ms."
            )
            log("[Warn] " + warnings[-1])
            result["images"] = filter_images_for_url(result["url"], result.get("images") or [])
            result["videos"] = [
                v for v in (result.get("videos") or [])
                if v and not str(v).startswith("blob:")
            ]
        else:
            selector_cfg = SelectorConfig(
                enabled=bool(kwargs.get("auto_selector", True)),
                use_ai=bool(kwargs.get("auto_selector_ai", True)),
                ai_api_key=str(kwargs.get("ai_api_key", "")).strip(),
                ai_base_url=str(kwargs.get("ai_base_url", "")).strip() or "https://api.openai.com/v1",
                ai_model=str(kwargs.get("ai_model", "")).strip() or "gpt-4o-mini",
            )
            result = enhance_with_auto_selectors(
                raw, result, text_sel, comment_sel, selector_cfg, parse_content, log
            )

        if kwargs.get("download_media", True):
            log("[Download] Saving images and videos to disk ...")
            result = download_media(result, log)

        if warnings:
            result["warnings"] = warnings

        log_q.put(("done", result))
    except Exception as exc:
        used_proxy = bool(kwargs.get("proxy"))
        log_q.put(("error", _format_browser_error(exc, url, used_proxy=used_proxy)))
