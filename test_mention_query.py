"""Mention-query extraction. Does not import bot.py."""

from command_handler import extract_mention_query, mention_query_or_referenced


BOT_ID = 1370407888509599804


class TestExtractMentionQuery:
    def test_strips_leading_mention_and_keeps_the_rest(self):
        assert extract_mention_query(f"<@{BOT_ID}> whats tern", BOT_ID) == "whats tern"

    def test_strips_nickname_mention(self):
        assert extract_mention_query(f"<@!{BOT_ID}> hello", BOT_ID) == "hello"

    def test_bare_mention_is_empty(self):
        assert extract_mention_query(f"<@{BOT_ID}>", BOT_ID) == ""

    def test_bare_mention_with_whitespace_is_empty(self):
        assert extract_mention_query(f"<@{BOT_ID}>   ", BOT_ID) == ""


class TestMentionQueryOrReferenced:
    def test_explicit_query_wins_over_referenced_message(self):
        assert (
            mention_query_or_referenced(
                f"<@{BOT_ID}> explain this",
                BOT_ID,
                "whats tern",
            )
            == "explain this"
        )

    def test_bare_mention_reply_uses_referenced_content(self):
        # Live 2026-10-17: AJ replied to "whats tern" with only @tfbot.
        assert (
            mention_query_or_referenced(f"<@{BOT_ID}>", BOT_ID, "whats tern")
            == "whats tern"
        )

    def test_bare_mention_with_no_referenced_content_stays_empty(self):
        assert mention_query_or_referenced(f"<@{BOT_ID}>", BOT_ID, None) == ""

    def test_bare_mention_with_blank_referenced_content_stays_empty(self):
        assert mention_query_or_referenced(f"<@{BOT_ID}>", BOT_ID, "   ") == ""
