"""
URL Utilities Module

Provides utilities for URL validation, extraction, and Discord-specific link handling.
"""

import re
from typing import List
from urllib.parse import urlparse


def is_discord_message_link(url: str) -> bool:
    """Return True if the URL is a Discord message permalink.

    We use this to avoid treating internal Discord message links as
    external web pages for auto link summaries or scraping.

    Args:
        url: The URL to check

    Returns:
        bool: True if the URL is a Discord message link, False otherwise
    """
    if not url:
        return False

    try:
        # Strip leading/trailing whitespace
        url = url.strip()
        # Reject URLs with trailing slashes (not a valid message link)
        if url.endswith('/'):
            return False
        parsed = urlparse(url)
    except Exception:
        return False

    hostname = (parsed.hostname or "").lower()
    if hostname not in ("discord.com", "discordapp.com"):
        return False

    path_parts = (parsed.path or "").strip("/").split("/")
    # Expect: /channels/{guild_id|@me}/{channel_id}/{message_id}
    if len(path_parts) != 4 or path_parts[0] != "channels":
        return False

    guild_id, channel_id, message_id = path_parts[1], path_parts[2], path_parts[3]
    # guild_id must be either @me (for DMs) or all digits (valid snowflake)
    if guild_id != "@me" and not guild_id.isdigit():
        return False
    if not channel_id.isdigit() or not message_id.isdigit():
        return False

    return True


def extract_message_links(text: str) -> List[str]:
    """Extract Discord message links from text.

    Args:
        text: Text to search for Discord message links

    Returns:
        List of Discord message links found in the text
    """
    pattern = r'https://discord\.com/channels/(?:@me|\d+)/\d+/\d+'
    return re.findall(pattern, text)


def generate_discord_message_link(guild_id: str, channel_id: str, message_id: str) -> str:
    """Generate a Discord message link from guild ID, channel ID, and message ID.

    Args:
        guild_id: The Discord guild (server) ID
        channel_id: The Discord channel ID
        message_id: The Discord message ID

    Returns:
        The Discord message link
    """
    if guild_id:
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
    else:
        # For DMs, use @me instead of guild_id
        return f"https://discord.com/channels/@me/{channel_id}/{message_id}"


def sanitize_url(url: str) -> str | None:
    """Sanitize and normalize a URL by stripping whitespace and common junk.

    Args:
        url: The URL to sanitize

    Returns:
        Sanitized URL string, or None if invalid
    """
    if not url:
        return None

    url = url.strip()

    # Remove common junk characters and trailing slashes
    url = url.rstrip('.,;:!?)]}\'/')

    # Remove leading/trailing quotes that often get attached
    url = url.strip('"\'')

    if not url:
        return None

    try:
        parsed = urlparse(url)
        # Require a scheme for valid URLs
        if not parsed.scheme:
            return None
        # Reject empty netloc (e.g., just "http://")
        if not parsed.netloc and not parsed.path:
            return None
    except Exception:
        return None

    return url


def extract_urls(text: str) -> List[str]:
    """Extract all URLs from text, not just Discord links.

    Args:
        text: Text to search for URLs

    Returns:
        List of URLs found in the text
    """
    # Pattern matches common URL formats
    pattern = r'https?://[^\s<>"\')}\]]+'
    return re.findall(pattern, text)


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL.

    Args:
        url: The URL to validate

    Returns:
        True if valid URL, False otherwise
    """
    if not url:
        return False

    sanitized = sanitize_url(url)
    if not sanitized:
        return False

    try:
        parsed = urlparse(sanitized)
        # Must have http or https scheme
        if parsed.scheme not in ('http', 'https'):
            return False
        # Must have a netloc (domain)
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False
