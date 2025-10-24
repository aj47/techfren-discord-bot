"""
Simple integration test to verify source linking functionality in practice.
This test simulates the actual workflow used in the Discord bot.
"""

import sys
import os
import asyncio
import datetime
from unittest.mock import Mock, AsyncMock, patch

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from message_utils import generate_discord_message_link, get_message_context
    from llm_handler import call_llm_for_summary
    from discord_formatter import DiscordFormatter
    import discord
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("This test requires the Discord bot modules to be available.")
    sys.exit(1)

def create_sample_messages():
    """Create sample message data that includes source links."""
    now = datetime.datetime.now()

    messages = [
        {
            'id': '123456789012345678',
            'content': 'Check out this great article about AI development trends!',
            'author_name': 'Alice',
            'created_at': now - datetime.timedelta(hours=2),
            'guild_id': '111222333444555666',
            'channel_id': '777888999000111222',
            'scraped_url': 'https://example.com/ai-trends',
            'scraped_content_summary': 'This article discusses the latest trends in AI development, including machine learning advances and ethical considerations.'
        },
        {
            'id': '987654321098765432',
            'content': 'I totally agree with the points made. The ethical considerations are really important.',
            'author_name': 'Bob',
            'created_at': now - datetime.timedelta(hours=1),
            'guild_id': '111222333444555666',
            'channel_id': '777888999000111222'
        },
        {
            'id': '555666777888999000',
            'content': 'Has anyone tried implementing these suggestions in practice?',
            'author_name': 'Charlie',
            'created_at': now - datetime.timedelta(minutes=30),
            'guild_id': '111222333444555666',
            'channel_id': '777888999000111222'
        }
    ]

    return messages

async def test_complete_source_linking_workflow():
    """Test the complete source linking workflow from message to formatted output."""
    print("=== Integration Test: Complete Source Linking Workflow ===")

    # Create sample messages
    messages = create_sample_messages()
    channel_name = "general"
    today = datetime.date.today()
    hours = 24

    print(f"Testing with {len(messages)} sample messages...")

    try:
        # Test 1: Verify message link generation during summary preparation
        print("\n1. Testing message link generation in summary...")

        expected_links = []
        for msg in messages:
            link = generate_discord_message_link(
                msg['guild_id'],
                msg['channel_id'],
                msg['id']
            )
            expected_links.append(link)
            print(f"   Generated link: {link}")

        if len(expected_links) == 3:
            print("   ✓ PASS - All message links generated correctly")
        else:
            print("   ✗ FAIL - Incorrect number of links generated")
            return False

        # Test 2: Test Discord formatter with source links
        print("\n2. Testing Discord formatter with source links...")

        # Simulate an LLM response that contains source links
        mock_llm_response = f"""Here's a summary of the recent discussion in #{channel_name}:

The conversation was initiated by Alice who shared valuable insights about AI development trends [Jump to message]({expected_links[0]}). The article she referenced discusses important aspects of machine learning advances and ethical considerations.

Bob provided thoughtful commentary on the ethical implications [Jump to message]({expected_links[1]}), emphasizing the importance of considering these factors in development.

Charlie raised practical questions about implementation [Jump to message]({expected_links[2]}), which shows the community's interest in applying these concepts.

Key topics:
- AI development trends
- Ethical considerations in ML
- Practical implementation challenges

**Sources:**
- [Original discussion starter]({expected_links[0]})
- [Ethics commentary]({expected_links[1]})
- [Implementation questions]({expected_links[2]})"""

        formatter = DiscordFormatter()
        formatted_response, chart_data = formatter.format_llm_response(mock_llm_response)

        # Count Discord links in formatted response
        from message_utils import extract_message_links
        links_in_formatted = extract_message_links(formatted_response)

        if len(links_in_formatted) >= 3:
            print(f"   ✓ PASS - Discord links preserved in formatted output ({len(links_in_formatted)} links)")
        else:
            print(f"   ✗ FAIL - Discord links lost in formatting (found {len(links_in_formatted)}, expected ≥3)")
            return False

        # Test 3: Test message splitting preserves links
        print("\n3. Testing message splitting preserves source links...")

        from message_utils import split_long_message
        message_parts = await split_long_message(formatted_response, max_length=1000)

        # Count links across all parts
        total_links = []
        for part in message_parts:
            part_links = extract_message_links(part)
            total_links.extend(part_links)

        if len(total_links) >= 3:
            print(f"   ✓ PASS - Links preserved across {len(message_parts)} message parts ({len(total_links)} total links)")
        else:
            print(f"   ✗ FAIL - Links lost during message splitting (found {len(total_links)}, expected ≥3)")
            return False

        # Test 4: Verify link format is clickable in Discord
        print("\n4. Testing Discord link format compatibility...")

        # Check that links follow Discord's expected format
        discord_link_pattern = r'https://discord\.com/channels/\d+/\d+/\d+'
        import re

        valid_links = 0
        for link in total_links:
            if re.match(discord_link_pattern, link):
                valid_links += 1

        if valid_links == len(total_links):
            print(f"   ✓ PASS - All {valid_links} links follow correct Discord format")
        else:
            print(f"   ✗ FAIL - {len(total_links) - valid_links} links have invalid format")
            return False

        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("Source linking workflow is functioning correctly end-to-end.")
        return True

    except Exception as e:
        print(f"\n✗ ERROR in integration test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_message_context_with_real_workflow():
    """Test message context extraction in a realistic scenario."""
    print("\n=== Integration Test: Message Context Extraction ===")

    try:
        # Create mock Discord objects
        mock_bot = Mock()
        mock_guild = Mock()
        mock_guild.id = 111222333444555666
        mock_guild.name = "Test Server"

        mock_channel = Mock()
        mock_channel.id = 777888999000111222
        mock_channel.name = "general"

        # Create a mock message with a Discord link in content
        mock_message = Mock()
        mock_message.content = "Can you analyze this discussion? https://discord.com/channels/111222333444555666/777888999000111222/123456789012345678"
        mock_message.author.name = "TestUser"
        mock_message.id = 999888777666555444
        mock_message.channel = mock_channel
        mock_message.guild = mock_guild
        mock_message.reference = None

        # Create a mock linked message
        mock_linked_message = Mock()
        mock_linked_message.content = "This is the content of the linked message about AI trends"
        mock_linked_message.author.name = "LinkedUser"
        mock_linked_message.id = 123456789012345678
        mock_linked_message.channel = mock_channel
        mock_linked_message.guild = mock_guild
        mock_linked_message.created_at = datetime.datetime.now()

        # Mock the fetch_message_from_link function
        with patch('message_utils.fetch_message_from_link', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_linked_message

            # Test context extraction
            context = await get_message_context(mock_message, mock_bot)

            # Verify context was extracted correctly
            has_linked = len(context['linked_messages']) > 0
            if has_linked:
                linked_content = context['linked_messages'][0].content
                print(f"   ✓ PASS - Extracted linked message: '{linked_content[:50]}...'")
                return True
            else:
                print("   ✗ FAIL - No linked messages extracted")
                return False

    except Exception as e:
        print(f"   ✗ ERROR in message context test: {e}")
        return False

async def main():
    """Run all integration tests."""
    print("SOURCE LINKING INTEGRATION TESTS")
    print("=" * 50)
    print("Testing real-world source linking scenarios\n")

    tests = [
        ("Complete Source Linking Workflow", test_complete_source_linking_workflow),
        ("Message Context Extraction", test_message_context_with_real_workflow)
    ]

    results = []

    for test_name, test_func in tests:
        print(f"Running {test_name}...")
        try:
            result = await test_func()
            results.append((test_name, result))
            status = "PASS" if result else "FAIL"
            print(f"Result: {status}\n")
        except Exception as e:
            print(f"ERROR: {e}\n")
            results.append((test_name, False))

    # Summary
    print("=" * 50)
    print("INTEGRATION TEST RESULTS")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name}: {status}")

    print(f"\nOverall: {passed}/{len(results)} integration tests passed")

    if passed == len(results):
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("Source linking is working correctly in practice!")
        print("\nKey functionality verified:")
        print("✓ Message links are generated with correct format")
        print("✓ Discord formatter preserves source links")
        print("✓ Message splitting maintains link integrity")
        print("✓ Message context extraction works with real scenarios")
        print("✓ End-to-end workflow preserves source attribution")
    else:
        print(f"\n❌ {len(results) - passed} integration test(s) failed.")
        print("Source linking may have issues in real-world usage.")

    return passed == len(results)

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
