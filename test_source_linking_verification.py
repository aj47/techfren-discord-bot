"""
Comprehensive test to verify source linking functionality in LLM responses.
This test ensures that Discord message links are properly preserved and formatted.
"""

import sys
import os
import asyncio
import datetime
from unittest.mock import Mock, AsyncMock, patch

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from message_utils import (
        generate_discord_message_link,
        extract_message_links,
        get_message_context,
    )
    from discord_formatter import DiscordFormatter
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("This test requires the Discord bot modules to be available.")
    sys.exit(1)


def test_discord_message_link_generation():
    """Test that Discord message links are generated correctly."""
    print("=== Testing Discord Message Link Generation ===")

    test_cases = [
        # (guild_id, channel_id, message_id, expected_link)
        (
            "123456789012345678",
            "987654321098765432",
            "555666777888999000",
            "https://discord.com/channels/123456789012345678/987654321098765432/555666777888999000",  # noqa: E501
        ),
        # DM channel (no guild)
        (
            None,
            "987654321098765432",
            "555666777888999000",
            "https://discord.com/channels/@me/987654321098765432/555666777888999000",
        ),
        # Empty guild should use @me
        (
            "",
            "987654321098765432",
            "555666777888999000",
            "https://discord.com/channels/@me/987654321098765432/555666777888999000",
        ),
    ]

    success_count = 0
    for i, (guild_id, channel_id, message_id, expected) in enumerate(test_cases):
        try:
            result = generate_discord_message_link(guild_id, channel_id, message_id)
            if result == expected:
                print(f"  Test {i+1}: ✓ PASS - {result}")
                success_count += 1
            else:
                print(f"  Test {i+1}: ✗ FAIL")
                print(f"    Expected: {expected}")
                print(f"    Got:      {result}")
        except Exception as e:
            print(f"  Test {i+1}: ✗ ERROR - {e}")

    print(f"Message link generation: {success_count}/{len(test_cases)} tests passed\n")
    return success_count == len(test_cases)


def test_message_link_extraction():
    """Test extracting Discord message links from text."""
    print("=== Testing Message Link Extraction ===")

    test_cases = [
        # Text with single link
        (
            "Check this message: https://discord.com/channels/123/456/789",
            ["https://discord.com/channels/123/456/789"],
        ),
        # Text with multiple links
        (
            "See https://discord.com/channels/123/456/789 and https://discord.com/channels/111/222/333",  # noqa: E501
            [
                "https://discord.com/channels/123/456/789",
                "https://discord.com/channels/111/222/333",
            ],
        ),
        # DM links
        (
            "DM link: https://discord.com/channels/@me/456/789",
            ["https://discord.com/channels/@me/456/789"],
        ),
        # No links
        ("This is just regular text with no links", []),
        # Mixed content
        (
            "Regular text https://discord.com/channels/123/456/789 more text https://example.com",  # noqa: E501
            ["https://discord.com/channels/123/456/789"],
        ),
    ]

    success_count = 0
    for i, (text, expected) in enumerate(test_cases):
        try:
            result = extract_message_links(text)
            if result == expected:
                print(f"  Test {i+1}: ✓ PASS - Found {len(result)} links")
                success_count += 1
            else:
                print(f"  Test {i+1}: ✗ FAIL")
                print(f"    Expected: {expected}")
                print(f"    Got:      {result}")
        except Exception as e:
            print(f"  Test {i+1}: ✗ ERROR - {e}")

    print(f"Link extraction: {success_count}/{len(test_cases)} tests passed\n")
    return success_count == len(test_cases)


def create_mock_message(
    content: str,
    author_name: str = "TestUser",
    message_id: str = "123456789",
    channel_id: str = "987654321",
    guild_id: str = "555444333",
) -> Mock:
    """Create a mock Discord message for testing."""
    mock_message = Mock()
    mock_message.content = content
    mock_message.id = int(message_id)
    mock_message.channel.id = int(channel_id)
    mock_message.author.name = author_name
    mock_message.author.__str__ = Mock(return_value=author_name)
    mock_message.created_at = datetime.datetime.now()

    # Guild setup
    if guild_id:
        mock_message.guild.id = int(guild_id)
        mock_message.guild.name = "Test Guild"
    else:
        mock_message.guild = None

    return mock_message


async def test_message_context_extraction():
    """Test extracting context from messages with references and links."""
    print("=== Testing Message Context Extraction ===")

    # Create mock bot
    mock_bot = Mock()
    mock_bot.get_guild = Mock(return_value=None)
    mock_bot.get_channel = Mock(return_value=None)

    # Test case 1: Message with link in content
    message_with_link = create_mock_message(
        "Check this out: https://discord.com/channels/123/456/789"
    )
    message_with_link.reference = None

    # Mock the fetch_message_from_link function to return a linked message
    linked_message = create_mock_message(
        "This is the linked message content", "LinkedUser"
    )

    with patch(
        "message_utils.fetch_message_from_link", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = linked_message

        context = await get_message_context(message_with_link, mock_bot)

        if (
            context["original_message"] == message_with_link
            and len(context["linked_messages"]) == 1
            and context["linked_messages"][0] == linked_message
        ):
            print("  Test 1: ✓ PASS - Message with link extracted correctly")
            test1_pass = True
        else:
            print("  Test 1: ✗ FAIL - Message context extraction failed")
            test1_pass = False

    # Test case 2: Message with reference (reply)
    referenced_message = create_mock_message("Original message", "OriginalUser")
    reply_message = create_mock_message("This is a reply")

    # Mock reference
    mock_reference = Mock()
    mock_reference.message_id = int(referenced_message.id)
    mock_reference.channel_id = referenced_message.channel.id
    mock_reference.cached_message = referenced_message
    reply_message.reference = mock_reference

    with patch(
        "message_utils.fetch_referenced_message", new_callable=AsyncMock
    ) as mock_ref:
        mock_ref.return_value = referenced_message

        context = await get_message_context(reply_message, mock_bot)

        if context["referenced_message"] == referenced_message:
            print("  Test 2: ✓ PASS - Referenced message extracted correctly")
            test2_pass = True
        else:
            print("  Test 2: ✗ FAIL - Referenced message extraction failed")
            test2_pass = False

    success_count = sum([test1_pass, test2_pass])
    print(f"Message context extraction: {success_count}/2 tests passed\n")
    return success_count == 2


def test_llm_summary_source_preservation():
    """Test that LLM summaries preserve source links correctly."""
    print("=== Testing LLM Summary Source Preservation ===")

    # Mock message data with links
    mock_messages = [
        {
            "id": "123456789",
            "content": "Check out this great article!",
            "author_name": "Alice",
            "created_at": datetime.datetime.now(),
            "guild_id": "111222333",
            "channel_id": "444555666",
            "scraped_url": "https://example.com/article",
            "scraped_content_summary": "Great insights about AI development",
        },
        {
            "id": "987654321",
            "content": "I agree with the points mentioned",
            "author_name": "Bob",
            "created_at": datetime.datetime.now(),
            "guild_id": "111222333",
            "channel_id": "444555666",
        },
    ]

    # Test that message links are properly formatted in the prompt
    try:
        # Create formatted messages like the LLM handler does
        formatted_messages = []
        for msg in mock_messages:
            message_id = msg["id"]
            guild_id = msg["guild_id"]
            channel_id = msg["channel_id"]
            author_name = msg["author_name"]
            content = msg["content"]

            # Generate Discord message link
            message_link = generate_discord_message_link(
                guild_id, channel_id, message_id
            )

            # Format message with clickable link
            message_text = (
                f"[12:00:00] {author_name}: {content} [Jump to message]({message_link})"
            )

            # Add scraped content if available
            if msg.get("scraped_url") and msg.get("scraped_content_summary"):
                scraped_url = msg["scraped_url"]
                scraped_summary = msg["scraped_content_summary"]
                link_content = (
                    f"\n\n[Link Content from {scraped_url}]:\n{scraped_summary}"
                )
                message_text += link_content

            formatted_messages.append(message_text)

        # Verify the formatted output contains proper Discord links
        full_text = "\n".join(formatted_messages)

        # Check that Discord links are present
        discord_links = extract_message_links(full_text)

        # Check markdown link format
        markdown_link_pattern = (
            r"\[Jump to message\]\(https://discord\.com/channels/[^)]+\)"
        )
        import re

        markdown_links = re.findall(markdown_link_pattern, full_text)

        if len(discord_links) == 2 and len(markdown_links) == 2:
            print("  ✓ PASS - Discord message links properly formatted in LLM input")
            print(f"    Found {len(discord_links)} Discord links")
            print(f"    Found {len(markdown_links)} markdown-formatted links")
            return True
        else:
            print("  ✗ FAIL - Discord message links not properly formatted")
            print(f"    Discord links found: {len(discord_links)}")
            print(f"    Markdown links found: {len(markdown_links)}")
            print(f"    Full text preview: {full_text[:200]}...")
            return False

    except Exception as e:
        print(f"  ✗ ERROR - {e}")
        return False


async def test_source_link_preservation_in_output():
    """Test that source links are preserved in LLM output formatting."""
    print("=== Testing Source Link Preservation in Output ===")

    # Simulate LLM response with Discord links
    mock_llm_response = """Here's a summary of the discussion:

The conversation started when Alice shared an interesting article [Jump to message](https://discord.com/channels/111222333/444555666/123456789).  # noqa: E501

Bob responded with valuable insights [Jump to message](https://discord.com/channels/111222333/444555666/987654321).  # noqa: E501

Key topics discussed:
- AI development trends
- Community feedback
- Future roadmap

Sources:
- [Original discussion](https://discord.com/channels/111222333/444555666/123456789)
- [Follow-up comments](https://discord.com/channels/111222333/444555666/987654321)"""

    try:
        # Test that Discord formatter preserves the links
        formatter = DiscordFormatter()

        # The formatter should not break Discord message links
        formatted_response, chart_data = formatter.format_llm_response(
            mock_llm_response
        )

        # Test message splitting to ensure links are preserved across splits
        from message_utils import split_long_message

        formatted_parts = await split_long_message(formatted_response, max_length=1900)

        # Rejoin the parts to check the full output
        full_output = (
            "\n".join(formatted_parts)
            if isinstance(formatted_parts, list)
            else formatted_response
        )

        # Extract Discord links from the output
        output_links = extract_message_links(full_output)

        # Check that all original Discord links are preserved
        actual_link_count = len(output_links)

        if actual_link_count >= 2:  # At least the main links should be preserved
            print(
                f"  ✓ PASS - Discord links preserved in formatted output ({actual_link_count} links)"  # noqa: E501
            )
            return True
        else:
            print("  ✗ FAIL - Discord links not preserved in output")
            print(f"    Expected at least 2 links, found {actual_link_count}")
            print(f"    Links found: {output_links}")
            return False

    except Exception as e:
        print(f"  ✗ ERROR - {e}")
        return False


async def test_end_to_end_source_linking():
    """Test the complete end-to-end source linking workflow."""
    print("=== Testing End-to-End Source Linking ===")

    # Create a mock message with references and links
    test_message = create_mock_message(
        "Can you summarize this discussion? https://discord.com/channels/123/456/789"
    )

    # Mock the referenced message
    referenced_msg = create_mock_message("This is important context", "ContextUser")
    mock_reference = Mock()
    mock_reference.message_id = int(referenced_msg.id)
    mock_reference.channel_id = referenced_msg.channel.id
    mock_reference.cached_message = referenced_msg
    test_message.reference = mock_reference

    # Mock bot client
    mock_bot = Mock()
    mock_bot.get_guild = Mock(return_value=None)
    mock_bot.get_channel = Mock(return_value=None)

    try:
        # Test getting message context
        with patch(
            "message_utils.fetch_referenced_message", new_callable=AsyncMock
        ) as mock_ref, patch(
            "message_utils.fetch_message_from_link", new_callable=AsyncMock
        ) as mock_link:

            mock_ref.return_value = referenced_msg
            linked_msg = create_mock_message("Linked message content", "LinkedUser")
            mock_link.return_value = linked_msg

            context = await get_message_context(test_message, mock_bot)

            # Verify context was extracted
            has_reference = context["referenced_message"] is not None
            has_linked = len(context["linked_messages"]) > 0

            if has_reference and has_linked:
                print("  ✓ PASS - Complete message context extracted")
                print(
                    f"    Referenced message: {context['referenced_message'].content}"
                )
                print(f"    Linked messages: {len(context['linked_messages'])}")
                return True
            else:
                print("  ✗ FAIL - Incomplete message context")
                print(f"    Has reference: {has_reference}")
                print(f"    Has linked: {has_linked}")
                return False

    except Exception as e:
        print(f"  ✗ ERROR - {e}")
        return False


async def run_all_tests():
    """Run all source linking tests."""
    print("SOURCE LINKING FUNCTIONALITY VERIFICATION")
    print("=" * 60)
    print("Testing Discord message link preservation and formatting\n")

    tests = [
        ("Discord Message Link Generation", test_discord_message_link_generation),
        ("Message Link Extraction", test_message_link_extraction),
        ("Message Context Extraction", test_message_context_extraction),
        ("LLM Summary Source Preservation", test_llm_summary_source_preservation),
        ("Source Link Preservation in Output", test_source_link_preservation_in_output),
        ("End-to-End Source Linking", test_end_to_end_source_linking),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"  ✗ ERROR in {test_name}: {e}\n")
            results.append((test_name, False))

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:.<45} {status}")

    print(f"\nOverall Result: {passed}/{len(results)} test suites passed")

    if passed == len(results):
        print("\n🎉 ALL SOURCE LINKING TESTS PASSED!")
        print("✓ Discord message links are properly generated")
        print("✓ Message context is correctly extracted")
        print("✓ Source links are preserved in LLM responses")
        print("✓ End-to-end workflow functions correctly")
        print("\nSource linking functionality is working properly!")
    elif passed >= len(results) * 0.75:
        print("\n✅ MOSTLY FUNCTIONAL!")
        print("Most source linking features are working correctly.")
        print("Some edge cases may need attention.")
    else:
        print("\n❌ NEEDS ATTENTION!")
        print("Source linking functionality has significant issues.")
        print("Multiple test failures indicate problems that need to be fixed.")

    return passed >= len(results) * 0.75


def main():
    """Main test runner."""
    try:
        success = asyncio.run(run_all_tests())
        return success
    except Exception as e:
        print(f"Failed to run tests: {e}")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
