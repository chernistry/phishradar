from __future__ import annotations

from urllib.parse import urlparse


def canonical_domain(url: str) -> str:
    """Return a simple canonical domain for grouping duplicates.

    - Lowercase
    - Strip leading "www." if present
    - Keep hostname (no port)
    This is a pragmatic approach matching the current product expectation
    (same host == candidate for duplication). For stricter grouping (eTLD+1),
    switch to a PSL-based extractor in a future hardening ticket.
    """
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host

