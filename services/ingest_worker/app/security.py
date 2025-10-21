from __future__ import annotations

from ipaddress import ip_address, ip_network
from urllib.parse import urlparse


_BLOCKED = [
    ip_network("127.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),  # link-local
    ip_network("::1/128"),
]


def assert_safe_url(url: str) -> None:
    """Raise ValueError if URL points to disallowed schemes/hosts (SSRF guard)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("disallowed_scheme")
    host = (p.hostname or "").lower()
    if host in {"localhost", "ip6-localhost"}:
        raise ValueError("disallowed_host")
    try:
        ip = ip_address(host)
    except ValueError:
        # Not an IP: allow (DNS resolution not performed here)
        return
    for net in _BLOCKED:
        if ip in net:
            raise ValueError("disallowed_host")
