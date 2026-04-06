"""Shared HTTP helpers with proper SSL handling."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.request

logger = logging.getLogger(__name__)

# Build an SSL context that uses certifi's CA bundle when available,
# falling back to the system default.
try:
    import certifi

    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    logger.info("SSL: using certifi CA bundle at %s", certifi.where())
except Exception:
    _ssl_ctx = ssl.create_default_context()
    logger.info("SSL: using system default CA bundle")


def get_json(url: str, timeout: float = 8.0) -> dict | list:
    """Fetch JSON from *url* with proper SSL context."""
    req = urllib.request.Request(url, headers={"User-Agent": "control-plane/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))
