"""
Utilities for rewriting x.com / twitter.com links to an embed-friendly mirror.

Discord's embeds for x.com posts are unreliable (no video, no images, often no
text at all). Mirrors like fixupx.com serve the same post with proper OpenGraph
tags so Discord renders a usable embed.

These helpers are pure functions so they can be unit tested without Discord.
The bot never edits or deletes the original message, which keeps the author's
message row (and therefore their point credit) intact.
"""

import re
from typing import List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

# Default mirror used to rewrite links
DEFAULT_REWRITE_DOMAIN = "fixupx.com"

# Hosts we rewrite (compared after stripping a leading "www.")
_X_HOSTS = {
    "x.com",
    "twitter.com",
    "mobile.x.com",
    "mobile.twitter.com",
    "m.x.com",
    "m.twitter.com",
}

# Mirrors that already produce a working embed - never rewrite these
_ALREADY_FIXED_HOSTS = {
    "fixupx.com",
    "fxtwitter.com",
    "vxtwitter.com",
    "fixvx.com",
    "twittpr.com",
}

# First path segments that are app UI rather than shareable content
_NON_CONTENT_SEGMENTS = {
    "home",
    "explore",
    "notifications",
    "messages",
    "settings",
    "search",
    "compose",
}

_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_URL_RE = re.compile(r"https?://[^\s<>\"'`\\|]+", re.IGNORECASE)

# Punctuation that commonly trails a URL in prose/markdown but isn't part of it
_TRAILING_PUNCTUATION = ")]}>,.!?;:'\"*_~"


def _mask_code_spans(content: str) -> str:
    """Blank out code blocks and inline code, preserving offsets.

    Links inside code are quoted deliberately, so we must not rewrite them.
    Replacing them with spaces keeps every other index in the string valid.
    """

    def blank(match: re.Match) -> str:
        return " " * (match.end() - match.start())

    masked = _CODE_BLOCK_RE.sub(blank, content)
    return _INLINE_CODE_RE.sub(blank, masked)


def _strip_trailing_punctuation(url: str) -> str:
    """Trim trailing prose/markdown punctuation from a matched URL."""
    return url.rstrip(_TRAILING_PUNCTUATION)


def _normalize_host(host: str) -> str:
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_rewritable_x_url(url: str) -> bool:
    """Return True if the URL points at an x.com/twitter.com post worth rewriting."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False

    if parts.scheme.lower() not in ("http", "https"):
        return False

    host = _normalize_host(parts.hostname or "")
    if host in _ALREADY_FIXED_HOSTS or host not in _X_HOSTS:
        return False

    path_segments = [segment for segment in parts.path.split("/") if segment]
    if not path_segments:
        # Bare domain link (https://x.com) - nothing to embed
        return False

    if path_segments[0].lower() in _NON_CONTENT_SEGMENTS:
        return False

    return True


def rewrite_x_url(url: str, rewrite_domain: str = DEFAULT_REWRITE_DOMAIN) -> Optional[str]:
    """Rewrite a single x.com/twitter.com URL onto the mirror domain.

    Returns None when the URL isn't one we rewrite.
    """
    if not is_rewritable_x_url(url):
        return None

    parts = urlsplit(url)
    # Always serve the mirror over https, and drop any userinfo/port from the original
    return urlunsplit(("https", rewrite_domain, parts.path, parts.query, parts.fragment))


def find_x_link_rewrites(
    content: str,
    rewrite_domain: str = DEFAULT_REWRITE_DOMAIN,
    max_links: int = 5,
) -> List[Tuple[str, str]]:
    """Find x.com/twitter.com links in message content and pair them with rewrites.

    Skips links inside code blocks/inline code and links the author wrapped in
    <angle brackets> (that syntax means "don't embed this", so we respect it).

    Args:
        content: Raw Discord message content
        rewrite_domain: Mirror domain to point the links at
        max_links: Cap on how many links are returned, to keep replies short

    Returns:
        List of (original_url, rewritten_url) pairs, deduplicated, in order.
    """
    if not content:
        return []

    masked = _mask_code_spans(content)

    rewrites: List[Tuple[str, str]] = []
    seen = set()

    for match in _URL_RE.finditer(masked):
        url = _strip_trailing_punctuation(match.group(0))
        if not url:
            continue

        # Respect <https://x.com/...> embed suppression by the author
        start, end = match.start(), match.start() + len(url)
        if start > 0 and masked[start - 1] == "<" and masked[end:end + 1] == ">":
            continue

        rewritten = rewrite_x_url(url, rewrite_domain)
        if not rewritten or rewritten in seen:
            continue

        seen.add(rewritten)
        rewrites.append((url, rewritten))

        if len(rewrites) >= max_links:
            break

    return rewrites


def build_rewrite_notice(author_display_name: str, rewrites: List[Tuple[str, str]]) -> str:
    """Build the bot message that carries the fixed links.

    The author is named in plain text (not a mention) so attribution is obvious
    without pinging them.
    """
    if not rewrites:
        return ""

    label = "link" if len(rewrites) == 1 else "links"
    lines = [f"🔗 Fixed embed for **{author_display_name}**'s X {label}:"]
    lines.extend(rewritten for _, rewritten in rewrites)
    return "\n".join(lines)


def build_thread_name(author_display_name: str, max_length: int = 100) -> str:
    """Build a thread title for the fixed-link thread (Discord caps names at 100)."""
    suffix = "'s X link"
    name = f"🔗 {author_display_name}{suffix}"
    if len(name) <= max_length:
        return name

    # Trim the display name rather than the descriptive suffix
    overflow = len(name) - max_length
    trimmed = author_display_name[: max(1, len(author_display_name) - overflow)]
    return f"🔗 {trimmed}{suffix}"[:max_length]
