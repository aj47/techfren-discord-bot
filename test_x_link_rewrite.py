"""
Tests for x.com/twitter.com link rewriting to an embed-friendly mirror.
"""

import os

import pytest

from x_link_utils import (
    build_rewrite_notice,
    build_thread_name,
    find_x_link_rewrites,
    is_rewritable_x_url,
    rewrite_x_url,
)


class TestIsRewritableXUrl:
    """Tests for detecting URLs that should be rewritten."""

    @pytest.mark.parametrize("url", [
        "https://x.com/cline/status/1925002086405832987",
        "https://twitter.com/cline/status/1925002086405832987",
        "https://www.x.com/user/status/123",
        "https://mobile.twitter.com/user/status/123",
        "http://x.com/user/status/123",
        "https://x.com/someprofile",
    ])
    def test_rewritable_urls(self, url):
        assert is_rewritable_x_url(url) is True

    @pytest.mark.parametrize("url", [
        "https://x.com",                       # bare domain, nothing to embed
        "https://x.com/",                      # bare domain with slash
        "https://x.com/home",                  # app UI, not content
        "https://x.com/search?q=test",         # app UI, not content
        "https://fixupx.com/user/status/123",  # already a fixed mirror
        "https://fxtwitter.com/user/status/1", # already a fixed mirror
        "https://example.com/x.com/fake",      # x.com only in the path
        "https://notx.com/user/status/123",    # different domain
        "https://youtube.com/watch?v=abc",
        "ftp://x.com/user/status/123",         # non-http scheme
    ])
    def test_non_rewritable_urls(self, url):
        assert is_rewritable_x_url(url) is False


class TestRewriteXUrl:
    """Tests for the single-URL rewrite."""

    def test_replaces_host_and_keeps_path(self):
        assert rewrite_x_url("https://x.com/cline/status/1925002086405832987") == \
            "https://fixupx.com/cline/status/1925002086405832987"

    def test_rewrites_twitter_com(self):
        assert rewrite_x_url("https://twitter.com/user/status/123") == \
            "https://fixupx.com/user/status/123"

    def test_preserves_query_and_fragment(self):
        assert rewrite_x_url("https://x.com/user/status/123?s=20&t=abc#frag") == \
            "https://fixupx.com/user/status/123?s=20&t=abc#frag"

    def test_upgrades_http_to_https(self):
        assert rewrite_x_url("http://x.com/user/status/123") == \
            "https://fixupx.com/user/status/123"

    def test_custom_domain(self):
        assert rewrite_x_url("https://x.com/user/status/123", rewrite_domain="vxtwitter.com") == \
            "https://vxtwitter.com/user/status/123"

    def test_returns_none_for_other_urls(self):
        assert rewrite_x_url("https://example.com/page") is None


class TestFindXLinkRewrites:
    """Tests for extracting rewritable links out of message content."""

    def test_finds_link_in_sentence(self):
        rewrites = find_x_link_rewrites("check this out https://x.com/user/status/123 lol")
        assert rewrites == [("https://x.com/user/status/123", "https://fixupx.com/user/status/123")]

    def test_empty_content(self):
        assert find_x_link_rewrites("") == []
        assert find_x_link_rewrites("no links here") == []

    def test_multiple_links(self):
        content = "https://x.com/a/status/1 and https://twitter.com/b/status/2"
        rewrites = find_x_link_rewrites(content)
        assert [new for _, new in rewrites] == [
            "https://fixupx.com/a/status/1",
            "https://fixupx.com/b/status/2",
        ]

    def test_deduplicates_repeated_links(self):
        content = "https://x.com/a/status/1 https://x.com/a/status/1"
        assert len(find_x_link_rewrites(content)) == 1

    def test_respects_max_links(self):
        content = " ".join(f"https://x.com/u/status/{i}" for i in range(10))
        assert len(find_x_link_rewrites(content, max_links=3)) == 3

    def test_ignores_links_in_code_block(self):
        content = "```\nhttps://x.com/user/status/123\n```"
        assert find_x_link_rewrites(content) == []

    def test_ignores_links_in_inline_code(self):
        content = "use `https://x.com/user/status/123` here"
        assert find_x_link_rewrites(content) == []

    def test_finds_link_outside_code_block(self):
        content = "```\nhttps://x.com/a/status/1\n```\nhttps://x.com/b/status/2"
        rewrites = find_x_link_rewrites(content)
        assert [new for _, new in rewrites] == ["https://fixupx.com/b/status/2"]

    def test_respects_angle_bracket_embed_suppression(self):
        content = "quiet one <https://x.com/user/status/123>"
        assert find_x_link_rewrites(content) == []

    def test_strips_trailing_punctuation(self):
        rewrites = find_x_link_rewrites("look at https://x.com/user/status/123.")
        assert rewrites == [("https://x.com/user/status/123", "https://fixupx.com/user/status/123")]

    def test_strips_markdown_paren(self):
        rewrites = find_x_link_rewrites("[post](https://x.com/user/status/123)")
        assert rewrites == [("https://x.com/user/status/123", "https://fixupx.com/user/status/123")]

    def test_ignores_already_fixed_links(self):
        assert find_x_link_rewrites("https://fixupx.com/user/status/123") == []

    def test_mixed_link_types(self):
        content = "https://youtube.com/watch?v=abc https://x.com/user/status/123"
        rewrites = find_x_link_rewrites(content)
        assert [new for _, new in rewrites] == ["https://fixupx.com/user/status/123"]


class TestBuildRewriteNotice:
    """Tests for the message body posted by the bot."""

    def test_single_link_names_the_author(self):
        notice = build_rewrite_notice("techfren", [("https://x.com/a/status/1", "https://fixupx.com/a/status/1")])
        assert "techfren" in notice
        assert "https://fixupx.com/a/status/1" in notice
        assert "X link:" in notice

    def test_plural_label_for_multiple_links(self):
        notice = build_rewrite_notice("techfren", [
            ("https://x.com/a/status/1", "https://fixupx.com/a/status/1"),
            ("https://x.com/b/status/2", "https://fixupx.com/b/status/2"),
        ])
        assert "X links:" in notice
        assert notice.count("fixupx.com") == 2

    def test_no_mention_ping(self):
        notice = build_rewrite_notice("techfren", [("https://x.com/a/status/1", "https://fixupx.com/a/status/1")])
        assert "<@" not in notice

    def test_empty_rewrites(self):
        assert build_rewrite_notice("techfren", []) == ""


class TestBuildThreadName:
    """Tests for thread naming."""

    def test_includes_author_name(self):
        assert "techfren" in build_thread_name("techfren")

    def test_respects_discord_length_limit(self):
        name = build_thread_name("a" * 200)
        assert len(name) <= 100
        assert name.endswith("'s X link")


# ---------------------------------------------------------------------------
# Handler tests (bot.handle_x_link_rewrite)
# ---------------------------------------------------------------------------

def _import_bot():
    """Import the bot module with placeholder config values."""
    os.environ.setdefault('DISCORD_BOT_TOKEN', 'test-token')
    os.environ.setdefault('EXA_API_KEY', 'test-key')
    os.environ.setdefault('OPENROUTER_API_KEY', 'test-key')
    os.environ.setdefault('FIRECRAWL_API_KEY', 'test-key')
    import bot as bot_module
    return bot_module


discord = pytest.importorskip("discord")
MagicMock = pytest.importorskip("unittest.mock").MagicMock
AsyncMock = pytest.importorskip("unittest.mock").AsyncMock


def _make_message(content="https://x.com/user/status/123", message_id=42, is_bot=False, in_thread=False):
    """Build a mock Discord message carrying an X link."""
    author = MagicMock(spec=discord.Member)
    author.bot = is_bot
    author.display_name = "techfren"

    channel = MagicMock(spec=discord.Thread if in_thread else discord.TextChannel)

    message = MagicMock(spec=discord.Message)
    message.id = message_id
    message.content = content
    message.author = author
    message.channel = channel
    message.guild = MagicMock(spec=discord.Guild)
    message.thread = None
    message.create_thread = AsyncMock()
    message.reply = AsyncMock()
    message.edit = AsyncMock()
    message.delete = AsyncMock()
    return message


@pytest.fixture
def bot_module(monkeypatch):
    module = _import_bot()
    module._x_link_handled_messages.clear()
    # Keep tests fast - the real delay is exercised in TestThreadCreationDelay
    monkeypatch.setattr(module.config, 'X_LINK_REWRITE_THREAD_DELAY_SECONDS', 0, raising=False)
    return module


@pytest.mark.asyncio
class TestHandleXLinkRewrite:
    """Tests for the Discord-facing handler."""

    async def test_thread_mode_posts_in_thread_and_preserves_original(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message()
        thread = AsyncMock()
        message.create_thread.return_value = thread

        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_awaited_once()
        thread.send.assert_awaited_once()
        assert "https://fixupx.com/user/status/123" in thread.send.await_args.args[0]
        assert "techfren" in thread.send.await_args.args[0]
        # The original message keeps its author, content and point credit
        message.delete.assert_not_awaited()
        message.edit.assert_not_awaited()
        message.reply.assert_not_awaited()

    async def test_reply_mode_replies_without_ping(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'reply', raising=False)
        message = _make_message()

        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_not_awaited()
        message.reply.assert_awaited_once()
        assert "https://fixupx.com/user/status/123" in message.reply.await_args.args[0]
        assert message.reply.await_args.kwargs['mention_author'] is False
        message.delete.assert_not_awaited()

    async def test_off_mode_does_nothing(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'off', raising=False)
        message = _make_message()

        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_not_awaited()
        message.reply.assert_not_awaited()

    async def test_ignores_messages_without_x_links(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message(content="just some text https://example.com")

        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_not_awaited()
        message.reply.assert_not_awaited()

    async def test_ignores_bot_messages(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message(is_bot=True)

        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_not_awaited()
        message.reply.assert_not_awaited()

    async def test_does_not_post_twice_for_same_message(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message()
        message.create_thread.return_value = AsyncMock()

        await bot_module.handle_x_link_rewrite(message)
        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_awaited_once()

    async def test_falls_back_to_reply_when_thread_creation_fails(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message()
        response = MagicMock(status=403, reason="Forbidden")
        message.create_thread.side_effect = discord.Forbidden(response, "no perms")

        await bot_module.handle_x_link_rewrite(message)

        message.reply.assert_awaited_once()
        assert "https://fixupx.com/user/status/123" in message.reply.await_args.args[0]

    async def test_uses_existing_thread_when_one_already_exists(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message()
        response = MagicMock(status=400, reason="Bad Request")
        error = discord.HTTPException(response, {"code": 160004, "message": "Thread already exists"})
        message.create_thread.side_effect = error
        existing_thread = AsyncMock()
        message.channel.get_thread = MagicMock(return_value=existing_thread)

        await bot_module.handle_x_link_rewrite(message)

        existing_thread.send.assert_awaited_once()
        message.reply.assert_not_awaited()

    async def test_replies_when_message_is_already_in_a_thread(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        message = _make_message(in_thread=True)

        await bot_module.handle_x_link_rewrite(message)

        message.create_thread.assert_not_awaited()
        message.reply.assert_awaited_once()

    async def test_suppresses_original_embed_when_enabled(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'reply', raising=False)
        monkeypatch.setattr(bot_module.config, 'X_LINK_SUPPRESS_ORIGINAL_EMBED', True, raising=False)
        message = _make_message()

        await bot_module.handle_x_link_rewrite(message)

        message.edit.assert_awaited_once_with(suppress=True)
        message.delete.assert_not_awaited()

    async def test_skips_silently_when_message_was_deleted(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'reply', raising=False)
        message = _make_message()
        response = MagicMock(status=404, reason="Not Found")
        message.reply.side_effect = discord.NotFound(response, "unknown message")

        # Must not raise
        await bot_module.handle_x_link_rewrite(message)

    async def test_uses_configured_mirror_domain(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'reply', raising=False)
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_DOMAIN', 'vxtwitter.com', raising=False)
        message = _make_message()

        await bot_module.handle_x_link_rewrite(message)

        assert "https://vxtwitter.com/user/status/123" in message.reply.await_args.args[0]


@pytest.mark.asyncio
class TestThreadCreationDelay:
    """Creating the thread too soon glitches it, so the bot waits first."""

    async def test_waits_before_creating_thread(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_THREAD_DELAY_SECONDS', 2, raising=False)

        calls = []
        message = _make_message()
        message.create_thread.return_value = AsyncMock()
        message.create_thread.side_effect = lambda *a, **kw: calls.append('create_thread')

        async def fake_sleep(seconds):
            calls.append(('sleep', seconds))

        monkeypatch.setattr(bot_module.asyncio, 'sleep', fake_sleep)

        await bot_module.handle_x_link_rewrite(message)

        assert calls[0] == ('sleep', 2), "expected the delay to happen before thread creation"
        assert 'create_thread' in calls

    async def test_no_delay_when_disabled(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'thread', raising=False)
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_THREAD_DELAY_SECONDS', 0, raising=False)

        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(bot_module.asyncio, 'sleep', fake_sleep)
        message = _make_message()
        message.create_thread.return_value = AsyncMock()

        await bot_module.handle_x_link_rewrite(message)

        assert slept == []
        message.create_thread.assert_awaited_once()

    async def test_no_delay_in_reply_mode(self, bot_module, monkeypatch):
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_MODE', 'reply', raising=False)
        monkeypatch.setattr(bot_module.config, 'X_LINK_REWRITE_THREAD_DELAY_SECONDS', 5, raising=False)

        slept = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(bot_module.asyncio, 'sleep', fake_sleep)
        message = _make_message()

        await bot_module.handle_x_link_rewrite(message)

        assert slept == []
        message.reply.assert_awaited_once()
