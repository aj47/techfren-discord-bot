#!/usr/bin/env python3
"""
Unit tests for URL utilities module.
"""

import pytest
from url_utils import (
    is_discord_message_link,
    extract_message_links,
    generate_discord_message_link,
    sanitize_url,
    extract_urls,
    is_valid_url
)


class TestIsDiscordMessageLink:
    """Test cases for is_discord_message_link function."""

    def test_valid_discord_link(self):
        """Test valid Discord message links are recognized."""
        assert is_discord_message_link("https://discord.com/channels/123456789/987654321/111222333") is True

    def test_discordapp_link(self):
        """Test discordapp.com links are recognized."""
        assert is_discord_message_link("https://discordapp.com/channels/123456789/987654321/111222333") is True

    def test_dm_link(self):
        """Test Discord DM links with @me are recognized."""
        assert is_discord_message_link("https://discord.com/channels/@me/987654321/111222333") is True

    def test_non_discord_link(self):
        """Test non-Discord links are rejected."""
        assert is_discord_message_link("https://example.com/article") is False
        assert is_discord_message_link("https://google.com/search?q=test") is False

    def test_empty_url(self):
        """Test empty URL returns False."""
        assert is_discord_message_link("") is False
        assert is_discord_message_link(None) is False

    def test_invalid_path_structure(self):
        """Test links with invalid path structure are rejected."""
        assert is_discord_message_link("https://discord.com/invalid/path") is False
        assert is_discord_message_link("https://discord.com/channels/123") is False

    def test_non_numeric_ids(self):
        """Test links with non-numeric IDs are rejected."""
        assert is_discord_message_link("https://discord.com/channels/abc/456/789") is False
        assert is_discord_message_link("https://discord.com/channels/123/abc/789") is False

    def test_trailing_slash(self):
        """Test links with trailing slashes are rejected."""
        assert is_discord_message_link("https://discord.com/channels/123/456/789/") is False

    def test_large_numeric_ids(self):
        """Test links with very large Discord IDs are accepted."""
        # Discord snowflakes can be up to 19 digits
        large_id = "1234567890123456789"
        assert is_discord_message_link(f"https://discord.com/channels/{large_id}/{large_id}/{large_id}") is True

    def test_whitespace_handling(self):
        """Test URL with leading/trailing whitespace is stripped and accepted."""
        # Whitespace is stripped, so URL should be accepted
        url_with_space = " https://discord.com/channels/123/456/789"
        assert is_discord_message_link(url_with_space) is True
        # Trailing whitespace with trailing slash should be rejected
        url_with_space_and_slash = " https://discord.com/channels/123/456/789/ "
        assert is_discord_message_link(url_with_space_and_slash) is False


class TestExtractMessageLinks:
    """Test cases for extract_message_links function."""

    def test_single_link(self):
        """Test extracting a single Discord message link."""
        text = "Check out https://discord.com/channels/123/456/789 for details"
        result = extract_message_links(text)
        assert result == ["https://discord.com/channels/123/456/789"]

    def test_multiple_links(self):
        """Test extracting multiple Discord message links."""
        text = "See https://discord.com/channels/111/222/333 and https://discord.com/channels/444/555/666"
        result = extract_message_links(text)
        assert len(result) == 2
        assert "https://discord.com/channels/111/222/333" in result
        assert "https://discord.com/channels/444/555/666" in result

    def test_dm_links(self):
        """Test extracting DM links."""
        text = "DM link: https://discord.com/channels/@me/123/456"
        result = extract_message_links(text)
        assert result == ["https://discord.com/channels/@me/123/456"]

    def test_no_links(self):
        """Test text with no Discord links."""
        text = "Just a regular message without any links"
        result = extract_message_links(text)
        assert result == []

    def test_mixed_content(self):
        """Test extracting links from mixed content."""
        text = "Check https://example.com and https://discord.com/channels/123/456/789 also https://google.com"
        result = extract_message_links(text)
        assert result == ["https://discord.com/channels/123/456/789"]

    def test_links_at_boundaries(self):
        """Test extracting links at start and end of text."""
        text = "https://discord.com/channels/111/222/333 in the middle"
        result = extract_message_links(text)
        assert result == ["https://discord.com/channels/111/222/333"]

    def test_links_at_start_end(self):
        """Test extracting links at start and end of text."""
        text = "https://discord.com/channels/111/222/333"
        result = extract_message_links(text)
        assert result == ["https://discord.com/channels/111/222/333"]

    def test_multiple_links_same_line(self):
        """Test extracting multiple links on the same line."""
        text = "Links: https://discord.com/channels/1/2/3 and https://discord.com/channels/4/5/6"
        result = extract_message_links(text)
        assert len(result) == 2
        assert "https://discord.com/channels/1/2/3" in result
        assert "https://discord.com/channels/4/5/6" in result

    def test_empty_text(self):
        """Test extracting links from empty text."""
        result = extract_message_links("")
        assert result == []

    def test_links_with_unicode_content(self):
        """Test extracting links from text with unicode characters."""
        text = "Check this out: https://discord.com/channels/123/456/789 日本語テスト 🎉"
        result = extract_message_links(text)
        assert result == ["https://discord.com/channels/123/456/789"]


class TestGenerateDiscordMessageLink:
    """Test cases for generate_discord_message_link function."""

    def test_guild_link(self):
        """Test generating link with guild ID."""
        link = generate_discord_message_link("123456789", "987654321", "111222333")
        assert link == "https://discord.com/channels/123456789/987654321/111222333"

    def test_dm_link(self):
        """Test generating DM link with empty guild ID."""
        link = generate_discord_message_link("", "123456", "789012")
        assert link == "https://discord.com/channels/@me/123456/789012"

    def test_dm_link_with_none(self):
        """Test generating DM link with None guild ID."""
        link = generate_discord_message_link(None, "123456", "789012")
        assert link == "https://discord.com/channels/@me/123456/789012"


class TestSanitizeUrl:
    """Test cases for sanitize_url function."""

    def test_valid_https_url(self):
        """Test sanitizing a valid HTTPS URL."""
        url = sanitize_url("https://example.com/path?query=value")
        assert url == "https://example.com/path?query=value"

    def test_valid_http_url(self):
        """Test sanitizing a valid HTTP URL."""
        url = sanitize_url("http://example.com")
        assert url == "http://example.com"

    def test_strips_whitespace(self):
        """Test stripping leading/trailing whitespace."""
        url = sanitize_url("  https://example.com  ")
        assert url == "https://example.com"

    def test_strips_trailing_punctuation(self):
        """Test stripping trailing punctuation."""
        url = sanitize_url("https://example.com/page,")
        assert url == "https://example.com/page"
        url = sanitize_url("https://example.com/page.")
        assert url == "https://example.com/page"
        url = sanitize_url("https://example.com/page;")
        assert url == "https://example.com/page"
        url = sanitize_url("https://example.com/page!")
        assert url == "https://example.com/page"

    def test_strips_quotes(self):
        """Test stripping leading/trailing quotes."""
        url = sanitize_url('"https://example.com"')
        assert url == "https://example.com"
        url = sanitize_url("'https://example.com'")
        assert url == "https://example.com"

    def test_none_input(self):
        """Test None input returns None."""
        assert sanitize_url(None) is None

    def test_empty_string(self):
        """Test empty string returns None."""
        assert sanitize_url("") is None

    def test_whitespace_only(self):
        """Test whitespace-only string returns None."""
        assert sanitize_url("   ") is None

    def test_url_without_scheme(self):
        """Test URL without scheme returns None."""
        assert sanitize_url("example.com") is None

    def test_url_with_trailing_slash(self):
        """Test URL with trailing slash is stripped."""
        url = sanitize_url("https://example.com/")
        assert url == "https://example.com"

    def test_url_with_multiple_trailing_slashes(self):
        """Test URL with multiple trailing slashes is stripped."""
        url = sanitize_url("https://example.com///")
        assert url == "https://example.com"


class TestExtractUrls:
    """Test cases for extract_urls function."""

    def test_single_url(self):
        """Test extracting a single URL."""
        text = "Visit https://example.com for more info"
        result = extract_urls(text)
        assert result == ["https://example.com"]

    def test_multiple_urls(self):
        """Test extracting multiple URLs."""
        text = "Check https://example.com and https://google.com"
        result = extract_urls(text)
        assert len(result) == 2
        assert "https://example.com" in result
        assert "https://google.com" in result

    def test_http_url(self):
        """Test extracting HTTP URLs."""
        text = "Link: http://example.com"
        result = extract_urls(text)
        assert result == ["http://example.com"]

    def test_no_urls(self):
        """Test text with no URLs."""
        text = "Just a regular message without any links"
        result = extract_urls(text)
        assert result == []

    def test_url_with_query_params(self):
        """Test extracting URLs with query parameters."""
        text = "Search: https://google.com/search?q=test&t=123"
        result = extract_urls(text)
        assert result == ["https://google.com/search?q=test&t=123"]

    def test_url_with_fragment(self):
        """Test extracting URLs with fragments."""
        text = "Anchor: https://example.com/page#section"
        result = extract_urls(text)
        assert result == ["https://example.com/page#section"]

    def test_url_at_start(self):
        """Test extracting URL at start of text."""
        text = "https://example.com is the link"
        result = extract_urls(text)
        assert result == ["https://example.com"]

    def test_url_at_end(self):
        """Test extracting URL at end of text."""
        text = "Click here: https://example.com"
        result = extract_urls(text)
        assert result == ["https://example.com"]

    def test_mixed_discord_and_regular_urls(self):
        """Test extracting regular URLs when Discord links are present."""
        text = "Check https://example.com and https://discord.com/channels/123/456/789"
        result = extract_urls(text)
        assert "https://example.com" in result
        # Discord links should also be extracted
        assert "https://discord.com/channels/123/456/789" in result

    def test_empty_text(self):
        """Test extracting URLs from empty text."""
        result = extract_urls("")
        assert result == []

    def test_urls_with_unicode_in_text(self):
        """Test extracting URLs from text with unicode."""
        text = "Link: https://example.com 日本語 🎉"
        result = extract_urls(text)
        assert result == ["https://example.com"]


class TestIsValidUrl:
    """Test cases for is_valid_url function."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL returns True."""
        assert is_valid_url("https://example.com") is True

    def test_valid_http_url(self):
        """Test valid HTTP URL returns True."""
        assert is_valid_url("http://example.com") is True

    def test_url_with_path(self):
        """Test valid URL with path."""
        assert is_valid_url("https://example.com/path/to/page") is True

    def test_url_with_query(self):
        """Test valid URL with query string."""
        assert is_valid_url("https://example.com?search=test") is True

    def test_none_input(self):
        """Test None input returns False."""
        assert is_valid_url(None) is False

    def test_empty_string(self):
        """Test empty string returns False."""
        assert is_valid_url("") is False

    def test_url_without_scheme(self):
        """Test URL without scheme returns False."""
        assert is_valid_url("example.com") is False

    def test_url_with_invalid_scheme(self):
        """Test URL with non-http(s) scheme returns False."""
        assert is_valid_url("ftp://example.com") is False
        assert is_valid_url("file:///path/to/file") is False

    def test_malformed_url(self):
        """Test malformed URL returns False."""
        assert is_valid_url("not a url") is False
        assert is_valid_url("https://") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
