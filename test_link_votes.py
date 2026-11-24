"""Vote arrows on #links-dump messages, and the Hot / New / Top board."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import link_votes


def _message(content, channel_id=111, author_bot=False, is_thread=False):
    message = MagicMock()
    message.content = content
    message.id = 999
    message.author.bot = author_bot
    message.channel.id = channel_id
    message.channel.parent_id = 111 if is_thread else None
    type(message.channel).mro = lambda self: (type(self),)
    message.channel.__class__ = type("TextChannel", (), {})
    if is_thread:
        message.channel.__class__ = type("Thread", (), {})
        # isinstance(..., discord.Thread) is patched per test; flag is enough here.
    message.add_reaction = AsyncMock()
    return message


def test_vote_emojis_are_up_then_down():
    assert link_votes.VOTE_EMOJIS == ("🔼", "🔽")


def test_message_in_dump_with_a_link_gets_both_arrows():
    message = _message("read this https://example.com/a", channel_id=111)
    assert link_votes.should_seed(message, dump_channel_id="111") is True


def test_text_only_message_is_not_seeded():
    message = _message("no link here", channel_id=111)
    assert link_votes.should_seed(message, dump_channel_id="111") is False


def test_a_link_in_any_channel_is_seeded():
    message = _message("https://example.com/a", channel_id=222)
    assert link_votes.should_seed(message, dump_channel_id="111") is True


def test_a_gif_or_an_image_is_not_seeded():
    gif = _message("https://tenor.com/view/cat-123", channel_id=111)
    image = _message("https://cdn.discordapp.com/attachments/1/2/pic.png", channel_id=111)
    assert link_votes.should_seed(gif, dump_channel_id="111") is False
    assert link_votes.should_seed(image, dump_channel_id="111") is False


def test_bot_message_is_not_seeded():
    message = _message("https://example.com/a", channel_id=111, author_bot=True)
    assert link_votes.should_seed(message, dump_channel_id="111") is False


def test_x_link_repost_in_any_channel_is_seeded():
    message = _message("https://fixupx.com/user/status/1", channel_id=111, author_bot=True)
    assert link_votes.should_seed(message, dump_channel_id="111", human_repost=True) is True
    other = _message("https://fixupx.com/user/status/1", channel_id=222, author_bot=True)
    assert link_votes.should_seed(other, dump_channel_id="111", human_repost=True) is True


def test_seeding_does_not_need_the_dump_channel():
    message = _message("https://example.com/a", channel_id=111)
    assert link_votes.should_seed(message, dump_channel_id=None) is True


def test_seed_adds_up_before_down():
    message = _message("https://example.com/a")
    message.reactions = []

    async def run():
        await link_votes.seed_vote_reactions(message)

    asyncio.run(run())
    assert [c.args[0] for c in message.add_reaction.await_args_list] == ["🔼", "🔽"]


def test_seed_skips_an_arrow_that_is_already_there():
    message = _message("https://example.com/a")
    already = MagicMock()
    already.emoji = "🔼"
    message.reactions = [already]

    asyncio.run(link_votes.seed_vote_reactions(message))
    assert [c.args[0] for c in message.add_reaction.await_args_list] == ["🔽"]


def test_opposite_arrow_is_removed():
    assert link_votes.opposite("🔼") == "🔽"
    assert link_votes.opposite("🔽") == "🔼"
    assert link_votes.opposite("👍") is None


def test_board_sorts_hot_new_and_top():
    now = 1_763_900_000_000
    two_days = 2 * 24 * 3600 * 1000
    rows = [
        {"url": "https://old-many.example/a", "up": 20, "down": 0, "created": now - two_days},
        {"url": "https://new-one.example/b", "up": 2, "down": 0, "created": now},
        {"url": "https://split.example/c", "up": 10, "down": 9, "created": now - two_days // 2},
    ]
    top = link_votes.order_rows(rows, "top")
    assert [r["url"] for r in top] == [
        "https://old-many.example/a",
        "https://split.example/c",
        "https://new-one.example/b",
    ]
    newest = link_votes.order_rows(rows, "new")
    assert newest[0]["url"] == "https://new-one.example/b"
    hot = link_votes.order_rows(rows, "hot")
    # A fresh link with a small net score outranks an old link with a large one.
    assert hot[0]["url"] == "https://new-one.example/b"


def test_board_text_names_the_sort_and_the_counts():
    rows = [{"url": "https://example.com/a", "up": 4, "down": 1, "created": 1_700_000_000_000}]
    text = link_votes.render_board(link_votes.order_rows(rows, "top"), "top")
    assert "Top" in text
    assert "https://example.com/a" in text
    assert "🔼 4" in text
    assert "🔽 1" in text


def test_member_voted_ignores_the_bot_and_other_people():
    bot = MagicMock()
    bot.id = 1
    bot.bot = True
    member = MagicMock()
    member.id = 2
    member.bot = False
    other = MagicMock()
    other.id = 3
    other.bot = False

    assert link_votes.member_voted([bot], 2) is False

    assert link_votes.member_voted([bot, member], 2) is True
    assert link_votes.member_voted([bot, member], 3) is False
    assert link_votes.member_voted([bot, other], 2) is False
    # The bot's own arrow is not a vote.
    assert link_votes.score(reaction_count=1, bot_reacted=True) == 0
    assert link_votes.score(reaction_count=3, bot_reacted=True) == 2
    assert link_votes.score(reaction_count=3, bot_reacted=False) == 3


def _history_message(content, up, down, created_ms, author_bot=False, me=True):
    from datetime import datetime, timezone
    message = MagicMock()
    message.content = content
    message.id = created_ms
    message.author.bot = author_bot
    message.created_at = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
    reactions = []
    for emoji, count in (("🔼", up + (1 if me else 0)), ("🔽", down + (1 if me else 0))):
        reaction = MagicMock()
        reaction.emoji = emoji
        reaction.count = count
        reaction.me = me
        reactions.append(reaction)
    message.reactions = reactions
    return message


def test_collect_rows_skips_bots_and_text_and_drops_the_bot_arrow():
    kept = _history_message("see https://example.com/a", up=2, down=0, created_ms=1_700_000_000_000)
    text = _history_message("no link", up=0, down=0, created_ms=1_700_000_000_100)
    bot_post = _history_message("https://example.com/b", up=9, down=0, created_ms=1_700_000_000_200, author_bot=True)

    class _History:
        def __init__(self, messages):
            self._messages = messages

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self._messages):
                raise StopAsyncIteration
            item = self._messages[self._i]
            self._i += 1
            return item

    channel = MagicMock()
    channel.history = lambda limit: _History([kept, text, bot_post])

    rows = asyncio.run(link_votes.collect_rows(channel, bot_id=1))
    assert len(rows) == 1
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[0]["up"] == 2
    assert rows[0]["down"] == 0


def test_collect_rows_keeps_an_x_link_repost():
    repost = _history_message(
        "posted:\nhttps://fixupx.com/user/status/1",
        up=1, down=0, created_ms=1_700_000_000_300, author_bot=True,
    )
    other_bot = _history_message(
        "https://example.com/not-a-repost",
        up=5, down=0, created_ms=1_700_000_000_400, author_bot=True,
    )

    class _History:
        def __init__(self, messages):
            self._messages = messages

        def __aiter__(self):
            self._i = 0
            return self

        async def __anext__(self):
            if self._i >= len(self._messages):
                raise StopAsyncIteration
            item = self._messages[self._i]
            self._i += 1
            return item

    channel = MagicMock()
    channel.history = lambda limit: _History([repost, other_bot])
    rows = asyncio.run(link_votes.collect_rows(channel, bot_id=1))
    assert [row["url"] for row in rows] == ["https://fixupx.com/user/status/1"]
