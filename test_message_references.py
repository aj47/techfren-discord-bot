import pytest
from unittest.mock import Mock, AsyncMock, patch
import discord
from message_utils import (
    fetch_referenced_message,
    fetch_message_from_link,
    extract_message_links,
    get_message_context,
)


class TestMessageReferences:
    """Test fetching referenced messages (replies)"""

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_cached(self):
        """Test fetching referenced message when it's cached"""
        # Create mock messages
        referenced_msg = Mock(spec=discord.Message)
        referenced_msg.id = 12345

        message = Mock(spec=discord.Message)
        message.reference = Mock()
        message.reference.message_id = 12345
        message.reference.cached_message = referenced_msg

        result = await fetch_referenced_message(message)
        assert result == referenced_msg

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_not_cached(self):
        """Test fetching referenced message when not cached"""
        # Create mock referenced message
        referenced_msg = Mock(spec=discord.Message)
        referenced_msg.id = 12345

        # Create mock channel that can fetch the message
        channel = AsyncMock()
        channel.fetch_message.return_value = referenced_msg
        channel.id = 67890

        # Create mock message with reference
        message = Mock(spec=discord.Message)
        message.reference = Mock()
        message.reference.message_id = 12345
        message.reference.cached_message = None
        message.reference.channel_id = 67890
        message.channel = channel

        result = await fetch_referenced_message(message)
        assert result == referenced_msg
        channel.fetch_message.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_fetch_referenced_message_no_reference(self):
        """Test when message has no reference"""
        message = Mock(spec=discord.Message)
        message.reference = None

        result = await fetch_referenced_message(message)
        assert result is None


class TestMessageFromLink:
    """Test fetching messages from Discord links"""

    @pytest.mark.asyncio
    async def test_fetch_message_from_valid_link(self):
        """Test fetching message from valid Discord link"""
        # Create mock message
        target_msg = Mock(spec=discord.Message)
        target_msg.id = 123456789

        # Create mock channel
        channel = AsyncMock()
        channel.fetch_message.return_value = target_msg

        # Create mock guild
        guild = Mock()
        guild.get_channel.return_value = channel

        # Create mock bot
        bot = Mock(spec=discord.Client)
        bot.get_guild.return_value = guild

        link = "https://discord.com/channels/111/222/123456789"
        result = await fetch_message_from_link(link, bot)

        assert result == target_msg
        bot.get_guild.assert_called_once_with(111)
        guild.get_channel.assert_called_once_with(222)
        channel.fetch_message.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_fetch_message_from_dm_link(self):
        """Test fetching message from DM link"""
        # Create mock message
        target_msg = Mock(spec=discord.Message)
        target_msg.id = 123456789

        # Create mock channel
        channel = AsyncMock()
        channel.fetch_message.return_value = target_msg

        # Create mock bot
        bot = Mock(spec=discord.Client)
        bot.get_channel.return_value = channel

        link = "https://discord.com/channels/@me/222/123456789"
        result = await fetch_message_from_link(link, bot)

        assert result == target_msg
        bot.get_channel.assert_called_once_with(222)
        channel.fetch_message.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_fetch_message_from_invalid_link(self):
        """Test with invalid Discord link"""
        bot = Mock(spec=discord.Client)

        invalid_link = "https://example.com/not-a-discord-link"
        result = await fetch_message_from_link(invalid_link, bot)

        assert result is None


class TestExtractMessageLinks:
    """Test extracting Discord message links from text"""

    def test_extract_single_link(self):
        """Test extracting single Discord message link"""
        text = "Check this message: https://discord.com/channels/111/222/333"
        links = extract_message_links(text)

        assert len(links) == 1
        assert links[0] == "https://discord.com/channels/111/222/333"

    def test_extract_multiple_links(self):
        """Test extracting multiple Discord message links"""
        text = """
        First: https://discord.com/channels/111/222/333
        Second: https://discord.com/channels/444/555/666
        """
        links = extract_message_links(text)

        assert len(links) == 2
        assert "https://discord.com/channels/111/222/333" in links
        assert "https://discord.com/channels/444/555/666" in links

    def test_extract_dm_link(self):
        """Test extracting DM message link"""
        text = "DM link: https://discord.com/channels/@me/222/333"
        links = extract_message_links(text)

        assert len(links) == 1
        assert links[0] == "https://discord.com/channels/@me/222/333"

    def test_extract_no_links(self):
        """Test with text containing no Discord links"""
        text = "This is just regular text with no links"
        links = extract_message_links(text)

        assert len(links) == 0


class TestGetMessageContext:
    """Test getting full message context"""

    @pytest.mark.asyncio
    async def test_get_message_context_with_reference_and_links(self):
        """Test getting context with both referenced message and linked messages"""
        # Create mock referenced message
        referenced_msg = Mock(spec=discord.Message)
        referenced_msg.id = 111

        # Create mock linked message
        linked_msg = Mock(spec=discord.Message)
        linked_msg.id = 222

        # Create mock original message
        message = Mock(spec=discord.Message)
        message.content = "Reply with link: https://discord.com/channels/111/222/333"
        message.reference = Mock()
        message.reference.message_id = 111
        message.reference.cached_message = referenced_msg

        # Create mock bot
        bot = Mock(spec=discord.Client)

        # Mock the functions
        with patch(
            "message_utils.fetch_referenced_message", return_value=referenced_msg
        ), patch("message_utils.fetch_message_from_link", return_value=linked_msg):

            context = await get_message_context(message, bot)

        assert context["original_message"] == message
        assert context["referenced_message"] == referenced_msg
        assert len(context["linked_messages"]) == 1
        assert context["linked_messages"][0] == linked_msg


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
