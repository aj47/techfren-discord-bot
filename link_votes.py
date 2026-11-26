"""Vote arrows for #links-dump, and the Hot / New / Top board.

The arrows live on the shared message. The bot adds both so a member only
taps. The bot's own arrow is not a vote. One person keeps one arrow: the
opposite arrow is removed when they add one.

The board is one message. Discord cannot reorder the channel, so Hot, New,
and Top rewrite that message.
"""

import math
import re

VOTE_EMOJIS = ("🔼", "🔽")
UP, DOWN = VOTE_EMOJIS

# Same shape as the URL check in handle_links_dump_channel.
_URL = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?(?:\?[^\s]*)?")

# Reddit hot score. log10 of the net vote count, plus age in 45_000-second
# steps from Reddit's epoch. A fresh link with one vote outranks an old link
# with a handful. Net below 1 scores as one, so a down-voted link sinks.
_HOT_EPOCH_MS = 1_134_028_003_000
_HOT_WINDOW_MS = 45_000_000

_SORT_LABEL = {"hot": "Hot", "new": "New", "top": "Top"}


_GIF_HOSTS = ("tenor.com", "giphy.com", "gfycat.com", "tenor.co", "klipy.com")
_MEDIA_HOSTS = {
    "cdn.discordapp.com",
    "media.discordapp.net",
    "images-ext-1.discordapp.net",
    "images-ext-2.discordapp.net",
    "i.imgur.com",
}
_MEDIA_EXT = re.compile(r"\.(png|jpe?g|gif|webp|bmp|svg|mp4|mov|webm|mp3|wav|ogg|zip|rar)$", re.I)


def _host(url: str) -> str:
    return url.split("/")[2].split(":")[0].lower()


def is_resource_url(url: str) -> bool:
    """True for a page the resources list keeps. A GIF, an image, or a clip is not."""
    host = _host(url)
    if host in _MEDIA_HOSTS or any(host == name or host.endswith("." + name) for name in _GIF_HOSTS):
        return False
    return _MEDIA_EXT.search(url.split("?", 1)[0]) is None


# Discord copies a thread's parent into the channel as the thread starter.
# That copy is not a new link. Type 18 is the parent side of the pair.
_THREAD_STARTER_TYPE = 18

_DISCORD_JUMP = re.compile(r"https?://(?:\w+\.)?discord(?:app)?\.com/channels/", re.I)


def _is_thread_start(message) -> bool:
    """True for the channel message Discord creates when a thread opens."""
    return getattr(message, "type", None) == _THREAD_STARTER_TYPE


def _only_discord_jumps(message) -> bool:
    """True when every link points at another Discord message."""
    urls = _URL.findall(message.content or "")
    return bool(urls) and all(_DISCORD_JUMP.match(url) for url in urls)


def should_seed(message, dump_channel_id=None, human_repost: bool = False) -> bool:
    """True when this message should receive both vote arrows.

    Any channel. One real link is enough. The links-channel setting is not
    used here. The sorted list still uses it. A bot message is skipped, except
    an X-link repost. That repost is the message that stays.

    A thread start is skipped. Discord copies the parent link into it, and
    that copy is not a new post. A message that only links to another Discord
    message is skipped for the same reason.
    """
    del dump_channel_id
    if _is_thread_start(message) or _only_discord_jumps(message):
        return False
    if getattr(message.author, "bot", False) and not human_repost:
        return False
    return any(is_resource_url(url) for url in _URL.findall(message.content or ""))


async def seed_vote_reactions(message) -> None:
    """Add the up arrow first, then the down arrow. Skip an arrow already there."""
    present = {str(reaction.emoji) for reaction in message.reactions}
    for emoji in VOTE_EMOJIS:
        if emoji in present:
            continue
        await message.add_reaction(emoji)


def opposite(emoji: str):
    if emoji == UP:
        return DOWN
    if emoji == DOWN:
        return UP
    return None


def member_voted(users, user_id: int) -> bool:
    """True when this member is in the voter list. A bot user is not a vote."""
    return any(
        getattr(user, "id", None) == user_id and not getattr(user, "bot", False)
        for user in users
    )


def score(reaction_count: int, bot_reacted: bool) -> int:
    """Member votes only. The bot's seed arrow does not count."""
    votes = reaction_count - (1 if bot_reacted else 0)
    return max(0, votes)


def hot_rank(up: int, down: int, created_ms: int) -> float:
    net = max(up - down, 1)
    return math.log10(net) + (created_ms - _HOT_EPOCH_MS) / _HOT_WINDOW_MS


def order_rows(rows, sort: str):
    if sort == "new":
        key = lambda r: r["created"]
    elif sort == "top":
        key = lambda r: (r["up"], r["up"] - r["down"])
    else:
        key = lambda r: hot_rank(r["up"], r["down"], r["created"])
    return sorted(rows, key=key, reverse=True)


def first_url(content: str):
    match = _URL.search(content or "")
    return match.group(0) if match else None


BOARD_SCAN_LIMIT = 100


async def collect_rows(channel, bot_id: int, limit: int = BOARD_SCAN_LIMIT, human_repost_ids=()):
    """Recent link posts in the dump channel, newest first from history.

    A bot message is skipped, except an X-link repost. That repost is the
    message people see and vote on.
    """
    rows = []
    reposts = {int(i) for i in human_repost_ids}
    async for message in channel.history(limit=limit):
        if message.author.bot and message.id not in reposts and "fixupx.com/" not in (message.content or "") and "fxtwitter.com/" not in (message.content or ""):
            continue
        url = first_url(message.content or "")
        if not url:
            continue
        row = row_from_message(message, bot_id)
        row["url"] = url
        rows.append(row)
    return rows


def row_from_message(message, bot_id: int) -> dict:
    """One board row. The bot's own arrow is not a vote."""
    up = down = 0
    for reaction in message.reactions:
        emoji = str(reaction.emoji)
        if emoji not in (UP, DOWN):
            continue
        count = score(reaction.count, bool(getattr(reaction, "me", False)))
        if emoji == UP:
            up = count
        else:
            down = count
    return {
        "url": first_url(message.content or "") or "",
        "up": up,
        "down": down,
        "created": int(message.created_at.timestamp() * 1000),
        "message_id": message.id,
    }


def render_board(rows, sort: str, limit: int = 10) -> str:
    label = _SORT_LABEL.get(sort, "Hot")
    lines = [f"**{label}** links"]
    shown = [r for r in rows if r.get("url")][:limit]
    if not shown:
        lines.append("_No links yet._")
        return "\n".join(lines)
    for row in shown:
        lines.append(f"🔼 {row['up']}  🔽 {row['down']}  {row['url']}")
    return "\n".join(lines)
