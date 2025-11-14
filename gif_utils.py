import re
from urllib.parse import urlparse, unquote

"""Utilities for detecting GIF URLs consistently across the bot.

This module centralizes GIF URL detection so that both message handling
and LLM-related URL scraping can share the same logic.
"""

# Regex patterns for direct .gif / .gifv URLs
GIF_URL_PATTERN = re.compile(r"https?://\S+\.gif(?:\?\S*)?", re.IGNORECASE)
GIFV_URL_PATTERN = re.compile(r"https?://\S+\.gifv(?:\?\S*)?", re.IGNORECASE)

# Provider brands to detect regardless of TLD/subdomain (tenor.com, tenor.co, etc.)
GIF_PROVIDER_BRANDS = ("tenor", "giphy", "gfycat", "redgifs")


def is_gif_url(url: str) -> bool:
    """Return True if the URL appears to point to a GIF.

    Detection is based on:
    - direct .gif / .gifv extensions, and
    - well-known GIF provider hostnames / URLs.
    """
    if not url:
        return False

    # Decode percent-encoding (e.g., t%65nor.com -> tenor.com)
    try:
        decoded = unquote(url).lower()
    except Exception:
        decoded = str(url).lower()

    # Check for .gif/.gifv extensions
    if GIF_URL_PATTERN.search(decoded) or GIFV_URL_PATTERN.search(decoded):
        return True

    # Check hostname for provider brands (covers all TLDs/subdomains)
    try:
        hostname = urlparse(decoded).hostname or ""
        if any(brand in hostname for brand in GIF_PROVIDER_BRANDS):
            return True
    except Exception:
        # Fallback: check if brand appears anywhere in URL
        if any(brand in decoded for brand in GIF_PROVIDER_BRANDS):
            return True

    return False

