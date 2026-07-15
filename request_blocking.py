#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Playwright route interception — block ads, custom domains, heavy resources."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence, Set, Union
from urllib.parse import urlparse

from ad_domains import load_ad_domains

# Resource types dropped when disable_resources=True (aligned with Scrapling EXTRA_RESOURCES)
HEAVY_RESOURCES = frozenset(
    {
        "font",
        "image",
        "media",
        "beacon",
        "object",
        "imageset",
        "texttrack",
        "websocket",
        "csp_report",
        "stylesheet",
    }
)

DomainSet = Union[Set[str], frozenset, Sequence[str], None]


def is_domain_blocked(hostname: str, domains: frozenset[str]) -> bool:
    """Return True if *hostname* or any parent domain is in *domains*.

    ``example.com`` matches ``example.com`` and ``sub.tracker.example.com``.
    """
    host = (hostname or "").lower().rstrip(".")
    if not host or not domains:
        return False
    if host in domains:
        return True
    # Walk suffix chain: a.b.example.com → b.example.com → example.com
    idx = host.find(".")
    while idx != -1:
        suffix = host[idx + 1 :]
        if suffix in domains:
            return True
        idx = host.find(".", idx + 1)
    return False


def merge_blocked_domains(
    blocked_domains: DomainSet = None,
    *,
    block_ads: bool = False,
) -> frozenset[str]:
    """Combine custom domains with the built-in ad list when ``block_ads``."""
    custom: set[str] = set()
    if blocked_domains:
        for item in blocked_domains:
            host = str(item).strip().lower().rstrip(".")
            if host.startswith("*."):
                host = host[2:]
            if host.startswith("."):
                host = host[1:]
            if host:
                custom.add(host)
    if block_ads:
        return frozenset(custom) | load_ad_domains()
    return frozenset(custom)


def create_route_handler(
    *,
    disable_resources: bool = False,
    blocked_domains: DomainSet = None,
    block_ads: bool = False,
    on_block: Optional[Callable[[str, str], None]] = None,
) -> Optional[Callable[[Any], None]]:
    """Build a Playwright ``page.route`` handler, or ``None`` if nothing to block.

    Blocks:
    1. Heavy resource types when ``disable_resources``
    2. Hostnames matching ``blocked_domains`` (and subdomains)
    3. ~3,500 ad/tracker domains when ``block_ads``
    """
    heavy = HEAVY_RESOURCES if disable_resources else frozenset()
    domains = merge_blocked_domains(blocked_domains, block_ads=block_ads)
    if not heavy and not domains:
        return None

    def handler(route: Any) -> None:
        try:
            req = route.request
            rtype = req.resource_type
            if rtype in heavy:
                if on_block:
                    on_block("resource", rtype)
                route.abort()
                return
            if domains:
                hostname = urlparse(req.url).hostname or ""
                if is_domain_blocked(hostname, domains):
                    if on_block:
                        on_block("domain", hostname)
                    route.abort()
                    return
            route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    return handler


def apply_request_blocking(
    page: Any,
    *,
    disable_resources: bool = False,
    blocked_domains: DomainSet = None,
    block_ads: bool = False,
    on_block: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Attach blocking routes to *page*. Returns True if a handler was installed."""
    handler = create_route_handler(
        disable_resources=disable_resources,
        blocked_domains=blocked_domains,
        block_ads=block_ads,
        on_block=on_block,
    )
    if handler is None:
        return False
    page.route("**/*", handler)
    return True
