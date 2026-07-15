#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stealth HTTP client — browser TLS fingerprint + headers, optional HTTP/3.

Built on ``curl_cffi`` (curl-impersonate). Falls back to ``urllib`` when the
optional dependency is missing, so the rest of the app still works.
"""

from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Union
from urllib.parse import urlparse

try:
    from curl_cffi import CurlHttpVersion
    from curl_cffi.requests import Session as CurlSession

    HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover
    CurlHttpVersion = None  # type: ignore[assignment, misc]
    CurlSession = None  # type: ignore[assignment, misc]
    HAS_CURL_CFFI = False

ImpersonateType = Union[str, Sequence[str], None]

# curl_cffi / libcurl http_version numeric codes → label
_HTTP_VERSION_LABELS = {
    1: "1.0",
    2: "1.1",
    3: "2",
    30: "3",
}

DEFAULT_IMPERSONATE = "chrome"
DEFAULT_TIMEOUT = 30.0

# Realistic Accept / language / fetch metadata when stealthy_headers=True.
# When impersonate is on, curl_cffi already injects matching UA / sec-ch-ua;
# we only fill gaps and add navigation-like metadata.
_STEALTH_BASE_HEADERS: dict[str, str] = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_FALLBACK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class FetchResponse:
    """Minimal response object shared by curl_cffi and urllib backends."""

    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes
    text: str = ""
    http_version: str = ""
    elapsed: float = 0.0
    ok: bool = True
    extras: dict[str, Any] = field(default_factory=dict)

    def json(self) -> Any:
        if self.text:
            return json.loads(self.text)
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise FetchError(f"HTTP {self.status_code} for {self.url}")


class FetchError(RuntimeError):
    """Raised when a Fetcher request fails."""


def _pick_impersonate(impersonate: ImpersonateType) -> Optional[str]:
    if impersonate is None:
        return None
    if isinstance(impersonate, (list, tuple)):
        if not impersonate:
            return None
        return random.choice(list(impersonate))
    return str(impersonate)


def _header_keys(headers: Mapping[str, str]) -> set[str]:
    return {k.lower() for k in headers}


def build_stealth_headers(
    url: str,
    headers: Optional[Mapping[str, str]] = None,
    *,
    stealthy_headers: bool = True,
    impersonate_enabled: bool = True,
    referer: Optional[str] = None,
) -> dict[str, str]:
    """Merge caller headers with browser-like defaults."""
    final: dict[str, str] = dict(headers or {})
    keys = _header_keys(final)

    if stealthy_headers:
        for key, value in _STEALTH_BASE_HEADERS.items():
            if key.lower() not in keys:
                final[key] = value
                keys.add(key.lower())

        if "referer" not in keys:
            if referer:
                final["Referer"] = referer
            else:
                # Soft provenance signal often seen from search → site navigations.
                final["Referer"] = "https://www.google.com/"
            keys.add("referer")

        # Same-site API / CDN style requests
        dest = urlparse(url)
        ref = final.get("Referer") or final.get("referer") or ""
        if ref and dest.netloc:
            ref_host = urlparse(ref).netloc
            if ref_host and ref_host == dest.netloc:
                final["Sec-Fetch-Site"] = "same-origin"
            elif ref_host:
                final["Sec-Fetch-Site"] = "cross-site"

    if not impersonate_enabled and "user-agent" not in keys:
        final["User-Agent"] = _FALLBACK_UA

    return final


def _normalize_proxy(proxy: Optional[str]) -> Optional[str]:
    proxy = (proxy or "").strip()
    return proxy or None


def _response_from_curl(resp: Any) -> FetchResponse:
    headers = {str(k): str(v) for k, v in dict(resp.headers or {}).items()}
    content = resp.content or b""
    text = getattr(resp, "text", None) or ""
    version = ""
    http_ver = getattr(resp, "http_version", None)
    if http_ver is not None:
        try:
            code = int(http_ver)
            version = _HTTP_VERSION_LABELS.get(code, str(code))
        except (TypeError, ValueError):
            version = str(http_ver)
    elapsed = float(getattr(getattr(resp, "elapsed", None), "total_seconds", lambda: 0.0)())
    return FetchResponse(
        url=str(getattr(resp, "url", "") or ""),
        status_code=int(resp.status_code),
        headers=headers,
        content=content,
        text=text,
        http_version=version,
        elapsed=elapsed,
        ok=200 <= int(resp.status_code) < 400,
    )


def _urllib_request(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    data: Optional[bytes] = None,
    timeout: float = DEFAULT_TIMEOUT,
    proxy: Optional[str] = None,
    allow_redirects: bool = True,
) -> FetchResponse:
    req = urllib.request.Request(url, data=data, headers=dict(headers), method=method.upper())
    handlers: list[Any] = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    if not allow_redirects:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                return None

        handlers.append(_NoRedirect())
    opener = urllib.request.build_opener(*handlers) if handlers else urllib.request.build_opener()
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read()
            hdrs = {k: v for k, v in resp.headers.items()}
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(charset, errors="replace")
            except Exception:
                text = body.decode("utf-8", errors="replace")
            return FetchResponse(
                url=resp.geturl(),
                status_code=getattr(resp, "status", 200) or 200,
                headers=hdrs,
                content=body,
                text=text,
                http_version="1.1",
                ok=True,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        try:
            text = body.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return FetchResponse(
            url=url,
            status_code=int(exc.code),
            headers={k: v for k, v in (exc.headers or {}).items()},
            content=body,
            text=text,
            http_version="1.1",
            ok=False,
        )


class _FetcherCore:
    """Shared request logic for one-shot and session-based Fetcher."""

    def __init__(
        self,
        *,
        impersonate: ImpersonateType = DEFAULT_IMPERSONATE,
        stealthy_headers: bool = True,
        http3: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        proxy: Optional[str] = None,
        proxies: Optional[Mapping[str, str]] = None,
        headers: Optional[Mapping[str, str]] = None,
        retries: int = 2,
        follow_redirects: bool = True,
        verify: bool = True,
        default_headers: bool = True,
    ) -> None:
        self.impersonate = impersonate
        self.stealthy_headers = stealthy_headers
        self.http3 = http3
        self.timeout = timeout
        self.proxy = _normalize_proxy(proxy)
        self.proxies = dict(proxies or {})
        self.headers = dict(headers or {})
        self.retries = max(0, int(retries))
        self.follow_redirects = follow_redirects
        self.verify = verify
        self.default_headers = default_headers
        self._session: Any = None

    def attach_session(self, session: Any) -> None:
        self._session = session

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        data: Any = None,
        json_body: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        cookies: Optional[Mapping[str, str]] = None,
        impersonate: ImpersonateType = ...,  # type: ignore[assignment]
        stealthy_headers: Optional[bool] = None,
        http3: Optional[bool] = None,
        timeout: Optional[float] = None,
        proxy: Optional[str] = None,
        proxies: Optional[Mapping[str, str]] = None,
        allow_redirects: Optional[bool] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
    ) -> FetchResponse:
        if not url or not str(url).strip():
            raise FetchError("URL is required")

        url = str(url).strip()
        impersonate_val = self.impersonate if impersonate is ... else impersonate
        stealth = self.stealthy_headers if stealthy_headers is None else stealthy_headers
        use_http3 = self.http3 if http3 is None else http3
        timeout_val = self.timeout if timeout is None else timeout
        proxy_val = _normalize_proxy(proxy if proxy is not None else self.proxy)
        proxies_val = dict(proxies) if proxies is not None else dict(self.proxies)
        if proxy_val and not proxies_val:
            proxies_val = {"http": proxy_val, "https": proxy_val}
        redirects = self.follow_redirects if allow_redirects is None else allow_redirects
        verify_val = self.verify if verify is None else verify

        browser = _pick_impersonate(impersonate_val)
        merged = build_stealth_headers(
            url,
            {**self.headers, **dict(headers or {})},
            stealthy_headers=bool(stealth),
            impersonate_enabled=bool(browser) and HAS_CURL_CFFI,
            referer=referer,
        )

        last_err: Optional[BaseException] = None
        attempts = self.retries + 1
        for attempt in range(attempts):
            try:
                if HAS_CURL_CFFI:
                    return self._curl_request(
                        method,
                        url,
                        params=params,
                        data=data,
                        json_body=json_body,
                        headers=merged,
                        cookies=cookies,
                        impersonate=browser,
                        http3=bool(use_http3),
                        timeout=float(timeout_val),
                        proxies=proxies_val or None,
                        allow_redirects=bool(redirects),
                        verify=bool(verify_val),
                    )
                # urllib fallback — no TLS impersonation / HTTP/3
                body: Optional[bytes] = None
                if json_body is not None:
                    body = json.dumps(json_body).encode("utf-8")
                    if "content-type" not in _header_keys(merged):
                        merged = {**merged, "Content-Type": "application/json"}
                elif data is not None:
                    if isinstance(data, bytes):
                        body = data
                    elif isinstance(data, str):
                        body = data.encode("utf-8")
                    else:
                        body = str(data).encode("utf-8")
                if params:
                    from urllib.parse import urlencode

                    qs = urlencode({k: v for k, v in params.items()})
                    url = f"{url}{'&' if '?' in url else '?'}{qs}"
                return _urllib_request(
                    method,
                    url,
                    headers=merged,
                    data=body,
                    timeout=float(timeout_val),
                    proxy=proxy_val,
                    allow_redirects=bool(redirects),
                )
            except Exception as exc:
                last_err = exc
                # HTTP/3 + impersonate can fail on some networks — retry without HTTP/3
                if use_http3 and HAS_CURL_CFFI and attempt + 1 < attempts:
                    use_http3 = False
                    continue
                if attempt + 1 >= attempts:
                    break
        raise FetchError(f"{method.upper()} {url} failed: {last_err}") from last_err

    def _curl_request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Mapping[str, Any]],
        data: Any,
        json_body: Any,
        headers: Mapping[str, str],
        cookies: Optional[Mapping[str, str]],
        impersonate: Optional[str],
        http3: bool,
        timeout: float,
        proxies: Optional[Mapping[str, str]],
        allow_redirects: bool,
        verify: bool,
    ) -> FetchResponse:
        assert HAS_CURL_CFFI and CurlSession is not None

        kwargs: dict[str, Any] = {
            "params": params,
            "headers": dict(headers),
            "cookies": cookies,
            "timeout": timeout,
            "proxies": proxies,
            "allow_redirects": allow_redirects,
            "verify": verify,
            "default_headers": self.default_headers,
        }
        if impersonate:
            kwargs["impersonate"] = impersonate
        if http3 and CurlHttpVersion is not None:
            # Prefer HTTP/3; some CDNs may fall back. Impersonation + v3 can
            # conflict on older curl builds — caller retries with http3=False.
            kwargs["http_version"] = CurlHttpVersion.V3ONLY
        if json_body is not None:
            kwargs["json"] = json_body
        elif data is not None:
            kwargs["data"] = data

        # Drop Nones so curl_cffi does not choke
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        client = self._session
        owns_client = False
        if client is None:
            client = CurlSession()
            owns_client = True
        try:
            resp = client.request(method.upper(), url, **kwargs)
            return _response_from_curl(resp)
        finally:
            if owns_client:
                client.close()


class Fetcher:
    """Fast stealthy HTTP client (TLS fingerprint + browser headers + optional HTTP/3).

    Example::

        from fetcher import Fetcher

        r = Fetcher.get("https://example.com", stealthy_headers=True)
        print(r.status_code, r.text[:200])

        r = Fetcher.get(
            "https://http3-target.example",
            impersonate="chrome",
            http3=True,
        )
    """

    _defaults: dict[str, Any] = {
        "impersonate": DEFAULT_IMPERSONATE,
        "stealthy_headers": True,
        "http3": False,
        "timeout": DEFAULT_TIMEOUT,
        "retries": 2,
    }

    @classmethod
    def configure(cls, **kwargs: Any) -> None:
        """Override class-level defaults for subsequent one-shot calls."""
        cls._defaults.update(kwargs)

    @classmethod
    def backend(cls) -> str:
        return "curl_cffi" if HAS_CURL_CFFI else "urllib"

    @classmethod
    def supports_tls_impersonation(cls) -> bool:
        return HAS_CURL_CFFI

    @classmethod
    def supports_http3(cls) -> bool:
        return HAS_CURL_CFFI and CurlHttpVersion is not None

    @classmethod
    def _core(cls, **overrides: Any) -> _FetcherCore:
        opts = {**cls._defaults, **overrides}
        return _FetcherCore(**opts)

    @classmethod
    def request(cls, method: str, url: str, **kwargs: Any) -> FetchResponse:
        return cls._core().request(method, url, **kwargs)

    @classmethod
    def get(cls, url: str, **kwargs: Any) -> FetchResponse:
        return cls.request("GET", url, **kwargs)

    @classmethod
    def post(cls, url: str, **kwargs: Any) -> FetchResponse:
        return cls.request("POST", url, **kwargs)

    @classmethod
    def put(cls, url: str, **kwargs: Any) -> FetchResponse:
        return cls.request("PUT", url, **kwargs)

    @classmethod
    def delete(cls, url: str, **kwargs: Any) -> FetchResponse:
        return cls.request("DELETE", url, **kwargs)

    @classmethod
    def head(cls, url: str, **kwargs: Any) -> FetchResponse:
        return cls.request("HEAD", url, **kwargs)


class FetcherSession:
    """Persistent session (cookies / connection reuse) with the same stealth options."""

    def __init__(
        self,
        *,
        impersonate: ImpersonateType = DEFAULT_IMPERSONATE,
        stealthy_headers: bool = True,
        http3: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        proxy: Optional[str] = None,
        proxies: Optional[Mapping[str, str]] = None,
        headers: Optional[Mapping[str, str]] = None,
        retries: int = 2,
        follow_redirects: bool = True,
        verify: bool = True,
    ) -> None:
        self._core = _FetcherCore(
            impersonate=impersonate,
            stealthy_headers=stealthy_headers,
            http3=http3,
            timeout=timeout,
            proxy=proxy,
            proxies=proxies,
            headers=headers,
            retries=retries,
            follow_redirects=follow_redirects,
            verify=verify,
        )
        self._entered = False

    def __enter__(self) -> "FetcherSession":
        if self._entered:
            raise RuntimeError("FetcherSession already entered")
        if HAS_CURL_CFFI and CurlSession is not None:
            session = CurlSession()
            self._core.attach_session(session)
        self._entered = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._core.close()
        self._entered = False

    def request(self, method: str, url: str, **kwargs: Any) -> FetchResponse:
        if not self._entered and HAS_CURL_CFFI and CurlSession is not None:
            # Allow use without context manager — open lazily
            self._core.attach_session(CurlSession())
            self._entered = True
        return self._core.request(method, url, **kwargs)

    def get(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> FetchResponse:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._core.close()
        self._entered = False


def fetch_bytes(
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    proxy: Optional[str] = None,
    timeout: float = 120.0,
    impersonate: ImpersonateType = DEFAULT_IMPERSONATE,
    http3: bool = False,
    referer: Optional[str] = None,
) -> tuple[bytes, str, int]:
    """Convenience helper for binary downloads (videos / images).

    Returns ``(content, content_type, status_code)``.
    """
    resp = Fetcher.get(
        url,
        headers=headers,
        proxy=proxy,
        timeout=timeout,
        impersonate=impersonate,
        http3=http3,
        stealthy_headers=True,
        referer=referer,
    )
    content_type = ""
    for key, value in resp.headers.items():
        if key.lower() == "content-type":
            content_type = value
            break
    return resp.content, content_type, resp.status_code
