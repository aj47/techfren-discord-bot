"""
Tests for the auto_thread module.

Tests conversation chain tracking and automatic thread creation logic.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Set up minimal environment variables before importing modules that need config
os.environ.setdefault('DISCORD_BOT_TOKEN', 'test_token')
os.environ.setdefault('EXA_API_KEY', 'test_key')
os.environ.setdefault('XAI_API_KEY', 'test_key')
os.environ.setdefault('FIRECRAWL_API_KEY', 'test_key')

from auto_thread import (
    ConversationChain,
    ConversationTracker,
    AutoThreadHandler,
)


class TestConversationChain(unittest.TestCase):
    """Test the ConversationChain data class."""

    def test_get_users_returns_both_users(self):
        """Test that get_users returns both user IDs."""
        chain = ConversationChain(user_a_id="123", user_b_id="456")
        users = chain.get_users()
        self.assertEqual(users, {"123", "456"})

    def test_is_valid_next_reply_alternating_pattern(self):
        """Test that alternating pattern is enforced."""
        chain = ConversationChain(
            user_a_id="123",
            user_b_id="456",
            last_replier_id="123"
        )
        # User 456 should be valid (alternating)
        self.assertTrue(chain.is_valid_next_reply("456"))
        # User 123 should not be valid (same user twice)
        self.assertFalse(chain.is_valid_next_reply("123"))
        # User 789 should not be valid (not in conversation)
        self.assertFalse(chain.is_valid_next_reply("789"))

    def test_is_valid_next_reply_empty_last_replier(self):
        """Test that any conversation participant can reply if no last replier."""
        chain = ConversationChain(
            user_a_id="123",
            user_b_id="456",
            last_replier_id=""
        )
        self.assertTrue(chain.is_valid_next_reply("123"))
        self.assertTrue(chain.is_valid_next_reply("456"))
        self.assertFalse(chain.is_valid_next_reply("789"))


class TestConversationTracker(unittest.TestCase):
    """Test the ConversationTracker class."""

    def test_start_new_chain(self):
        """Test starting a new conversation chain."""
        tracker = ConversationTracker(threshold=5)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # Chain should be created
        self.assertIn("chan1", tracker._chains)
        self.assertIn("msg1", tracker._chains["chan1"])

        # Messages should be in reverse lookup
        self.assertIn("msg1", tracker._message_to_chain)
        self.assertIn("msg2", tracker._message_to_chain)

        # Chain should have 2 messages
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(len(chain.message_ids), 2)
        self.assertEqual(chain.user_a_id, "user1")
        self.assertEqual(chain.user_b_id, "user2")

    def test_start_new_chain_ignores_duplicate(self):
        """Test that starting a chain with an already-tracked message is ignored."""
        tracker = ConversationTracker(threshold=5)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # Try to start another chain with msg1
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user3",
            reply_message_id="msg3",
            reply_author_id="user4"
        )

        # Should still only have the original chain
        self.assertEqual(len(tracker._chains["chan1"]), 1)
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(chain.user_a_id, "user1")
        self.assertEqual(chain.user_b_id, "user2")

    def test_track_reply_extends_chain(self):
        """Test that track_reply extends an existing chain."""
        tracker = ConversationTracker(threshold=5)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # user1 replies to msg2
        result = tracker.track_reply(
            channel_id="chan1",
            message_id="msg3",
            author_id="user1",
            reply_to_message_id="msg2"
        )

        # Threshold not reached yet
        self.assertIsNone(result)

        # Chain should now have 3 messages
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(len(chain.message_ids), 3)
        self.assertIn("msg3", chain.message_ids)

    def test_track_reply_threshold_triggers(self):
        """Test that reaching the threshold returns the chain."""
        tracker = ConversationTracker(threshold=4)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # msg3: user1 replies to msg2
        result = tracker.track_reply("chan1", "msg3", "user1", "msg2")
        self.assertIsNone(result)  # 3 messages, need 4

        # msg4: user2 replies to msg3 - this should hit threshold
        result = tracker.track_reply("chan1", "msg4", "user2", "msg3")
        self.assertIsNotNone(result)
        self.assertEqual(len(result.message_ids), 4)

    def test_track_reply_rejects_same_user_twice(self):
        """Test that the same user can't reply twice in a row."""
        tracker = ConversationTracker(threshold=5)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # user2 tries to reply again (should fail - same user twice)
        result = tracker.track_reply("chan1", "msg3", "user2", "msg2")
        self.assertIsNone(result)

        # Chain should still have only 2 messages
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(len(chain.message_ids), 2)

    def test_track_reply_rejects_third_party(self):
        """Test that a third user can't extend the chain."""
        tracker = ConversationTracker(threshold=5)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # user3 tries to reply (should fail - not in conversation)
        result = tracker.track_reply("chan1", "msg3", "user3", "msg2")
        self.assertIsNone(result)

        # Chain should still have only 2 messages
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(len(chain.message_ids), 2)

    def test_track_reply_returns_none_for_untracked_message(self):
        """Test that replying to an untracked message returns None."""
        tracker = ConversationTracker(threshold=5)

        # Reply to a message that's not being tracked
        result = tracker.track_reply("chan1", "msg2", "user2", "msg1")
        self.assertIsNone(result)

    def test_cleanup_expired_chains(self):
        """Test that expired chains are cleaned up."""
        tracker = ConversationTracker(threshold=5, ttl_minutes=1)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )

        # Manually expire the chain
        chain = tracker._chains["chan1"]["msg1"]
        chain.last_activity = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Trigger cleanup via track_reply
        tracker.track_reply("chan1", "msg3", "user1", "msg_unknown")

        # Chain should be cleaned up
        self.assertNotIn("msg1", tracker._chains.get("chan1", {}))
        self.assertNotIn("msg1", tracker._message_to_chain)
        self.assertNotIn("msg2", tracker._message_to_chain)

    def test_mark_processing_prevents_duplicate(self):
        """Test that mark_processing prevents concurrent processing."""
        tracker = ConversationTracker()

        # First mark should succeed
        self.assertTrue(tracker.mark_processing("chan1", "msg1"))

        # Second mark should fail
        self.assertFalse(tracker.mark_processing("chan1", "msg1"))

        # After unmarking, should succeed again
        tracker.unmark_processing("chan1", "msg1")
        self.assertTrue(tracker.mark_processing("chan1", "msg1"))

    def test_remove_chain_cleans_up_fully(self):
        """Test that remove_chain removes all tracking data."""
        tracker = ConversationTracker(threshold=5)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="user1",
            reply_message_id="msg2",
            reply_author_id="user2"
        )
        tracker.track_reply("chan1", "msg3", "user1", "msg2")

        tracker.remove_chain("chan1", "msg1")

        # All tracking should be removed
        self.assertNotIn("msg1", tracker._chains.get("chan1", {}))
        self.assertNotIn("msg1", tracker._message_to_chain)
        self.assertNotIn("msg2", tracker._message_to_chain)
        self.assertNotIn("msg3", tracker._message_to_chain)


class TestAutoThreadHandler(unittest.TestCase):
    """Test the AutoThreadHandler class."""

    def setUp(self):
        """Set up mock bot and handler."""
        self.mock_bot = MagicMock()
        self.mock_bot.user = MagicMock()
        self.mock_bot.user.id = 12345

    @patch('auto_thread.config')
    def test_is_enabled_channel_with_config(self, mock_config):
        """Test is_enabled_channel returns True for configured channels."""
        mock_config.auto_thread_channel_ids = ["chan1", "chan2"]
        mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
        mock_config.AUTO_THREAD_TTL_MINUTES = 60

        handler = AutoThreadHandler(self.mock_bot)

        self.assertTrue(handler.is_enabled_channel("chan1"))
        self.assertTrue(handler.is_enabled_channel("chan2"))
        self.assertFalse(handler.is_enabled_channel("chan3"))

    @patch('auto_thread.config')
    def test_is_enabled_channel_without_config(self, mock_config):
        """Test is_enabled_channel returns False when not configured."""
        mock_config.auto_thread_channel_ids = None
        mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
        mock_config.AUTO_THREAD_TTL_MINUTES = 60

        handler = AutoThreadHandler(self.mock_bot)

        self.assertFalse(handler.is_enabled_channel("chan1"))

    def test_format_message_for_thread(self):
        """Test message formatting for thread reposting."""
        with patch('auto_thread.config') as mock_config:
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60
            handler = AutoThreadHandler(self.mock_bot)

        mock_message = MagicMock()
        mock_message.author.display_name = "TestUser"
        mock_message.content = "Hello world!"
        mock_message.created_at = datetime(2024, 1, 15, 14, 30, 0)
        mock_message.attachments = []
        mock_message.embeds = []

        result = handler._format_message_for_thread(mock_message)

        self.assertIn("**TestUser**", result)
        self.assertIn("14:30", result)
        self.assertIn("Hello world!", result)

    def test_format_message_with_attachments(self):
        """Test message formatting with attachments."""
        with patch('auto_thread.config') as mock_config:
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60
            handler = AutoThreadHandler(self.mock_bot)

        mock_attachment = MagicMock()
        mock_attachment.url = "https://example.com/image.png"

        mock_message = MagicMock()
        mock_message.author.display_name = "TestUser"
        mock_message.content = "Check this out"
        mock_message.created_at = datetime(2024, 1, 15, 14, 30, 0)
        mock_message.attachments = [mock_attachment]
        mock_message.embeds = []

        result = handler._format_message_for_thread(mock_message)

        self.assertIn("https://example.com/image.png", result)

    def test_format_message_with_no_content(self):
        """Test message formatting when there's no text content."""
        with patch('auto_thread.config') as mock_config:
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60
            handler = AutoThreadHandler(self.mock_bot)

        mock_message = MagicMock()
        mock_message.author.display_name = "TestUser"
        mock_message.content = ""
        mock_message.created_at = datetime(2024, 1, 15, 14, 30, 0)
        mock_message.attachments = []
        mock_message.embeds = []

        result = handler._format_message_for_thread(mock_message)

        self.assertIn("[No text content]", result)

    def test_format_message_with_embeds(self):
        """Test message formatting with embeds."""
        with patch('auto_thread.config') as mock_config:
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60
            handler = AutoThreadHandler(self.mock_bot)

        mock_embed = MagicMock()
        mock_embed.url = "https://example.com/embedded"

        mock_message = MagicMock()
        mock_message.author.display_name = "TestUser"
        mock_message.content = "Check this link"
        mock_message.created_at = datetime(2024, 1, 15, 14, 30, 0)
        mock_message.attachments = []
        mock_message.embeds = [mock_embed]

        result = handler._format_message_for_thread(mock_message)

        self.assertIn("[Embed: https://example.com/embedded]", result)


class TestConversationFlow(unittest.TestCase):
    """Integration tests for full conversation flows."""

    def test_full_conversation_reaches_threshold(self):
        """Test a full conversation reaching the threshold."""
        tracker = ConversationTracker(threshold=5)

        # User A sends msg1 (original message - tracked when B replies)
        # User B replies to msg1 (msg2) - starts chain
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="userA",
            reply_message_id="msg2",
            reply_author_id="userB"
        )

        # msg3: User A replies to msg2
        result = tracker.track_reply("chan1", "msg3", "userA", "msg2")
        self.assertIsNone(result)
        self.assertEqual(len(tracker._chains["chan1"]["msg1"].message_ids), 3)

        # msg4: User B replies to msg3
        result = tracker.track_reply("chan1", "msg4", "userB", "msg3")
        self.assertIsNone(result)
        self.assertEqual(len(tracker._chains["chan1"]["msg1"].message_ids), 4)

        # msg5: User A replies to msg4 - threshold reached!
        result = tracker.track_reply("chan1", "msg5", "userA", "msg4")
        self.assertIsNotNone(result)
        self.assertEqual(len(result.message_ids), 5)
        self.assertEqual(result.user_a_id, "userA")
        self.assertEqual(result.user_b_id, "userB")

    def test_third_party_interjection_doesnt_break_chain(self):
        """Test that third party replies don't break the chain."""
        tracker = ConversationTracker(threshold=5)

        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="userA",
            reply_message_id="msg2",
            reply_author_id="userB"
        )

        # msg3: User A replies to msg2
        tracker.track_reply("chan1", "msg3", "userA", "msg2")

        # msg4: User C replies to msg3 (third party - not extended but chain not broken)
        result = tracker.track_reply("chan1", "msg4", "userC", "msg3")
        self.assertIsNone(result)

        # Chain should still have 3 messages (A, B, A)
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(len(chain.message_ids), 3)

        # msg5: User B replies to msg3 (continuing original chain)
        result = tracker.track_reply("chan1", "msg5", "userB", "msg3")
        self.assertIsNone(result)

        # Chain should now have 4 messages
        chain = tracker._chains["chan1"]["msg1"]
        self.assertEqual(len(chain.message_ids), 4)

    def test_multiple_channels_tracked_independently(self):
        """Test that conversations in different channels are tracked independently."""
        tracker = ConversationTracker(threshold=3)

        # Start chain in channel 1
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="userA",
            reply_message_id="msg2",
            reply_author_id="userB"
        )

        # Start chain in channel 2
        tracker.start_new_chain(
            channel_id="chan2",
            original_message_id="msg10",
            original_author_id="userX",
            reply_message_id="msg11",
            reply_author_id="userY"
        )

        # Extend channel 1
        result1 = tracker.track_reply("chan1", "msg3", "userA", "msg2")

        # Extend channel 2
        result2 = tracker.track_reply("chan2", "msg12", "userX", "msg11")

        # Both should hit threshold
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)

        # Verify they're independent chains
        self.assertEqual(result1.user_a_id, "userA")
        self.assertEqual(result2.user_a_id, "userX")

    def test_chain_expires_and_can_restart(self):
        """Test that an expired chain allows a new chain to start."""
        tracker = ConversationTracker(threshold=5, ttl_minutes=1)

        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg1",
            original_author_id="userA",
            reply_message_id="msg2",
            reply_author_id="userB"
        )

        # Expire the chain
        chain = tracker._chains["chan1"]["msg1"]
        chain.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)

        # Trigger cleanup
        tracker._cleanup_expired("chan1")

        # Now we should be able to start a new chain with msg1
        # (though in practice msg1 is a different message conceptually)
        tracker.start_new_chain(
            channel_id="chan1",
            original_message_id="msg100",
            original_author_id="userC",
            reply_message_id="msg101",
            reply_author_id="userD"
        )

        self.assertIn("msg100", tracker._chains["chan1"])
        self.assertEqual(tracker._chains["chan1"]["msg100"].user_a_id, "userC")


class TestAsyncHandlerMethods(unittest.TestCase):
    """Test async methods of AutoThreadHandler using asyncio."""

    def setUp(self):
        """Set up mock bot."""
        self.mock_bot = MagicMock()
        self.mock_bot.user = MagicMock()
        self.mock_bot.user.id = 12345

    def test_handle_message_skips_bots(self):
        """Test that bot messages are skipped."""
        import asyncio

        with patch('auto_thread.config') as mock_config:
            mock_config.auto_thread_channel_ids = ["123"]
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60

            handler = AutoThreadHandler(self.mock_bot)

            mock_message = MagicMock()
            mock_message.author.bot = True

            result = asyncio.get_event_loop().run_until_complete(
                handler.handle_message(mock_message)
            )
            self.assertFalse(result)

    def test_handle_message_skips_threads(self):
        """Test that messages in threads are skipped."""
        import asyncio
        import discord

        with patch('auto_thread.config') as mock_config:
            mock_config.auto_thread_channel_ids = ["123"]
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60

            handler = AutoThreadHandler(self.mock_bot)

            mock_message = MagicMock()
            mock_message.author.bot = False
            mock_message.channel = MagicMock(spec=discord.Thread)
            mock_message.channel.id = 123

            result = asyncio.get_event_loop().run_until_complete(
                handler.handle_message(mock_message)
            )
            self.assertFalse(result)

    def test_handle_message_skips_non_replies(self):
        """Test that non-reply messages are skipped."""
        import asyncio

        with patch('auto_thread.config') as mock_config:
            mock_config.auto_thread_channel_ids = ["123"]
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60

            handler = AutoThreadHandler(self.mock_bot)

            mock_message = MagicMock()
            mock_message.author.bot = False
            mock_message.channel = MagicMock()
            mock_message.channel.__class__.__name__ = "TextChannel"
            mock_message.channel.id = 123
            mock_message.reference = None

            result = asyncio.get_event_loop().run_until_complete(
                handler.handle_message(mock_message)
            )
            self.assertFalse(result)

    def test_handle_message_skips_disabled_channels(self):
        """Test that messages in non-enabled channels are skipped."""
        import asyncio

        with patch('auto_thread.config') as mock_config:
            mock_config.auto_thread_channel_ids = ["999"]  # Different channel
            mock_config.AUTO_THREAD_REPLY_THRESHOLD = 5
            mock_config.AUTO_THREAD_TTL_MINUTES = 60

            handler = AutoThreadHandler(self.mock_bot)

            mock_message = MagicMock()
            mock_message.author.bot = False
            mock_message.channel = MagicMock()
            mock_message.channel.__class__.__name__ = "TextChannel"
            mock_message.channel.id = 123
            mock_message.reference = MagicMock()
            mock_message.reference.message_id = 456

            result = asyncio.get_event_loop().run_until_complete(
                handler.handle_message(mock_message)
            )
            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
