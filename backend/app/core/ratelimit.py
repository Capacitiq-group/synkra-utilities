"""
In-process, per-IP rate limiting via slowapi. This is intentionally the
simplest thing that works for a single-instance lightweight deployment.

If/when this API is horizontally scaled behind a load balancer, swap the
default in-memory storage for Redis (slowapi supports it out of the box
via storage_uri="redis://...") so limits are shared across instances —
until then, each instance enforces its own limits independently.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
