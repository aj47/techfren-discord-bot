"""
Test script to verify Discord mentions in summaries.
This script tests that the LLM receives user mappings and generates proper Discord mentions.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_handler import call_llm_for_summary

class TestDiscordMentions(unittest.TestCase):
    """Test case for Discord mentions in summaries"""

    def setUp(self):
        """Set up test environment"""
        # Mock config
        self.config_patcher = patch('llm_handler.config')
        self.mock_config = self.config_patcher.start()
        self.mock_config.openrouter = "test_openrouter_key"
        self.mock_config.llm_model = "test-model"

        # Mock OpenAI client
        self.openai_patcher = patch('llm_handler.OpenAI')
        self.mock_openai_class = self.openai_patcher.start()
        self.mock_openai_client = MagicMock()
        self.mock_openai_class.return_value = self.mock_openai_client

        # Mock completion response
        self.mock_completion = MagicMock()
        self.mock_completion.choices = [MagicMock()]
        self.mock_completion.choices[0].message.content = "Test summary with <@123456789> mentioned"
        self.mock_openai_client.chat.completions.create.return_value = self.mock_completion

        # Mock logger
        self.logger_patcher = patch('llm_handler.logger')
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self):
        """Clean up after tests"""
        self.config_patcher.stop()
        self.openai_patcher.stop()
        self.logger_patcher.stop()

    async def test_user_mappings_in_prompt(self):
        """Test that user mappings are included in the LLM prompt"""
        # Create test messages with user IDs
        test_messages = [
            {
                'author_name': 'pierrunoyt',
                'author_id': '123456789',
                'content': 'test message 1',
                'created_at': datetime.now(),
                'is_bot': False,
                'is_command': False,
                'id': 'msg1',
                'channel_id': 'channel1',
                'guild_id': 'guild1'
            },
            {
                'author_name': 'testuser',
                'author_id': '987654321',
                'content': 'test message 2',
                'created_at': datetime.now(),
                'is_bot': False,
                'is_command': False,
                'id': 'msg2',
                'channel_id': 'channel1',
                'guild_id': 'guild1'
            }
        ]

        # Call the function
        result = await call_llm_for_summary(test_messages, "test-channel", datetime.now(), 24)

        # Verify the OpenAI client was called
        self.mock_openai_client.chat.completions.create.assert_called_once()

        # Get the call arguments
        call_args = self.mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        user_prompt = messages[1]['content']

        # Check that user mappings are included in the prompt
        self.assertIn("User ID Mappings (for Discord mentions):", user_prompt)
        self.assertIn("pierrunoyt = <@123456789>", user_prompt)
        self.assertIn("testuser = <@987654321>", user_prompt)

        # Check that the prompt instructs to use Discord mentions
        self.assertIn("use Discord mention format <@user_id>", user_prompt)

        # Verify the result
        self.assertEqual(result, "Test summary with <@123456789> mentioned")

    async def test_system_prompt_mentions_instruction(self):
        """Test that the system prompt instructs to use Discord mentions"""
        test_messages = [
            {
                'author_name': 'testuser',
                'author_id': '123456789',
                'content': 'test message',
                'created_at': datetime.now(),
                'is_bot': False,
                'is_command': False,
                'id': 'msg1',
                'channel_id': 'channel1',
                'guild_id': 'guild1'
            }
        ]

        # Call the function
        await call_llm_for_summary(test_messages, "test-channel", datetime.now(), 24)

        # Get the call arguments
        call_args = self.mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        system_prompt = messages[0]['content']

        # Check that system prompt instructs to use Discord mentions
        self.assertIn("use Discord mention format <@user_id>", system_prompt)
        self.assertNotIn("backticks", system_prompt)

    async def test_no_user_mappings_when_no_valid_ids(self):
        """Test that no user mappings are created when there are no valid user IDs"""
        test_messages = [
            {
                'author_name': 'Unknown Author',
                'author_id': '',
                'content': 'test message',
                'created_at': datetime.now(),
                'is_bot': False,
                'is_command': False,
                'id': 'msg1',
                'channel_id': 'channel1',
                'guild_id': 'guild1'
            }
        ]

        # Call the function
        await call_llm_for_summary(test_messages, "test-channel", datetime.now(), 24)

        # Get the call arguments
        call_args = self.mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]['messages']
        user_prompt = messages[1]['content']

        # Check that no user mappings section is included
        self.assertNotIn("User ID Mappings (for Discord mentions):", user_prompt)

def run_async_test():
    """Run async tests"""
    async def run_tests():
        test_case = TestDiscordMentions()
        test_case.setUp()
        
        try:
            print("Testing user mappings in prompt...")
            await test_case.test_user_mappings_in_prompt()
            print("✓ User mappings test passed")
            
            print("Testing system prompt mentions instruction...")
            await test_case.test_system_prompt_mentions_instruction()
            print("✓ System prompt test passed")
            
            print("Testing no user mappings when no valid IDs...")
            await test_case.test_no_user_mappings_when_no_valid_ids()
            print("✓ No user mappings test passed")
            
            print("\n✅ All tests passed!")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            raise
        finally:
            test_case.tearDown()

    # Run the async tests
    asyncio.run(run_tests())

if __name__ == "__main__":
    print("Running Discord mentions tests...")
    run_async_test()
