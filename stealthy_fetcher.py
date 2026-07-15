#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StealthyFetcher — advanced anti-bot browser fetch with fingerprint spoofing.

Tier-3 counterpart to ``Fetcher`` (HTTP) and ``DynamicFetcher`` (Playwright):

* Prefer **patchright** (stealth Chromium fork) when installed; else Playwright
* Fingerprint controls: canvas noise, WebRTC IP leak block, WebGL toggle
* ``solve_cloudflare=True`` — detect & clear Cloudflare Turnstile / interstitial
  challenges (managed / interactive / non-interactive / embedded), Scrapling-style

This does **not** cryptographically crack CAPTCHAs. It presents a more realistic
browser environment and automates the UI flow so challenges can pass on their own.
"""

from __future__ import annotations

import random
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from fetcher import FetchError
from dynamic_fetcher import (
    DynamicFetchResult,
    PageAction,
    CookieInput,
    ProxyInput,
    _as_bool_chrome,
    _normalize_proxy,
    _pick_profile,
    _inject_cookies,
    _block_heavy_resources,
)

# Prefer patchright (drops many Playwright CDP / automation leaks).
try:
    from patchright.sync_api import sync_playwright as _sync_playwright

    HAS_PATCHRIGHT = True
    ENGINE_NAME = "patchright"
except ImportError:
    from playwright.sync_api import sync_playwright as _sync_playwright

    HAS_PATCHRIGHT = False
    ENGINE_NAME = "playwright"

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, Response as PWResponse

try:
    from playwright_stealth import Stealth

    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

from scraper_core import (  # noqa: E402
    BROWSER_ARGS,
    _build_headers,
    _is_challenge_page,
    _simulate_human,
    _stealth_init_script,
)

CF_FRAME_RE = re.compile(
    r"^https?://challenges\.cloudflare\.com/cdn-cgi/challenge-platform/.*"
)
TURNSTILE_SCRIPT_RE = re.compile(
    r'challenges\.cloudflare\.com/turnstile/v', re.I
)

DEFAULT_TIMEOUT_MS = 60_000  # CF solver needs longer waits
DEFAULT_WAIT_MS = 0

STEALTH_LAUNCH_FLAGS = (
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-dev-shm-usage",
    "--disable-features=IsolateOrigins,site-per-process",
    "--lang=en-US",
)


def _fingerprint_init_script(
    *,
    languages: list[str],
    navigator_platform: str,
    hide_canvas: bool,
    block_webrtc: bool,
    allow_webgl: bool,
) -> str:
    """Stronger init patches on top of the base stealth script."""
    base = _stealth_init_script(languages, navigator_platform)
    extras: list[str] = []

    if hide_canvas:
        extras.append(
            """
(() => {
  const noise = () => (Math.random() * 0.0001) - 0.00005;
  const patch = (proto, method) => {
    const orig = proto[method];
    if (!orig) return;
    proto[method] = function(...args) {
      const result = orig.apply(this, args);
      if (result && result.data && result.data.length) {
        try {
          for (let i = 0; i < Math.min(48, result.data.length); i += 4) {
            result.data[i] = Math.max(0, Math.min(255, result.data[i] + (Math.random() < 0.08 ? 1 : 0)));
          }
        } catch (_) {}
      }
      return result;
    };
  };
  patch(CanvasRenderingContext2D.prototype, 'getImageData');
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function(...args) {
    try {
      const ctx = this.getContext('2d');
      if (ctx) {
        const w = Math.min(this.width || 0, 16);
        const h = Math.min(this.height || 0, 16);
        if (w && h) {
          const img = ctx.getImageData(0, 0, w, h);
          for (let i = 0; i < img.data.length; i += 4) {
            img.data[i] ^= (Math.random() < 0.02 ? 1 : 0);
          }
          ctx.putImageData(img, 0, 0);
        }
      }
    } catch (_) {}
    return toDataURL.apply(this, args);
  };
})();
"""
        )

    if block_webrtc:
        extras.append(
            """
(() => {
  const noop = () => {};
  const FakePC = function() {
    this.createDataChannel = () => ({ close: noop, send: noop });
    this.createOffer = () => Promise.reject(new Error('WebRTC blocked'));
    this.setLocalDescription = () => Promise.resolve();
    this.close = noop;
    this.onicecandidate = null;
  };
  try { window.RTCPeerConnection = FakePC; } catch (_) {}
  try { window.webkitRTCPeerConnection = FakePC; } catch (_) {}
  try {
    Object.defineProperty(navigator, 'mediaDevices', {
      get: () => ({
        enumerateDevices: async () => [],
        getUserMedia: async () => { throw new Error('Permission denied'); },
      }),
    });
  } catch (_) {}
})();
"""
        )

    if not allow_webgl:
        extras.append(
            """
(() => {
  const block = function() { return null; };
  HTMLCanvasElement.prototype.getContext = new Proxy(HTMLCanvasElement.prototype.getContext, {
    apply(target, thisArg, args) {
      if (args[0] === 'webgl' || args[0] === 'webgl2' || args[0] === 'experimental-webgl') {
        return null;
      }
      return Reflect.apply(target, thisArg, args);
    },
  });
})();
"""
        )
    else:
        # Keep WebGL on but stabilize vendor/renderer (common WAF check).
        extras.append(
            """
(() => {
  const patchParam = (proto) => {
    if (!proto || !proto.getParameter) return;
    const orig = proto.getParameter;
    proto.getParameter = function(param) {
      if (param === 37445) return 'Intel Inc.';
      if (param === 37446) return 'Intel Iris OpenGL Engine';
      return orig.call(this, param);
    };
  };
  try { patchParam(WebGLRenderingContext.prototype); } catch (_) {}
  try { patchParam(WebGL2RenderingContext.prototype); } catch (_) {}
})();
"""
        )

    return base + "\n" + "\n".join(extras)


def detect_cloudflare_challenge(html: str) -> Optional[str]:
    """Return challenge kind: non-interactive | managed | interactive | embedded."""
    for ctype in ("non-interactive", "managed", "interactive"):
        if f"cType: '{ctype}'" in html:
            return ctype
    if TURNSTILE_SCRIPT_RE.search(html) or "cf-turnstile" in html.lower():
        return "embedded"
    lower = html.lower()
    if "just a moment" in lower or "cf-browser-verification" in lower:
        return "managed"
    if any(h in lower for h in ("cf-turnstile", "challenge-platform", "turnstile")):
        return "embedded"
    return None


def _page_has_cf_challenge(page: Page) -> bool:
    try:
        html = page.content()
        title = page.title()
    except Exception:
        return False
    if detect_cloudflare_challenge(html):
        return True
    return _is_challenge_page(html, title)


def _wait_networkidle(page: Page, timeout: int = 5000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def solve_cloudflare_challenge(
    page: Page,
    *,
    timeout_ms: int = 60_000,
    max_rounds: int = 3,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Detect and clear Cloudflare Turnstile / interstitial UI challenges.

    Returns True when the challenge no longer appears on the page.
    """
    _log = log or (lambda _m: None)
    deadline = time.time() + timeout_ms / 1000.0
    viewport = page.viewport_size or {"width": 1280, "height": 900}

    for round_idx in range(max_rounds):
        if time.time() > deadline:
            break

        _wait_networkidle(page, timeout=5000)
        try:
            html = page.content()
        except Exception:
            html = ""

        challenge_type = detect_cloudflare_challenge(html)
        if not challenge_type and not _is_challenge_page(html, page.title()):
            _log("[Stealthy] No Cloudflare challenge detected.")
            return True

        _log(f"[Stealthy] Cloudflare challenge type={challenge_type or 'generic'} (round {round_idx + 1})")

        # Non-interactive: wait for "Just a moment..." to vanish
        if challenge_type == "non-interactive" or (
            challenge_type in (None, "managed") and "just a moment" in html.lower()
        ):
            waited = 0
            while time.time() < deadline and waited < 45:
                try:
                    content = page.content()
                    title = page.title().lower()
                except Exception:
                    break
                if "just a moment" not in content.lower() and "just a moment" not in title:
                    if not _page_has_cf_challenge(page):
                        _log("[Stealthy] Non-interactive challenge cleared.")
                        return True
                    break
                page.wait_for_timeout(1000)
                waited += 1
                if random.random() < 0.35:
                    _simulate_human(page, viewport)
            if not _page_has_cf_challenge(page):
                return True

        # Interactive / embedded: click Turnstile checkbox
        _click_turnstile_checkbox(page, challenge_type or "embedded", _log)

        # Poll for clearance
        poll = 0
        while time.time() < deadline and poll < 100:
            page.wait_for_timeout(100)
            poll += 1
            try:
                content = page.content()
                title = page.title()
            except Exception:
                continue
            if "just a moment" in content.lower() or "just a moment" in title.lower():
                continue
            if not detect_cloudflare_challenge(content) and not _is_challenge_page(content, title):
                # Prefer seeing cf_clearance when available
                try:
                    cookies = page.context.cookies()
                    if any(c.get("name") == "cf_clearance" for c in cookies):
                        _log("[Stealthy] cf_clearance cookie present — challenge solved.")
                        return True
                except Exception:
                    pass
                _log("[Stealthy] Challenge page cleared.")
                return True
            if poll % 15 == 0:
                _simulate_human(page, viewport)

        if not _page_has_cf_challenge(page):
            return True
        _log("[Stealthy] Challenge still present — retrying …")

    ok = not _page_has_cf_challenge(page)
    _log("[Stealthy] Cloudflare solve finished ok=" + str(ok))
    return ok


def _click_turnstile_checkbox(
    page: Page, challenge_type: str, log: Callable[[str], None]
) -> None:
    """Human-like click on the Cloudflare Turnstile checkbox / iframe."""
    # Wait for verifying spinner to leave
    for _ in range(20):
        try:
            body = page.content()
        except Exception:
            break
        if "verifying you are human" not in body.lower():
            break
        page.wait_for_timeout(500)

    outer_box: Optional[dict] = None
    iframe = None
    try:
        iframe = page.frame(url=CF_FRAME_RE)
    except Exception:
        iframe = None

    if iframe is not None:
        try:
            _wait_networkidle(iframe, timeout=4000)  # type: ignore[arg-type]
        except Exception:
            pass
        if challenge_type != "embedded":
            for _ in range(20):
                try:
                    el = iframe.frame_element()
                    if el.is_visible():
                        outer_box = el.bounding_box()
                        break
                except Exception:
                    pass
                page.wait_for_timeout(500)
        else:
            try:
                outer_box = iframe.frame_element().bounding_box()
            except Exception:
                outer_box = None

    if not outer_box:
        selectors = [
            "#cf_turnstile div",
            "#cf-turnstile div",
            ".turnstile > div > div",
            ".main-content p + div > div > div",
            "iframe[src*='challenges.cloudflare.com']",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).last
                if loc.count() == 0:
                    continue
                box = loc.bounding_box()
                if box:
                    outer_box = box
                    break
            except Exception:
                continue

    if not outer_box:
        # Soft human noise even if we cannot find the box yet
        vp = page.viewport_size or {"width": 1280, "height": 900}
        _simulate_human(page, vp)
        log("[Stealthy] Turnstile box not found — waited with human mouse noise.")
        return

    x = outer_box["x"] + random.randint(26, 28)
    y = outer_box["y"] + random.randint(25, 27)
    # Approach from a nearby point for less robotic motion
    page.mouse.move(
        x + random.randint(-40, -10),
        y + random.randint(-30, 10),
        steps=random.randint(12, 24),
    )
    page.wait_for_timeout(random.randint(80, 200))
    page.mouse.click(x, y, delay=random.randint(100, 220), button="left")
    log(f"[Stealthy] Clicked Turnstile at ({x:.0f}, {y:.0f}).")
    _wait_networkidle(page, timeout=8000)


@dataclass
class _StealthOptions:
    headless: bool = True
    real_chrome: bool = True
    solve_cloudflare: bool = True
    hide_canvas: bool = True
    block_webrtc: bool = True
    allow_webgl: bool = True
    disable_resources: bool = False
    network_idle: bool = False
    load_dom: bool = True
    timeout: int = DEFAULT_TIMEOUT_MS
    wait: int = DEFAULT_WAIT_MS
    wait_selector: Optional[str] = None
    wait_selector_state: str = "attached"
    useragent: Optional[str] = None
    cookies: CookieInput = None
    locale: Optional[str] = None
    timezone_id: Optional[str] = None
    proxy: ProxyInput = None
    google_search: bool = True
    extra_headers: Optional[Mapping[str, str]] = None
    extra_flags: Optional[Sequence[str]] = None
    init_script: Optional[str] = None
    page_action: Optional[PageAction] = None
    page_setup: Optional[PageAction] = None
    cdp_url: Optional[str] = None
    additional_args: Optional[Mapping[str, Any]] = None
    viewport: Optional[Mapping[str, int]] = None
    user_data_dir: Optional[str] = None
    humanize: bool = True


class StealthySession:
    """Persistent stealth browser session (patchright preferred)."""

    def __init__(self, **kwargs: Any) -> None:
        real_chrome = _as_bool_chrome(kwargs)
        solve_cf = bool(kwargs.pop("solve_cloudflare", True))
        # Scrapling auto-enables humanize with CF solver
        humanize = bool(kwargs.pop("humanize", solve_cf or True))
        timeout = int(kwargs.pop("timeout", DEFAULT_TIMEOUT_MS if solve_cf else 30_000))

        self.opts = _StealthOptions(
            headless=bool(kwargs.pop("headless", True)),
            real_chrome=real_chrome,
            solve_cloudflare=solve_cf,
            hide_canvas=bool(kwargs.pop("hide_canvas", True)),
            block_webrtc=bool(kwargs.pop("block_webrtc", True)),
            allow_webgl=bool(kwargs.pop("allow_webgl", True)),
            disable_resources=bool(kwargs.pop("disable_resources", False)),
            network_idle=bool(kwargs.pop("network_idle", False)),
            load_dom=bool(kwargs.pop("load_dom", True)),
            timeout=timeout,
            wait=int(kwargs.pop("wait", DEFAULT_WAIT_MS)),
            wait_selector=kwargs.pop("wait_selector", None),
            wait_selector_state=str(kwargs.pop("wait_selector_state", "attached")),
            useragent=kwargs.pop("useragent", None),
            cookies=kwargs.pop("cookies", None),
            locale=kwargs.pop("locale", None),
            timezone_id=kwargs.pop("timezone_id", None),
            proxy=kwargs.pop("proxy", None),
            google_search=bool(kwargs.pop("google_search", True)),
            extra_headers=kwargs.pop("extra_headers", None),
            extra_flags=kwargs.pop("extra_flags", None),
            init_script=kwargs.pop("init_script", None),
            page_action=kwargs.pop("page_action", None),
            page_setup=kwargs.pop("page_setup", None),
            cdp_url=kwargs.pop("cdp_url", None),
            additional_args=kwargs.pop("additional_args", None),
            viewport=kwargs.pop("viewport", None) or {"width": 1920, "height": 1080},
            user_data_dir=kwargs.pop("user_data_dir", None),
            humanize=humanize,
        )
        for soft in (
            "selector_config",
            "custom_config",
            "block_ads",
            "blocked_domains",
            "dns_over_https",
            "simulate_stealth",
        ):
            kwargs.pop(soft, None)
        if kwargs:
            extra = dict(self.opts.additional_args or {})
            extra.update(kwargs)
            self.opts.additional_args = extra

        self._pw: Any = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._temp_profile: Optional[str] = None
        self._engine = ENGINE_NAME
        self._browser_label = ""
        self._entered = False
        self._log: Callable[[str], None] = lambda _m: None

    def set_logger(self, log: Callable[[str], None]) -> None:
        self._log = log

    def __enter__(self) -> "StealthySession":
        if self._entered:
            raise RuntimeError("StealthySession already entered")
        self._pw = _sync_playwright().start()
        self._browser, self._context, self._browser_label = self._launch(self._pw)
        self._entered = True
        self._log(
            f"[Stealthy] Engine={self._engine} browser={self._browser_label} "
            f"patchright={HAS_PATCHRIGHT}"
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
        self._context = None
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
        self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._pw = None
        if self._temp_profile:
            try:
                import shutil

                shutil.rmtree(self._temp_profile, ignore_errors=True)
            except Exception:
                pass
            self._temp_profile = None
        self._entered = False

    def _stealth_args(self) -> list[str]:
        args = list(dict.fromkeys([*BROWSER_ARGS, *STEALTH_LAUNCH_FLAGS]))
        # QUIC can look odd behind some proxies; keep optional — do not force disable
        if self.opts.block_webrtc:
            args.extend(
                [
                    "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                    "--force-webrtc-ip-handling-policy",
                ]
            )
        if not self.opts.allow_webgl:
            args.extend(
                [
                    "--disable-webgl",
                    "--disable-webgl-image-chromium",
                    "--disable-webgl2",
                ]
            )
        if self.opts.hide_canvas:
            # Supported on Chromium builds that ship fingerprinting-canvas noise
            args.append("--fingerprinting-canvas-image-data-noise")
        if self.opts.extra_flags:
            args.extend(str(f) for f in self.opts.extra_flags)
        return args

    def _launch(self, pw: Playwright) -> tuple[Optional[Browser], BrowserContext, str]:
        opts = self.opts
        if opts.cdp_url:
            browser = pw.chromium.connect_over_cdp(opts.cdp_url)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            return browser, ctx, "cdp"

        profile = _pick_profile(opts.useragent, opts.locale, opts.viewport)
        if opts.timezone_id:
            profile["timezone"] = opts.timezone_id

        args = self._stealth_args()
        proxy = _normalize_proxy(opts.proxy)
        launch_kwargs: dict[str, Any] = {
            "headless": opts.headless,
            "args": args,
            "ignore_default_args": ["--enable-automation"],
        }
        if proxy:
            launch_kwargs["proxy"] = proxy

        user_data = opts.user_data_dir
        if not user_data:
            self._temp_profile = tempfile.mkdtemp(prefix="stealthy_profile_")
            user_data = self._temp_profile

        ctx_kwargs: dict[str, Any] = {
            "user_agent": profile["ua"],
            "viewport": {
                "width": int(profile["viewport"]["width"]),
                "height": int(profile["viewport"]["height"]),
            },
            "screen": {"width": 1920, "height": 1080},
            "locale": profile["locale"],
            "timezone_id": profile["timezone"],
            "color_scheme": "dark",
            "device_scale_factor": 2,
            "has_touch": False,
            "is_mobile": False,
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "permissions": ["geolocation", "notifications"],
            "service_workers": "allow",
        }
        if opts.additional_args:
            ctx_kwargs.update(dict(opts.additional_args))

        errors: list[str] = []

        def try_persistent(channel: Optional[str]) -> Optional[tuple[BrowserContext, str]]:
            kw = {**launch_kwargs, **ctx_kwargs, "user_data_dir": user_data}
            if channel:
                kw["channel"] = channel
            try:
                ctx = pw.chromium.launch_persistent_context(**kw)
                label = channel or "chromium"
                return ctx, label
            except Exception as exc:
                errors.append(f"persistent/{channel or 'chromium'}: {exc}")
                return None

        def try_ephemeral(channel: Optional[str]) -> Optional[tuple[Browser, BrowserContext, str]]:
            kw = dict(launch_kwargs)
            if channel:
                kw["channel"] = channel
            try:
                browser = pw.chromium.launch(**kw)
                ctx = browser.new_context(**ctx_kwargs)
                return browser, ctx, channel or "chromium"
            except Exception as exc:
                errors.append(f"ephemeral/{channel or 'chromium'}: {exc}")
                return None

        # Prefer persistent context (more realistic cookies / storage)
        order: list[Optional[str]] = []
        if opts.real_chrome:
            order.extend(["chrome", None])
        else:
            order.extend([None, "chrome"])

        for channel in order:
            got = try_persistent(channel)
            if got:
                ctx, label = got
                self._apply_init_scripts(ctx, profile, url_hint="https://example.com")
                return None, ctx, label

        for channel in order:
            got_e = try_ephemeral(channel)
            if got_e:
                browser, ctx, label = got_e
                self._apply_init_scripts(ctx, profile, url_hint="https://example.com")
                return browser, ctx, label

        raise FetchError(
            "Unable to launch stealth browser: "
            + (" | ".join(errors) or "unknown")
            + ". Install Google Chrome or run: python -m playwright install chromium"
            + (" (and pip install patchright)" if not HAS_PATCHRIGHT else "")
        )

    def _apply_init_scripts(
        self, ctx: BrowserContext, profile: dict, url_hint: str
    ) -> None:
        opts = self.opts
        headers = _build_headers(
            profile["ua"], url_hint, profile["languages"], profile["platform"]
        )
        if opts.google_search:
            headers["Referer"] = "https://www.google.com/"
        if opts.extra_headers:
            headers.update({str(k): str(v) for k, v in opts.extra_headers.items()})
        try:
            ctx.set_extra_http_headers(headers)
        except Exception:
            pass

        ctx.add_init_script(
            _fingerprint_init_script(
                languages=profile["languages"],
                navigator_platform=profile["navigator_platform"],
                hide_canvas=opts.hide_canvas,
                block_webrtc=opts.block_webrtc,
                allow_webgl=opts.allow_webgl,
            )
        )
        if opts.init_script:
            path = Path(opts.init_script)
            if path.is_file():
                ctx.add_init_script(path=str(path))
            else:
                ctx.add_init_script(opts.init_script)

    def fetch(self, url: str, **overrides: Any) -> DynamicFetchResult:
        if not url or not str(url).strip():
            raise FetchError("URL is required")
        url = str(url).strip()

        owns = False
        if not self._entered:
            self.__enter__()
            owns = True

        assert self._context is not None
        opts = self.opts
        # lightweight per-call overrides
        solve_cf = bool(overrides.pop("solve_cloudflare", opts.solve_cloudflare))
        wait = int(overrides.pop("wait", opts.wait))
        network_idle = bool(overrides.pop("network_idle", opts.network_idle))
        wait_selector = overrides.pop("wait_selector", opts.wait_selector)
        page_action = overrides.pop("page_action", opts.page_action)
        page_setup = overrides.pop("page_setup", opts.page_setup)
        extra_headers = overrides.pop("extra_headers", None)

        started = time.perf_counter()
        page = self._context.new_page()
        page.set_default_timeout(opts.timeout)

        try:
            if HAS_STEALTH:
                try:
                    _stealth.apply_stealth_sync(page)
                except Exception:
                    pass

            if opts.disable_resources:
                _block_heavy_resources(page)

            if extra_headers:
                page.set_extra_http_headers(
                    {str(k): str(v) for k, v in dict(extra_headers).items()}
                )

            _inject_cookies(self._context, opts.cookies, url)

            if page_setup:
                page_setup(page)

            wait_until = "load" if opts.load_dom else "domcontentloaded"
            response: Optional[PWResponse] = page.goto(
                url, wait_until=wait_until, timeout=opts.timeout
            )

            if opts.humanize:
                vp = page.viewport_size or {"width": 1280, "height": 900}
                _simulate_human(page, vp)

            if network_idle:
                _wait_networkidle(page, timeout=min(opts.timeout, 15_000))

            solved = False
            if solve_cf and _page_has_cf_challenge(page):
                solved = solve_cloudflare_challenge(
                    page,
                    timeout_ms=min(opts.timeout, 90_000),
                    log=self._log,
                )

            if wait_selector:
                page.wait_for_selector(
                    wait_selector,
                    state=opts.wait_selector_state,  # type: ignore[arg-type]
                    timeout=opts.timeout,
                )

            if page_action:
                page_action(page)

            if wait > 0:
                page.wait_for_timeout(int(wait))

            html = page.content()
            title = page.title()
            final_url = page.url or url
            status = int(response.status) if response is not None else 200
            hdrs: dict[str, str] = {}
            if response is not None:
                try:
                    hdrs = {k: v for k, v in response.headers.items()}
                except Exception:
                    pass

            still_challenged = _page_has_cf_challenge(page)
            elapsed = time.perf_counter() - started
            return DynamicFetchResult(
                url=final_url,
                status_code=status,
                headers=hdrs,
                content=html.encode("utf-8", errors="replace"),
                text=html,
                elapsed=elapsed,
                ok=200 <= status < 400 and not still_challenged,
                title=title,
                browser_engine=f"{self._engine}:{self._browser_label}",
                final_url=final_url,
                extras={
                    "title": title,
                    "browser": self._browser_label,
                    "engine": self._engine,
                    "patchright": HAS_PATCHRIGHT,
                    "cloudflare_solved": solved,
                    "cloudflare_remaining": still_challenged,
                    "headless": opts.headless,
                    "hide_canvas": opts.hide_canvas,
                    "block_webrtc": opts.block_webrtc,
                    "allow_webgl": opts.allow_webgl,
                },
            )
        except Exception as exc:
            raise FetchError(f"StealthyFetcher failed for {url}: {exc}") from exc
        finally:
            try:
                page.close()
            except Exception:
                pass
            if owns:
                self.close()


class StealthyFetcher:
    """Advanced stealth browser fetch with fingerprint spoofing + CF bypass.

    Example::

        from stealthy_fetcher import StealthyFetcher

        r = StealthyFetcher.fetch(
            "https://protected.example",
            solve_cloudflare=True,
            hide_canvas=True,
            block_webrtc=True,
            real_chrome=True,
            headless=True,
            timeout=60000,
        )
        print(r.title, r.extras.get("cloudflare_solved"))
    """

    _defaults: dict[str, Any] = {
        "real_chrome": True,
        "headless": True,
        "solve_cloudflare": True,
        "hide_canvas": True,
        "block_webrtc": True,
        "allow_webgl": True,
        "timeout": DEFAULT_TIMEOUT_MS,
        "google_search": True,
        "humanize": True,
    }

    @classmethod
    def configure(cls, **kwargs: Any) -> None:
        cls._defaults.update(kwargs)

    @classmethod
    def backend(cls) -> str:
        return ENGINE_NAME

    @classmethod
    def has_patchright(cls) -> bool:
        return HAS_PATCHRIGHT

    @classmethod
    def fetch(cls, url: str, **kwargs: Any) -> DynamicFetchResult:
        opts = {**cls._defaults, **kwargs}
        log = opts.pop("log", None)
        with StealthySession(**opts) as session:
            if log:
                session.set_logger(log)
            return session.fetch(url)

    get = fetch
