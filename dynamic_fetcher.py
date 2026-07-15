#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dynamic page loader via Playwright — Chromium or system Google Chrome.

Complement to the stealth HTTP ``Fetcher``: use this when the page needs a
real browser (JavaScript, SPAs, lazy content). API shaped after Scrapling's
``DynamicFetcher``.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response as PWResponse,
    sync_playwright,
)

from fetcher import FetchError, FetchResponse

try:
    from playwright_stealth import Stealth

    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# Reuse hardened launch defaults from the main scrape pipeline.
from scraper_core import (  # noqa: E402
    BROWSER_ARGS,
    BROWSER_PROFILES,
    _build_headers,
    _parse_cookies,
    _parse_proxy,
    _stealth_init_script,
)

PageAction = Callable[[Page], Any]
CookieInput = Union[str, Sequence[Mapping[str, Any]], None]
ProxyInput = Union[str, Mapping[str, str], None]

DEFAULT_TIMEOUT_MS = 30_000
DEFAULT_WAIT_MS = 0


@dataclass
class DynamicFetchResult(FetchResponse):
    """Browser-rendered response with useful page metadata in ``extras``."""

    title: str = ""
    browser_engine: str = ""  # "chrome" | "chromium"
    final_url: str = ""


@dataclass
class _SessionOptions:
    headless: bool = True
    real_chrome: bool = True
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
    proxy: ProxyInput = None
    google_search: bool = True
    extra_headers: Optional[Mapping[str, str]] = None
    extra_flags: Optional[Sequence[str]] = None
    init_script: Optional[str] = None
    page_action: Optional[PageAction] = None
    page_setup: Optional[PageAction] = None
    cdp_url: Optional[str] = None
    additional_args: Optional[Mapping[str, Any]] = None
    simulate_stealth: bool = True
    viewport: Optional[Mapping[str, int]] = None


def _as_bool_chrome(kwargs: dict[str, Any]) -> bool:
    """Accept Scrapling ``real_chrome`` or project ``use_chrome``."""
    if "real_chrome" in kwargs:
        return bool(kwargs.pop("real_chrome"))
    if "use_chrome" in kwargs:
        return bool(kwargs.pop("use_chrome"))
    return True


def _normalize_proxy(proxy: ProxyInput) -> Optional[dict]:
    if not proxy:
        return None
    if isinstance(proxy, Mapping):
        server = str(proxy.get("server") or "").strip()
        if not server:
            return None
        out: dict[str, str] = {"server": server}
        if proxy.get("username"):
            out["username"] = str(proxy["username"])
        if proxy.get("password"):
            out["password"] = str(proxy["password"])
        return out
    return _parse_proxy(str(proxy))


def _pick_profile(
    useragent: Optional[str],
    locale: Optional[str],
    viewport: Optional[Mapping[str, int]],
) -> dict:
    profile = dict(random.choice(BROWSER_PROFILES))
    if useragent:
        profile["ua"] = useragent
    if locale:
        profile["locale"] = locale
    if viewport:
        profile["viewport"] = {
            "width": int(viewport.get("width", 1280)),
            "height": int(viewport.get("height", 720)),
        }
    return profile


def _inject_cookies(ctx: BrowserContext, cookies: CookieInput, url: str) -> None:
    if not cookies:
        return
    if isinstance(cookies, str):
        parsed = _parse_cookies(cookies, url)
        if parsed:
            ctx.add_cookies(parsed)
        return
    items: list[dict[str, Any]] = []
    for item in cookies:
        c = dict(item)
        if "url" not in c and "domain" not in c:
            c["url"] = url
        items.append(c)
    if items:
        ctx.add_cookies(items)


def _block_heavy_resources(page: Page) -> None:
    blocked = {"image", "media", "font", "stylesheet"}

    def handler(route: Any) -> None:
        if route.request.resource_type in blocked:
            route.abort()
        else:
            route.continue_()

    page.route("**/*", handler)


class DynamicSession:
    """Reusable Playwright session (Chromium or system Chrome)."""

    def __init__(self, **kwargs: Any) -> None:
        real_chrome = _as_bool_chrome(kwargs)
        self.opts = _SessionOptions(
            headless=bool(kwargs.pop("headless", True)),
            real_chrome=real_chrome,
            disable_resources=bool(kwargs.pop("disable_resources", False)),
            network_idle=bool(kwargs.pop("network_idle", False)),
            load_dom=bool(kwargs.pop("load_dom", True)),
            timeout=int(kwargs.pop("timeout", DEFAULT_TIMEOUT_MS)),
            wait=int(kwargs.pop("wait", DEFAULT_WAIT_MS)),
            wait_selector=kwargs.pop("wait_selector", None),
            wait_selector_state=str(kwargs.pop("wait_selector_state", "attached")),
            useragent=kwargs.pop("useragent", None),
            cookies=kwargs.pop("cookies", None),
            locale=kwargs.pop("locale", None),
            proxy=kwargs.pop("proxy", None),
            google_search=bool(kwargs.pop("google_search", True)),
            extra_headers=kwargs.pop("extra_headers", None),
            extra_flags=kwargs.pop("extra_flags", None),
            init_script=kwargs.pop("init_script", None),
            page_action=kwargs.pop("page_action", None),
            page_setup=kwargs.pop("page_setup", None),
            cdp_url=kwargs.pop("cdp_url", None),
            additional_args=kwargs.pop("additional_args", None),
            simulate_stealth=bool(kwargs.pop("simulate_stealth", True)),
            viewport=kwargs.pop("viewport", None),
        )
        # Ignore Scrapling-only knobs so callers can pass them safely.
        kwargs.pop("selector_config", None)
        kwargs.pop("custom_config", None)
        kwargs.pop("block_ads", None)
        kwargs.pop("blocked_domains", None)
        kwargs.pop("dns_over_https", None)
        if kwargs:
            # Keep forward-compatible: stash unknown keys into additional_args
            extra = dict(self.opts.additional_args or {})
            extra.update(kwargs)
            self.opts.additional_args = extra

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._owns_browser = False
        self._browser_engine = ""
        self._entered = False

    def __enter__(self) -> "DynamicSession":
        if self._entered:
            raise RuntimeError("DynamicSession already entered")
        self._pw = sync_playwright().start()
        self._browser, self._browser_engine = self._launch(self._pw)
        self._owns_browser = True
        self._entered = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._browser is not None and self._owns_browser:
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
        self._entered = False

    def _launch(self, pw: Playwright) -> tuple[Browser, str]:
        opts = self.opts
        if opts.cdp_url:
            browser = pw.chromium.connect_over_cdp(opts.cdp_url)
            return browser, "cdp"

        args = list(BROWSER_ARGS)
        if opts.extra_flags:
            args.extend(str(f) for f in opts.extra_flags)

        launch_kwargs: dict[str, Any] = {
            "headless": opts.headless,
            "args": args,
        }
        proxy = _normalize_proxy(opts.proxy)
        if proxy:
            launch_kwargs["proxy"] = proxy

        errors: list[str] = []

        def try_chrome() -> Optional[Browser]:
            try:
                return pw.chromium.launch(channel="chrome", **launch_kwargs)
            except Exception as exc:
                errors.append(f"chrome: {exc}")
                return None

        def try_chromium() -> Optional[Browser]:
            try:
                return pw.chromium.launch(**launch_kwargs)
            except Exception as exc:
                errors.append(f"chromium: {exc}")
                return None

        if opts.real_chrome:
            browser = try_chrome()
            if browser is not None:
                return browser, "chrome"
            browser = try_chromium()
            if browser is not None:
                return browser, "chromium"
        else:
            browser = try_chromium()
            if browser is not None:
                return browser, "chromium"
            # Dev machines often have Chrome but no Playwright Chromium bundle.
            browser = try_chrome()
            if browser is not None:
                return browser, "chrome"

        hint = (
            "Install system Google Chrome, or run: python -m playwright install chromium"
        )
        detail = " | ".join(errors) if errors else "unknown launch error"
        raise FetchError(f"Unable to launch browser ({detail}). {hint}")

    def _new_context(self, browser: Browser, url: str) -> BrowserContext:
        opts = self.opts
        profile = _pick_profile(opts.useragent, opts.locale, opts.viewport)
        viewport = profile["viewport"]
        headers = _build_headers(
            profile["ua"], url, profile["languages"], profile["platform"]
        )
        if opts.google_search and "Referer" not in (opts.extra_headers or {}):
            headers["Referer"] = "https://www.google.com/"
        if opts.extra_headers:
            headers.update({str(k): str(v) for k, v in opts.extra_headers.items()})

        ctx_kwargs: dict[str, Any] = {
            "user_agent": profile["ua"],
            "viewport": {"width": viewport["width"], "height": viewport["height"]},
            "screen": {"width": viewport["width"], "height": viewport["height"]},
            "locale": profile["locale"],
            "timezone_id": profile["timezone"],
            "color_scheme": "light",
            "java_script_enabled": True,
            "ignore_https_errors": True,
            "extra_http_headers": headers,
        }
        if opts.additional_args:
            ctx_kwargs.update(dict(opts.additional_args))

        ctx = browser.new_context(**ctx_kwargs)
        if opts.simulate_stealth:
            ctx.add_init_script(
                _stealth_init_script(profile["languages"], profile["navigator_platform"])
            )
        if opts.init_script:
            path = Path(opts.init_script)
            if path.is_file():
                ctx.add_init_script(path=str(path))
            else:
                ctx.add_init_script(opts.init_script)
        _inject_cookies(ctx, opts.cookies, url)
        return ctx

    def fetch(self, url: str, **overrides: Any) -> DynamicFetchResult:
        """Navigate and return the rendered page as a ``DynamicFetchResult``."""
        if not url or not str(url).strip():
            raise FetchError("URL is required")
        url = str(url).strip()

        # Per-call overrides (shallow) without mutating session defaults permanently
        saved = self.opts
        if overrides:
            merged = field_replace(saved, **_overrides_to_opts(overrides))
            self.opts = merged

        started = time.perf_counter()
        owns_runtime = False
        try:
            if not self._entered:
                self.__enter__()
                owns_runtime = True

            assert self._browser is not None
            browser = self._browser
            engine = self._browser_engine or "chromium"
            ctx = self._new_context(browser, url)
            page = ctx.new_page()
            page.set_default_timeout(self.opts.timeout)

            try:
                if HAS_STEALTH and self.opts.simulate_stealth:
                    _stealth.apply_stealth_sync(page)

                if self.opts.disable_resources:
                    _block_heavy_resources(page)

                if self.opts.page_setup:
                    self.opts.page_setup(page)

                wait_until = "load" if self.opts.load_dom else "domcontentloaded"
                response: Optional[PWResponse] = page.goto(
                    url, wait_until=wait_until, timeout=self.opts.timeout
                )

                if self.opts.network_idle:
                    try:
                        page.wait_for_load_state(
                            "networkidle", timeout=self.opts.timeout
                        )
                    except Exception:
                        pass

                if self.opts.wait_selector:
                    page.wait_for_selector(
                        self.opts.wait_selector,
                        state=self.opts.wait_selector_state,  # type: ignore[arg-type]
                        timeout=self.opts.timeout,
                    )

                if self.opts.page_action:
                    self.opts.page_action(page)

                if self.opts.wait and self.opts.wait > 0:
                    page.wait_for_timeout(int(self.opts.wait))

                html = page.content()
                title = page.title()
                final_url = page.url or url
                status = int(response.status) if response is not None else 200
                hdrs = {}
                if response is not None:
                    try:
                        hdrs = {k: v for k, v in response.headers.items()}
                    except Exception:
                        hdrs = {}

                elapsed = time.perf_counter() - started
                return DynamicFetchResult(
                    url=final_url,
                    status_code=status,
                    headers=hdrs,
                    content=html.encode("utf-8", errors="replace"),
                    text=html,
                    http_version="",
                    elapsed=elapsed,
                    ok=200 <= status < 400,
                    title=title,
                    browser_engine=engine,
                    final_url=final_url,
                    extras={
                        "title": title,
                        "browser": engine,
                        "engine": "playwright",
                        "headless": self.opts.headless,
                    },
                )
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
        except Exception as exc:
            raise FetchError(f"DynamicFetcher failed for {url}: {exc}") from exc
        finally:
            self.opts = saved
            if owns_runtime:
                self.close()


def _overrides_to_opts(overrides: dict[str, Any]) -> dict[str, Any]:
    """Map public kwargs into ``_SessionOptions`` field names."""
    out = dict(overrides)
    if "real_chrome" in out or "use_chrome" in out:
        out["real_chrome"] = _as_bool_chrome(out)
    allowed = {f.name for f in _SessionOptions.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    return {k: v for k, v in out.items() if k in allowed}


def field_replace(opts: _SessionOptions, **changes: Any) -> _SessionOptions:
    data = {f.name: getattr(opts, f.name) for f in opts.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    data.update(changes)
    return _SessionOptions(**data)


class DynamicFetcher:
    """Fetch JS-rendered pages with Playwright Chromium or Google Chrome.

    Example::

        from dynamic_fetcher import DynamicFetcher

        r = DynamicFetcher.fetch(
            "https://spa.example.com",
            real_chrome=True,   # system Google Chrome; False → bundled Chromium
            headless=True,
            network_idle=True,
            wait=1500,
            wait_selector="main",
        )
        print(r.title, r.status_code, len(r.text))
    """

    _defaults: dict[str, Any] = {
        "real_chrome": True,
        "headless": True,
        "timeout": DEFAULT_TIMEOUT_MS,
        "wait": DEFAULT_WAIT_MS,
        "load_dom": True,
        "google_search": True,
        "simulate_stealth": True,
    }

    @classmethod
    def configure(cls, **kwargs: Any) -> None:
        cls._defaults.update(kwargs)

    @classmethod
    def fetch(cls, url: str, **kwargs: Any) -> DynamicFetchResult:
        opts = {**cls._defaults, **kwargs}
        with DynamicSession(**opts) as session:
            return session.fetch(url)

    # Scrapling alias
    get = fetch


# Backward-compatible alias used by some Scrapling docs
PlayWrightFetcher = DynamicFetcher
