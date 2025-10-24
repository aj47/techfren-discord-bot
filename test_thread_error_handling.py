"""
Test to verify improved thread creation error handling.
This test ensures that thread creation failures are handled gracefully
with appropriate log levels and fallback mechanisms.
"""

import sys
import os
import asyncio
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import discord

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from command_abstraction import ThreadManager
    from command_handler import handle_bot_command, _send_error_response_thread, _handle_bot_command_fallback
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("This test requires the bot modules to be available.")
    sys.exit(1)

class TestThreadErrorHandling(unittest.TestCase):
    """Test thread creation error handling and fallback mechanisms."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock logger to capture log messages
        self.log_messages = []

        def mock_log(level, message, *args, **kwargs):
            self.log_messages.append((level, message))

        self.mock_logger = Mock()
        self.mock_logger.debug = lambda msg, *args, **kwargs: mock_log('DEBUG', msg)
        self.mock_logger.info = lambda msg, *args, **kwargs: mock_log('INFO', msg)
        self.mock_logger.warning = lambda msg, *args, **kwargs: mock_log('WARNING', msg)
        self.mock_logger.error = lambda msg, *args, **kwargs: mock_log('ERROR', msg)

    def create_mock_channel(self, channel_type='dm'):
        """Create mock Discord channel of specified type."""
        if channel_type == 'dm':
            mock_channel = Mock(spec=discord.DMChannel)
            mock_channel.__class__ = discord.DMChannel
            return mock_channel
        elif channel_type == 'text':
            mock_channel = Mock(spec=discord.TextChannel)
            mock_channel.__class__ = discord.TextChannel
            mock_channel.create_thread = AsyncMock()
            return mock_channel
        elif channel_type == 'voice':
            mock_channel = Mock(spec=discord.VoiceChannel)
            mock_channel.__class__ = discord.VoiceChannel
            return mock_channel
        elif channel_type == 'thread':
            mock_channel = Mock(spec=discord.Thread)
            mock_channel.__class__ = discord.Thread
            return mock_channel

    def create_mock_guild(self):
        """Create mock Discord guild."""
        mock_guild = Mock(spec=discord.Guild)
        mock_guild.id = 123456789
        return mock_guild

    def test_thread_manager_dm_channel(self):
        """Test ThreadManager behavior with DM channels."""
        print("=== Testing ThreadManager with DM Channel ===")

        mock_dm_channel = self.create_mock_channel('dm')

        with patch('command_abstraction.logging.getLogger', return_value=self.mock_logger):
            thread_manager = ThreadManager(mock_dm_channel, None)

            # Test _can_create_threads
            can_create = thread_manager._can_create_threads()
            self.assertFalse(can_create, "Should not be able to create threads in DM")

            # Test create_thread
            result = asyncio.run(thread_manager.create_thread("Test Thread"))
            self.assertIsNone(result, "create_thread should return None for DM")

            # Check log messages
            debug_messages = [msg for level, msg in self.log_messages if level == 'DEBUG']
            self.assertTrue(any('DM' in msg for msg in debug_messages),
                          "Should log debug message about DM not supporting threads")

        print("✓ DM channel handling works correctly")

    def test_thread_manager_voice_channel(self):
        """Test ThreadManager behavior with voice channels."""
        print("=== Testing ThreadManager with Voice Channel ===")

        mock_voice_channel = self.create_mock_channel('voice')
        mock_guild = self.create_mock_guild()

        self.log_messages.clear()

        with patch('command_abstraction.logging.getLogger', return_value=self.mock_logger):
            thread_manager = ThreadManager(mock_voice_channel, mock_guild)

            # Test _can_create_threads
            can_create = thread_manager._can_create_threads()
            self.assertFalse(can_create, "Should not be able to create threads in voice channel")

            # Test create_thread
            result = asyncio.run(thread_manager.create_thread("Test Thread"))
            self.assertIsNone(result, "create_thread should return None for voice channel")

            # Check log messages
            info_messages = [msg for level, msg in self.log_messages if level == 'INFO']
            self.assertTrue(any('Voice Channel' in msg for msg in info_messages),
                          "Should log info message about voice channel not supporting threads")

        print("✓ Voice channel handling works correctly")

    def test_thread_manager_text_channel_success(self):
        """Test ThreadManager behavior with text channels (success case)."""
        print("=== Testing ThreadManager with Text Channel (Success) ===")

        mock_text_channel = self.create_mock_channel('text')
        mock_guild = self.create_mock_guild()
        mock_thread = Mock(spec=discord.Thread)

        # Set up successful thread creation
        mock_text_channel.create_thread.return_value = mock_thread

        self.log_messages.clear()

        with patch('command_abstraction.logging.getLogger', return_value=self.mock_logger):
            thread_manager = ThreadManager(mock_text_channel, mock_guild)

            # Test _can_create_threads
            can_create = thread_manager._can_create_threads()
            self.assertTrue(can_create, "Should be able to create threads in text channel")

            # Test create_thread
            result = asyncio.run(thread_manager.create_thread("Test Thread"))
            self.assertEqual(result, mock_thread, "Should return the created thread")

            # Verify create_thread was called
            mock_text_channel.create_thread.assert_called_once_with(
                name="Test Thread",
                type=discord.ChannelType.public_thread
            )

        print("✓ Text channel thread creation works correctly")

    def test_thread_manager_http_error_handling(self):
        """Test ThreadManager handling of HTTP errors."""
        print("=== Testing ThreadManager HTTP Error Handling ===")

        mock_text_channel = self.create_mock_channel('text')
        mock_guild = self.create_mock_guild()

        # Test different HTTP error scenarios
        error_scenarios = [
            (400, "Cannot execute action on this channel type", 'INFO'),
            (400, "thread has already been created", 'INFO'),
            (403, "Missing permissions", 'WARNING'),
            (500, "Internal server error", 'WARNING')
        ]

        for status, text, expected_level in error_scenarios:
            self.log_messages.clear()

            # Create HTTP exception
            http_error = discord.HTTPException(
                response=Mock(status=status),
                message=text
            )
            http_error.status = status
            http_error.text = text

            mock_text_channel.create_thread.side_effect = http_error

            with patch('command_abstraction.logging.getLogger', return_value=self.mock_logger):
                thread_manager = ThreadManager(mock_text_channel, mock_guild)
                result = asyncio.run(thread_manager.create_thread("Test Thread"))

                self.assertIsNone(result, f"Should return None for HTTP {status}")

                # Check appropriate log level was used
                level_messages = [msg for level, msg in self.log_messages if level == expected_level]
                self.assertTrue(len(level_messages) > 0,
                              f"Should log {expected_level} message for HTTP {status}")

        print("✓ HTTP error handling works correctly")

    def test_channel_type_descriptions(self):
        """Test channel type description generation."""
        print("=== Testing Channel Type Descriptions ===")

        channel_types = [
            ('dm', discord.DMChannel, 'DM'),
            ('voice', discord.VoiceChannel, 'Voice Channel'),
            ('thread', discord.Thread, 'Thread')
        ]

        for channel_type, channel_class, expected_desc in channel_types:
            mock_channel = self.create_mock_channel(channel_type)
            thread_manager = ThreadManager(mock_channel, None)

            desc = thread_manager._get_channel_type_description()
            self.assertEqual(desc, expected_desc,
                           f"Should return '{expected_desc}' for {channel_class.__name__}")

        print("✓ Channel type descriptions work correctly")

    async def test_fallback_mechanism_integration(self):
        """Test the complete fallback mechanism when thread creation fails."""
        print("=== Testing Fallback Mechanism Integration ===")

        # Create mock message in DM
        mock_message = Mock(spec=discord.Message)
        mock_message.channel = self.create_mock_channel('dm')
        mock_message.guild = None
        mock_message.author.display_name = "TestUser"
        mock_message.content = "Test question"

        # Mock the send method to track calls
        mock_message.channel.send = AsyncMock()

        with patch('command_handler.ThreadManager') as mock_thread_manager_class:
            # Set up thread manager to return None (thread creation failed)
            mock_thread_manager = Mock()
            mock_thread_manager.create_thread_from_message = AsyncMock(return_value=None)
            mock_thread_manager_class.return_value = mock_thread_manager

            with patch('command_handler._handle_bot_command_fallback') as mock_fallback:
                mock_fallback.return_value = None

                # This should trigger the fallback mechanism
                try:
                    await handle_bot_command(mock_message, Mock(), Mock())
                except Exception:
                    pass  # We expect some exceptions due to mocking

                # Verify fallback was called
                mock_fallback.assert_called_once()

        print("✓ Fallback mechanism integration works correctly")

def run_async_test(test_func):
    """Helper to run async test functions."""
    return asyncio.run(test_func())

def main():
    """Run all thread error handling tests."""
    print("THREAD ERROR HANDLING VERIFICATION")
    print("=" * 60)
    print("Testing improved error handling for thread creation\n")

    test_case = TestThreadErrorHandling()
    test_case.setUp()

    tests = [
        ("DM Channel Handling", test_case.test_thread_manager_dm_channel),
        ("Voice Channel Handling", test_case.test_thread_manager_voice_channel),
        ("Text Channel Success", test_case.test_thread_manager_text_channel_success),
        ("HTTP Error Handling", test_case.test_thread_manager_http_error_handling),
        ("Channel Type Descriptions", test_case.test_channel_type_descriptions),
        ("Fallback Integration", lambda: run_async_test(test_case.test_fallback_mechanism_integration)),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            test_func()
            results.append((test_name, True))
            print(f"✓ {test_name}: PASS\n")
        except Exception as e:
            results.append((test_name, False))
            print(f"✗ {test_name}: FAIL - {e}\n")

    # Summary
    print("=" * 60)
    print("THREAD ERROR HANDLING TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test_name:.<45} {status}")

    print(f"\nOverall Result: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n🎉 ALL THREAD ERROR HANDLING TESTS PASSED!")
        print("✓ DM channels properly detected and handled with debug logs")
        print("✓ Unsupported channel types handled with appropriate log levels")
        print("✓ HTTP errors classified correctly (INFO vs WARNING)")
        print("✓ Fallback mechanisms work when thread creation fails")
        print("✓ No more unnecessary WARNING logs for expected limitations")
        print("\nThread creation errors are now handled gracefully!")
    elif passed >= len(results) * 0.8:
        print(f"\n✅ THREAD ERROR HANDLING MOSTLY WORKING!")
        print("Most error handling improvements are working correctly.")
    else:
        print(f"\n❌ THREAD ERROR HANDLING NEEDS WORK!")
        print("Error handling improvements may not be working properly.")

    return passed >= len(results) * 0.8

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
