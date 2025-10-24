import pytest
from unittest.mock import Mock, AsyncMock, patch
import discord
from command_handler import handle_bot_command
from llm_handler import call_llm_api


class TestMessageReferenceIntegration:
    """Test integration of message references with bot commands"""

    @pytest.mark.asyncio
    async def test_bot_command_with_referenced_message(self):
        """Test that bot command can see referenced messages"""
        # Create mock referenced message
        referenced_msg = Mock(spec=discord.Message)
        referenced_msg.id = 12345
        referenced_msg.author = Mock()
        referenced_msg.author.__str__ = Mock(return_value="TestUser")
        referenced_msg.content = "This is the original message being referenced"
        referenced_msg.created_at = Mock()
        referenced_msg.created_at.strftime = Mock(
            return_value="2024-01-01 12:00:00 UTC"
        )

        # Create mock channel
        channel = AsyncMock()
        channel.name = "test-channel"
        channel.id = 67890

        # Create mock guild
        guild = Mock()
        guild.name = "Test Guild"
        guild.id = 11111

        # Create mock user message that references another message
        message = Mock(spec=discord.Message)
        message.id = 54321
        message.author = Mock()
        message.author.__str__ = Mock(return_value="QueryUser")
        message.content = "@bot What does this message mean?"
        message.channel = channel
        message.guild = guild
        message.reference = Mock()
        message.reference.message_id = 12345
        message.reference.cached_message = referenced_msg
        message.reference.channel_id = 67890

        # Create mock client user
        client_user = Mock(spec=discord.ClientUser)
        client_user.id = 99999

        # Create mock bot client
        bot_client = Mock(spec=discord.Client)

        # Mock the message context function
        mock_context = {
            "original_message": message,
            "referenced_message": referenced_msg,
            "linked_messages": [],
        }

        # Mock the LLM API call to capture what gets sent
        captured_query = None
        captured_context = None

        async def mock_llm_call(query, context=None):
            nonlocal captured_query, captured_context
            captured_query = query
            captured_context = context
            return "I can see the referenced message about 'This is the original message being referenced'"

        # Mock thread creation and response sending
        mock_thread = AsyncMock()
        mock_thread.mention = "#test-thread"

        with patch(
            "command_handler.get_message_context", return_value=mock_context
        ), patch("command_handler.call_llm_api", side_effect=mock_llm_call), patch(
            "command_abstraction.ThreadManager"
        ) as mock_thread_manager_class, patch(
            "command_abstraction.MessageResponseSender"
        ) as mock_sender_class, patch(
            "command_handler.split_long_message", return_value=["Test response"]
        ), patch(
            "command_handler.store_bot_response_db"
        ):

            # Setup mocks
            mock_thread_manager = AsyncMock()
            mock_thread_manager.create_thread_from_message.return_value = mock_thread
            mock_thread_manager_class.return_value = mock_thread_manager

            mock_sender = AsyncMock()
            mock_sender.send.return_value = Mock()  # Mock message object
            mock_sender_class.return_value = mock_sender

            # Call the function
            await handle_bot_command(message, client_user, bot_client)

            # Verify that the LLM was called with the context
            assert captured_query == "What does this message mean?"
            assert captured_context is not None
            assert captured_context["referenced_message"] == referenced_msg
            assert len(captured_context["linked_messages"]) == 0

    @pytest.mark.asyncio
    async def test_bot_command_with_linked_message(self):
        """Test that bot command can see linked messages"""
        # Create mock linked message
        linked_msg = Mock(spec=discord.Message)
        linked_msg.id = 98765
        linked_msg.author = Mock()
        linked_msg.author.__str__ = Mock(return_value="LinkedUser")
        linked_msg.content = "This is a linked message with important info"
        linked_msg.created_at = Mock()
        linked_msg.created_at.strftime = Mock(return_value="2024-01-01 11:00:00 UTC")

        # Create mock channel
        channel = AsyncMock()
        channel.name = "test-channel"
        channel.id = 67890

        # Create mock guild
        guild = Mock()
        guild.name = "Test Guild"
        guild.id = 11111

        # Create mock user message with a Discord link
        message = Mock(spec=discord.Message)
        message.id = 54321
        message.author = Mock()
        message.author.__str__ = Mock(return_value="QueryUser")
        message.content = (
            "@bot Explain this: https://discord.com/channels/11111/67890/98765"
        )
        message.channel = channel
        message.guild = guild
        message.reference = None  # No reply reference

        # Create mock client user
        client_user = Mock(spec=discord.ClientUser)
        client_user.id = 99999

        # Create mock bot client
        bot_client = Mock(spec=discord.Client)

        # Mock the message context function
        mock_context = {
            "original_message": message,
            "referenced_message": None,
            "linked_messages": [linked_msg],
        }

        # Mock the LLM API call to capture what gets sent
        captured_query = None
        captured_context = None

        async def mock_llm_call(query, context=None):
            nonlocal captured_query, captured_context
            captured_query = query
            captured_context = context
            return "I can see the linked message about important info"

        # Mock thread creation and response sending
        mock_thread = AsyncMock()
        mock_thread.mention = "#test-thread"

        with patch(
            "command_handler.get_message_context", return_value=mock_context
        ), patch("command_handler.call_llm_api", side_effect=mock_llm_call), patch(
            "command_abstraction.ThreadManager"
        ) as mock_thread_manager_class, patch(
            "command_abstraction.MessageResponseSender"
        ) as mock_sender_class, patch(
            "command_handler.split_long_message", return_value=["Test response"]
        ), patch(
            "command_handler.store_bot_response_db"
        ):

            # Setup mocks
            mock_thread_manager = AsyncMock()
            mock_thread_manager.create_thread_from_message.return_value = mock_thread
            mock_thread_manager_class.return_value = mock_thread_manager

            mock_sender = AsyncMock()
            mock_sender.send.return_value = Mock()  # Mock message object
            mock_sender_class.return_value = mock_sender

            # Call the function
            await handle_bot_command(message, client_user, bot_client)

            # Verify that the LLM was called with the context
            assert "Explain this:" in captured_query
            assert captured_context is not None
            assert captured_context["referenced_message"] is None
            assert len(captured_context["linked_messages"]) == 1
            assert captured_context["linked_messages"][0] == linked_msg

    @pytest.mark.asyncio
    async def test_llm_api_formats_context_correctly(self):
        """Test that the LLM API formats message context correctly"""
        # Create mock referenced message
        referenced_msg = Mock(spec=discord.Message)
        referenced_msg.author = Mock()
        referenced_msg.author.__str__ = Mock(return_value="RefUser")
        referenced_msg.content = "Original message content"
        referenced_msg.created_at = Mock()
        referenced_msg.created_at.strftime = Mock(
            return_value="2024-01-01 10:00:00 UTC"
        )

        # Create mock linked message
        linked_msg = Mock(spec=discord.Message)
        linked_msg.author = Mock()
        linked_msg.author.__str__ = Mock(return_value="LinkUser")
        linked_msg.content = "Linked message content"
        linked_msg.created_at = Mock()
        linked_msg.created_at.strftime = Mock(return_value="2024-01-01 09:00:00 UTC")

        # Create message context
        message_context = {
            "referenced_message": referenced_msg,
            "linked_messages": [linked_msg],
        }

        query = "What do these messages say?"

        # Mock the Perplexity client
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.content = "Test response"

        with patch("llm_handler.OpenAI") as mock_openai_class, patch(
            "llm_handler.config"
        ) as mock_config:

            mock_config.perplexity = "test-key"
            mock_config.llm_model = "test-model"

            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_openai_class.return_value = mock_client

            # Call the LLM API
            result = await call_llm_api(query, message_context)

            # Verify the API was called
            assert mock_client.chat.completions.create.called
            call_args = mock_client.chat.completions.create.call_args

            # Check that the user content includes the context
            user_message = call_args[1]["messages"][1]["content"]
            assert "**Referenced Message (Reply):**" in user_message
            assert "RefUser" in user_message
            assert "Original message content" in user_message
            assert "**Linked Message 1:**" in user_message
            assert "LinkUser" in user_message
            assert "Linked message content" in user_message
            assert "**User's Question/Request:**" in user_message
            assert "What do these messages say?" in user_message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
