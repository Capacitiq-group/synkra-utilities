"""
Fetch a remote resource by URL, safely.

Any endpoint that accepts a user-supplied URL and fetches it server-side
(the QR logo feature is the first) is a classic SSRF vector — a malicious
`logo_url` could point at http://169.254.169.254/... (cloud metadata),
http://localhost:6379 (internal services), etc. This module is the one
place that fetch happens, so every caller gets the same protection.
"""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

MAX_FETCH_BYTES = 5 * 1024 * 1024  # 5 MB — plenty for a logo/icon
FETCH_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class UnsafeUrlError(Exception):
    pass


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # can't parse it -> block
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _assert_safe_host(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise UnsafeUrlError(f"Could not resolve host: {hostname}") from e
    if not infos:
        raise UnsafeUrlError(f"Could not resolve host: {hostname}")
    for info in infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            raise UnsafeUrlError(f"URL resolves to a blocked address: {ip_str}")


async def safe_fetch_bytes(url: str, allowed_content_types: set[str] | None = None) -> tuple[bytes, str]:
    """
    Fetches `url` after validating it isn't pointed at an internal/private
    address, enforcing a size cap. Returns (bytes, content_type).
    Raises UnsafeUrlError or httpx.HTTPError on failure — callers should
    catch both and turn them into a 400, never a 500.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http/https URLs are allowed.")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no host.")

    _assert_safe_host(parsed.hostname)

    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=False,  # a redirect could repoint at an internal IP
        max_redirects=0,
    ) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            if allowed_content_types and content_type not in allowed_content_types:
                raise UnsafeUrlError(f"Unsupported content type: {content_type or 'unknown'}")

            declared_length = resp.headers.get("content-length")
            if declared_length and int(declared_length) > MAX_FETCH_BYTES:
                raise UnsafeUrlError("File is too large.")

            chunks = bytearray()
            async for chunk in resp.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_FETCH_BYTES:
                    raise UnsafeUrlError("File is too large.")
            return bytes(chunks), content_type
