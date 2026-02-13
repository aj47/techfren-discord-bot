#!/usr/bin/env python3
"""
Unit tests for URL utilities module.
"""

import pytest
from url_utils import (
    is_discord_message_link,
    extract_message_links,
    generate_discord_message_link
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
