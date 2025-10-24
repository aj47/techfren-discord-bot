#!/usr/bin/env python3
"""
Test for links dump channel functionality.
"""

import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import re

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_url_detection():
    """Test the URL detection regex pattern."""
    url_pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?"

    test_cases = [
        ("Check out this link: https://example.com", True),
        ("Visit http://test.com/path?query=value", True),
        ("No links here", False),
        ("Just text without URLs", False),
        ("https://github.com/user/repo", True),
        ("Mixed content https://site.com and more text", True),
        ("", False),
    ]

    for text, should_have_urls in test_cases:
        urls = re.findall(url_pattern, text)
        has_urls = len(urls) > 0

        if has_urls == should_have_urls:
            print(f"✓ '{text}' -> {has_urls} (expected {should_have_urls})")
        else:
            print(f"✗ '{text}' -> {has_urls} (expected {should_have_urls})")
            return False

    return True


async def test_handle_links_dump_channel():
    """Test the handle_links_dump_channel function."""
    # Import the function
    try:
        from bot import handle_links_dump_channel
    except ImportError as e:
        print(f"✗ Could not import handle_links_dump_channel: {e}")
        return False

    # Mock config
    mock_config = MagicMock()
    mock_config.links_dump_channel_id = "123456789"

    # Mock message objects
    def create_mock_message(content, channel_id, is_bot=False, reference=None):
        message = MagicMock()
        message.content = content
        message.channel.id = int(channel_id)
        message.author.bot = is_bot
        message.id = 12345
        message.author.mention = "@testuser"
        message.channel.send = AsyncMock()
        message.delete = AsyncMock()
        message.reference = reference
        return message

    # Test cases
    cross_ref = MagicMock()
    cross_ref.message_id = 222
    cross_ref.channel_id = 987654321
    cross_ref.cached_message = None

    test_cases = [
        # (content, channel_id, is_bot, reference, should_be_handled, description)
        (
            "Check this link: https://example.com",
            "123456789",
            False,
            None,
            False,
            "URL in links dump channel",
        ),
        (
            "Just text",
            "123456789",
            False,
            None,
            True,
            "Text only in links dump channel",
        ),
        ("Just text", "987654321", False, None, False, "Text in different channel"),
        (
            "Any content",
            "123456789",
            True,
            None,
            False,
            "Bot message in links dump channel",
        ),
        (
            "Forwarded",
            "123456789",
            False,
            cross_ref,
            False,
            "Forwarded message allowed",
        ),
    ]

    with patch("bot.config", mock_config):
        with patch("bot.asyncio.create_task") as mock_create_task:
            for (
                content,
                channel_id,
                is_bot,
                reference,
                should_be_handled,
                description,
            ) in test_cases:
                message = create_mock_message(content, channel_id, is_bot, reference)

                try:
                    result = await handle_links_dump_channel(message)

                    if result == should_be_handled:
                        print(f"✓ {description}: handled={result}")
                    else:
                        print(
                            f"✗ {description}: handled={result}, expected={should_be_handled}"
                        )
                        return False

                except Exception as e:
                    print(f"✗ {description}: Exception {e}")
                    return False

    return True


def test_config_integration():
    """Test that config can be loaded without errors."""
    try:
        # Set dummy environment variables to avoid ValueError
        os.environ["DISCORD_BOT_TOKEN"] = "dummy_token"
        os.environ["OPENROUTER_API_KEY"] = "dummy_key"
        os.environ["FIRECRAWL_API_KEY"] = "dummy_key"
        os.environ["LINKS_DUMP_CHANNEL_ID"] = "123456789"

        import config

        # Check if the new config option is available
        if hasattr(config, "links_dump_channel_id"):
            print(
                f"✓ Config loaded, links_dump_channel_id = {config.links_dump_channel_id}"
            )
            return True
        else:
            print("✗ Config missing links_dump_channel_id attribute")
            return False

    except Exception as e:
        print(f"✗ Config loading failed: {e}")
        return False


async def run_tests():
    """Run all tests."""
    print("Testing links dump channel functionality...")

    tests = [
        ("URL Detection", test_url_detection()),
        ("Config Integration", test_config_integration()),
        ("Handle Links Dump Channel", await test_handle_links_dump_channel()),
    ]

    all_passed = True
    for test_name, result in tests:
        if result:
            print(f"✓ {test_name} passed")
        else:
            print(f"✗ {test_name} failed")
            all_passed = False

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    if not success:
        sys.exit(1)
    print("\n✓ All tests passed!")
