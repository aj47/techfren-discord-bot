"""Nearby channel messages added to @tfbot mention context.

Does not import bot.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from message_utils import (
    NEARBY_MESSAGE_COUNT,
    format_nearby_messages,
    get_message_context,
    select_nearby_messages,
)


def _msg(mid, content, author="alice"):
    return SimpleNamespace(
        id=mid,
        content=content,
        author=author,
        created_at=datetime(2026, 10, 17, 22, 30, tzinfo=timezone.utc),
    )


class TestSelectNearbyMessages:
    def test_takes_four_messages_before_the_ping_oldest_first(self):
        ping_id = 50
        # Discord history is newest-first, already excluding the ping.
        history = [
            _msg(40, "dsh?"),
            _msg(30, "I haven’t used dsh in a minute"),
            _msg(20, "but I use orca and tern"),
            _msg(10, "whats tern"),
            _msg(5, "older"),
        ]
        nearby = select_nearby_messages(history, ping_id=ping_id)
        assert [m.content for m in nearby] == [
            "whats tern",
            "but I use orca and tern",
            "I haven’t used dsh in a minute",
            "dsh?",
        ]
        assert NEARBY_MESSAGE_COUNT == 4

    def test_skips_empty_and_whitespace_messages(self):
        history = [
            _msg(40, "keep-4"),
            _msg(30, ""),
            _msg(20, "   "),
            _msg(10, "keep-3"),
            _msg(9, "keep-2"),
            _msg(8, "keep-1"),
        ]
        nearby = select_nearby_messages(history, ping_id=50)
        assert [m.content for m in nearby] == ["keep-1", "keep-2", "keep-3", "keep-4"]

    def test_skips_the_ping_itself_if_history_includes_it(self):
        history = [
            _msg(50, "<@1370407888509599804>"),
            _msg(40, "four"),
            _msg(30, "three"),
            _msg(20, "two"),
            _msg(10, "one"),
        ]
        nearby = select_nearby_messages(history, ping_id=50)
        assert [m.id for m in nearby] == [10, 20, 30, 40]

    def test_skips_ids_already_used_as_the_reply_target(self):
        history = [
            _msg(40, "four"),
            _msg(30, "three"),
            _msg(20, "two"),
            _msg(10, "whats tern"),
        ]
        nearby = select_nearby_messages(history, ping_id=50, skip_ids={10})
        assert [m.content for m in nearby] == ["two", "three", "four"]

    def test_fewer_than_four_returns_what_exists(self):
        history = [_msg(20, "b"), _msg(10, "a")]
        nearby = select_nearby_messages(history, ping_id=50)
        assert [m.content for m in nearby] == ["a", "b"]


class TestFormatNearbyMessages:
    def test_formats_author_and_content_oldest_first(self):
        messages = [
            _msg(10, "whats tern", author="techfren"),
            _msg(20, "but I use orca and tern", author="alexthelambo"),
        ]
        text = format_nearby_messages(messages)
        assert "whats tern" in text
        assert "but I use orca and tern" in text
        assert text.index("whats tern") < text.index("but I use orca and tern")
        assert "techfren" in text
        assert "Nearby" in text

    def test_empty_list_is_empty_string(self):
        assert format_nearby_messages([]) == ""


class TestGetMessageContextNearby:
    @pytest.mark.asyncio
    async def test_always_includes_nearby_messages_even_without_a_reply(self):
        nearby = [_msg(10, "whats tern"), _msg(20, "dsh?")]
        message = Mock()
        message.content = "<@1370407888509599804> what is that"
        message.reference = None
        message.id = 50
        bot = Mock()

        with patch("message_utils.fetch_referenced_message", return_value=None), \
             patch("message_utils.fetch_nearby_messages", new_callable=AsyncMock, return_value=nearby):
            context = await get_message_context(message, bot)

        assert context["nearby_messages"] == nearby
        assert context["referenced_message"] is None


class TestCallLlmApiNearby:
    @pytest.mark.asyncio
    async def test_nearby_messages_are_prefixed_onto_the_query(self):
        from llm_handler import call_llm_api

        nearby = [
            SimpleNamespace(
                id=10,
                content="whats tern",
                author="techfren",
                created_at=datetime(2026, 10, 17, 22, 30, tzinfo=timezone.utc),
            )
        ]
        captured = {}

        async def fake_exa(query, system_prompt=None):
            captured["query"] = query
            return {"answer": "Tern is an agent CLI.", "citations": []}

        with patch("llm_handler.call_exa_answer", side_effect=fake_exa), \
             patch("llm_handler.DiscordFormatter.format_llm_response", side_effect=lambda m, c: m):
            result = await call_llm_api("what is that", {"nearby_messages": nearby})

        assert result == "Tern is an agent CLI."
        assert "**Nearby Messages:**" in captured["query"]
        assert "whats tern" in captured["query"]
        assert "**User's Question/Request:**" in captured["query"]
        assert "what is that" in captured["query"]
