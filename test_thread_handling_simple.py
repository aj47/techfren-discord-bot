"""
Simplified test to verify thread error handling works correctly.
This test ensures that thread creation failures are handled gracefully.
"""

import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock
import discord

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from command_abstraction import ThreadManager
except ImportError as e:
    print(f"Error importing ThreadManager: {e}")
    sys.exit(1)


def create_mock_dm_channel():
    """Create mock DM channel."""
    mock_channel = Mock(spec=discord.DMChannel)
    mock_channel.__class__ = discord.DMChannel
    return mock_channel


def create_mock_text_channel():
    """Create mock text channel."""
    mock_channel = Mock(spec=discord.TextChannel)
    mock_channel.__class__ = discord.TextChannel
    mock_channel.create_thread = AsyncMock()
    return mock_channel


def create_mock_guild():
    """Create mock guild."""
    mock_guild = Mock(spec=discord.Guild)
    mock_guild.id = 123456789
    return mock_guild


def test_dm_channel_handling():
    """Test that DM channels are handled correctly."""
    print("=== Testing DM Channel Handling ===")

    dm_channel = create_mock_dm_channel()
    thread_manager = ThreadManager(dm_channel, None)

    # Should not be able to create threads in DMs
    can_create = thread_manager._can_create_threads()
    assert not can_create, "Should not be able to create threads in DM"

    # Should return None when trying to create thread
    result = asyncio.run(thread_manager.create_thread("Test Thread"))
    assert result is None, "Should return None for DM thread creation"

    print("✓ DM channel correctly rejects thread creation")
    return True


def test_text_channel_support():
    """Test that text channels support threads."""
    print("=== Testing Text Channel Support ===")

    text_channel = create_mock_text_channel()
    guild = create_mock_guild()
    thread_manager = ThreadManager(text_channel, guild)

    # Should be able to create threads in text channels
    can_create = thread_manager._can_create_threads()
    assert can_create, "Should be able to create threads in text channel"

    print("✓ Text channel correctly supports thread creation")
    return True


def test_channel_type_descriptions():
    """Test channel type description generation."""
    print("=== Testing Channel Type Descriptions ===")

    # Test DM channel description
    dm_channel = create_mock_dm_channel()
    dm_manager = ThreadManager(dm_channel, None)
    dm_desc = dm_manager._get_channel_type_description()
    assert dm_desc == "DM", f"Expected 'DM', got '{dm_desc}'"

    # Test text channel description
    text_channel = create_mock_text_channel()
    text_manager = ThreadManager(text_channel, create_mock_guild())
    text_desc = text_manager._get_channel_type_description()
    assert text_desc == "TextChannel", f"Expected 'TextChannel', got '{text_desc}'"

    print("✓ Channel type descriptions work correctly")
    return True


def test_error_handling():
    """Test HTTP error handling."""
    print("=== Testing Error Handling ===")

    text_channel = create_mock_text_channel()
    guild = create_mock_guild()

    # Simulate HTTP 400 error for unsupported channel type
    http_error = discord.HTTPException(
        response=Mock(status=400), message="Cannot execute action on this channel type"
    )
    http_error.status = 400
    http_error.text = "Cannot execute action on this channel type"

    text_channel.create_thread.side_effect = http_error

    thread_manager = ThreadManager(text_channel, guild)
    result = asyncio.run(thread_manager.create_thread("Test Thread"))

    assert result is None, "Should return None for HTTP 400 error"

    print("✓ HTTP errors handled correctly")
    return True


def main():
    """Run all simplified tests."""
    print("SIMPLIFIED THREAD ERROR HANDLING TEST")
    print("=" * 50)
    print("Testing core thread creation error handling\n")

    tests = [
        ("DM Channel Handling", test_dm_channel_handling),
        ("Text Channel Support", test_text_channel_support),
        ("Channel Type Descriptions", test_channel_type_descriptions),
        ("Error Handling", test_error_handling),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
            print(f"✓ {test_name}: PASS\n")
        except Exception as e:
            results.append((test_name, False))
            print(f"✗ {test_name}: FAIL - {e}\n")

    # Summary
    print("=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:.<35} {status}")

    print(f"\nOverall: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED!")
        print("✓ Thread error handling works correctly")
        print("✓ DM channels properly detected and handled")
        print("✓ Text channels support thread creation")
        print("✓ HTTP errors handled gracefully")
        print(
            "\nThe 'Cannot execute action on this channel type' warning should now be reduced!"
        )
    else:
        print(f"\n❌ {len(results) - passed} test(s) failed.")

    return passed == len(results)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
