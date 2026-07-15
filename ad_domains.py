#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Built-in ad/tracker domain list (~3,500 entries).

Source: Peter Lowe's Ad and tracking server list
https://pgl.yoyo.org/adservers/
(also mirrored in Scrapling's ad_domains module)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent / "data" / "ad_domains.txt"


@lru_cache(maxsize=1)
def load_ad_domains() -> frozenset[str]:
    """Load the bundled ad/tracker domain frozenset (lazy, cached)."""
    if not _DATA_FILE.is_file():
        return frozenset()
    domains: set[str] = set()
    for line in _DATA_FILE.read_text(encoding="utf-8").splitlines():
        host = line.strip().lower().rstrip(".")
        if host and not host.startswith("#") and "." in host:
            domains.add(host)
    return frozenset(domains)


def ad_domain_count() -> int:
    return len(load_ad_domains())
