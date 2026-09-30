"""Nightly unanswered-questions thread in #general.

Runs at 23:00 UTC so it finishes before the 00:00 UTC digest prune.
Posts as this bot (tfbot) — parent + thread, same shape as the daily summary.
No user pings, no channel mentions, no timestamps, no `in channelname`.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import discord
from discord.ext import tasks

import config
import database
from logging_config import logger
from message_utils import split_long_message

discord_client = None

# Parent rooms only. Hermes/tfbot thread titles leak into channel_name.
ALLOW_CHANNELS = {
    "general",
    "agentic-engineering",
    "ai-models",
    "collabs",
    "paid-work",
    "cli-coding",
    "bot-devs",
    "linux",
    "learn-study",
    "showcase",
    "suggestions",
    "events-hackathons",
    "deals-promos",
    "crypto",
    "noob-talk",
    "ask-for-help-here",
    "augment-code",
    "agentbattler",
    "100x-orchestrator",
    "clickolas-cage",
    "google-gemini-challenge",
    "mvp-cribs",
    "video-editor-app",
    "dotagents",
    "off-topic",
}

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>|<a?:\w+:\d+>")
CODE_RE = re.compile(r"```[\s\S]*?```|`[^`]+`")
WS_RE = re.compile(r"\s+")
QSTART = re.compile(
    r"^(?:hey |hi |yo |sup |so |ok |okay |please |pls |quick q[:.,]? )*"
    r"(?:how|what|why|where|when|who|which|can|could|would|should|"
    r"is there|are there|does anyone|has anyone|anyone|anybody|"
    r"any chance|do you|did anyone)\b",
    re.I,
)
HELP = re.compile(
    r"\b(help me|need help|how do i|how to|anyone know|does anyone|"
    r"can someone|can anybody|is there a (?:way|tool|guide)|looking for|"
    r"stuck on|what's the best|whats the best|recommend (?:a|an|any))\b",
    re.I,
)
JUNK = re.compile(
    r"^(wait|what|huh|lol|lmao|wtf|bro|fr|right|sure|ok|okay|nice|cool|"
    r"true|based|why|who|eh|hmm)\??$",
    re.I,
)
RHETORICAL = re.compile(r"\b(lmao|lol|lmaooo|kek|bruh)\b", re.I)
SPAM = re.compile(
    r"(we're currently expanding|looking for people who want to work with us|"
    r"public ai training platforms|flexible opportunity|dm me if interested|"
    r"guaranteed (?:income|returns)|work from home opportunity)",
    re.I,
)
INTRO = re.compile(
    r"\b(just joined|i'?m new here|nice to meet|full-stack developer mostly working)\b",
    re.I,
)
DEIXIS = re.compile(
    r"\b(that one|this one|is that|was that|the license|when it was up|"
    r"how long will that|they take)\b",
    re.I,
)
QUESTION_STOPS = {
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "in", "on", "for",
    "with", "from", "about", "into", "over", "just", "really", "also", "too",
    "how", "what", "whats", "why", "where", "when", "who", "which", "can",
    "could", "would", "should", "is", "are", "do", "does", "did", "will",
    "has", "have", "anyone", "anybody", "someone", "somebody", "everyone",
    "everyones", "you", "your", "guys", "here", "there", "up", "out", "any",
    "new", "main", "coming", "used", "once", "only", "want", "need", "help",
    "make", "nice", "last", "long", "take", "away", "think", "better",
}
REACTION = re.compile(
    r"^(rip|lmao|lol|true|nice|cool|same|wait|huh|wtf|bro|fr|ok|okay|yeah|"
    r"yep|nah|send help|oh|hmm)\.?$",
    re.I,
)
CHATTY = re.compile(
    r"(who is getting the first|anyone here going to buy|who is going to use astra|"
    r"so why they bragging|they never delivered|how can he claim|also damn bro)",
    re.I,
)


def set_discord_client(client_instance):
    global discord_client
    discord_client = client_instance


def strip_noise(content: str) -> str:
    text = URL_RE.sub(" ", content or "")
    text = MENTION_RE.sub(" ", text)
    text = CODE_RE.sub(" ", text)
    return WS_RE.sub(" ", text).strip()


def is_question(content: str, stripped: str) -> bool:
    if len(stripped) < 28:
        return False
    if JUNK.match(stripped):
        return False
    if SPAM.search(content or "") or SPAM.search(stripped):
        return False
    if INTRO.search(stripped) and "?" not in (content or ""):
        return False
    if RHETORICAL.search(stripped) and len(stripped) < 80:
        return False
    if CHATTY.search(stripped):
        return False
    has_q = "?" in (content or "")
    return bool(has_q or QSTART.search(stripped) or HELP.search(stripped))


def has_topic_token(stripped: str) -> bool:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,}", stripped)
    return any(t.lower() not in QUESTION_STOPS and len(t) >= 3 for t in tokens)


def needs_context(stripped: str) -> bool:
    topical = has_topic_token(stripped)
    deictic = bool(DEIXIS.search(stripped))
    if deictic and (not topical or len(stripped) < 90):
        return True
    if len(stripped) < 48 and not topical:
        return True
    return False


def pick_context(prior: List[Dict[str, Any]], author_id: str, excerpt: str) -> Optional[str]:
    excerpt_l = (excerpt or "").lower()
    same: List[str] = []
    other: List[str] = []
    for r in reversed(prior):
        if r.get("is_bot"):
            continue
        text = strip_noise(r.get("content") or "")
        if len(text) < 18 or REACTION.match(text):
            continue
        if text.lower() in excerpt_l or excerpt_l in text.lower():
            continue
        if is_question(r.get("content") or "", text):
            continue
        bucket = same if r.get("author_id") == author_id else other
        bucket.append(text)
        if same:
            break
        if len(other) >= 6:
            break
    pick = same[0] if same else (other[0] if other else None)
    if not pick:
        return None
    if len(pick) > 90:
        pick = pick[:87] + "…"
    return pick


def jump_url(guild_id: str, channel_id: str, message_id: str) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"


def _created_sort_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def scout_questions(
    messages_by_channel: Dict[str, Any],
    *,
    guild_id: str,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """Pick unanswered human questions from a get_messages_for_time_range payload."""
    rows: List[Dict[str, Any]] = []
    replied = set()
    for channel in messages_by_channel.values():
        channel_id = channel.get("channel_id")
        channel_name = (channel.get("channel_name") or "").strip()
        channel_guild = channel.get("guild_id") or guild_id
        for msg in channel.get("messages") or []:
            row = dict(msg)
            row["channel_id"] = channel_id
            row["channel_name"] = channel_name
            row["guild_id"] = channel_guild
            rows.append(row)
            reply_to = row.get("reply_to_message_id")
            if reply_to:
                replied.add(str(reply_to))
    rows.sort(key=lambda r: (_created_sort_key(r.get("created_at")), r.get("id") or ""))

    questions: List[Dict[str, Any]] = []
    seen_norm = set()
    for idx, r in enumerate(rows):
        if r.get("is_bot") or r.get("is_command"):
            continue
        channel = (r.get("channel_name") or "").strip()
        if channel not in ALLOW_CHANNELS:
            continue
        if r.get("reply_to_message_id"):
            continue
        if str(r.get("id") or "") in replied:
            continue
        content = r.get("content") or ""
        stripped = strip_noise(content)
        if not is_question(content, stripped):
            continue
        norm = re.sub(r"[^\w\s]", "", stripped.lower())[:160]
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        item = {
            "id": r.get("id"),
            "author_id": r.get("author_id"),
            "author_name": r.get("author_name"),
            "channel_id": r.get("channel_id"),
            "channel_name": channel,
            "excerpt": stripped[:240],
            "url": jump_url(
                str(r.get("guild_id") or guild_id),
                str(r.get("channel_id") or ""),
                str(r.get("id") or ""),
            ),
        }
        if needs_context(stripped):
            prior = []
            j = idx - 1
            while j >= 0 and len(prior) < 12:
                prev = rows[j]
                if prev.get("channel_id") == r.get("channel_id"):
                    prior.append(prev)
                j -= 1
            prior.reverse()
            ctx = pick_context(prior, str(r.get("author_id") or ""), stripped)
            if ctx:
                item["context"] = ctx
        questions.append(item)
        if len(questions) >= limit:
            break
    return questions


def parent_content(n: int, date_str: str) -> str:
    noun = "question" if n == 1 else "questions"
    return (
        f"🙋 **Open questions — {date_str}** — {n} unanswered {noun} from the last 24h. "
        "Jump in the thread and answer them."
    )


def thread_body(questions: List[Dict[str, Any]]) -> str:
    lines = [
        "Help a fren — reply on **their original message** (link below) and give the actual answer. Don't only reply here.",
        "",
    ]
    for i, q in enumerate(questions, 1):
        ask = (q.get("excerpt") or "").replace("\n", " ").strip()
        if len(ask) > 160:
            ask = ask[:157] + "…"
        name = ((q.get("author_name") or "someone").replace("\n", " ").strip() or "someone")[:40]
        lines.append(f"{i}. **{name}** — {ask}")
        ctx = (q.get("context") or "").replace("\n", " ").strip()
        if ctx:
            if len(ctx) > 90:
                ctx = ctx[:87] + "…"
            lines.append(f"   _re: {ctx}_")
        lines.append(f"   {q['url']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now(timezone.utc)
    future = datetime(now.year, now.month, now.day, hour, minute, tzinfo=timezone.utc)
    if now.hour > hour or (now.hour == hour and now.minute >= minute):
        future += timedelta(days=1)
    return (future - now).total_seconds()


async def run_open_questions_once():
    """Scout the rolling cache and post the #general thread. Empty list = no post."""
    if not discord_client:
        logger.error("Discord client not set. Cannot post open questions.")
        return

    general_channel_id = getattr(config, "general_channel_id", None)
    if not general_channel_id:
        logger.warning("GENERAL_CHANNEL_ID not configured. Skipping open questions.")
        return

    hours = int(getattr(config, "open_questions_lookback_hours", 24))
    limit = int(getattr(config, "open_questions_limit", 12))
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    messages_by_channel = database.get_messages_for_time_range(start, now)
    guild_id = getattr(config, "bridge_guild_id", None) or "1010083670599671838"
    questions = scout_questions(messages_by_channel, guild_id=guild_id, limit=limit)
    if not questions:
        logger.info("Open questions: none unanswered in the last %sh — skipping post", hours)
        return

    target = discord_client.get_channel(int(general_channel_id))
    if not target:
        logger.warning("General channel %s not found; cannot post open questions", general_channel_id)
        return

    date_str = now.strftime("%B %d, %Y").replace(" 0", " ")
    parent_text = parent_content(len(questions), date_str)
    body = thread_body(questions)
    try:
        master = await target.send(
            parent_text,
            allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True,
        )
        logger.info("Created open-questions parent %s in #general", master.id)
        thread = await master.create_thread(
            name=f"Open questions - {date_str}"[:100],
            auto_archive_duration=1440,
        )
        logger.info("Created open-questions thread %s", thread.id)
        for part in await split_long_message(body):
            await thread.send(
                part,
                allowed_mentions=discord.AllowedMentions.none(),
                suppress_embeds=True,
            )
        logger.info("Posted %s open questions into thread %s", len(questions), thread.id)
    except Exception:
        logger.error("Failed to post open-questions thread", exc_info=True)


@tasks.loop(hours=24)
async def daily_open_questions():
    await run_open_questions_once()


@daily_open_questions.before_loop
async def before_daily_open_questions():
    if not discord_client:
        logger.error("Discord client not set. Cannot start before_daily_open_questions.")
        await asyncio.sleep(60)
        return
    hour = int(getattr(config, "open_questions_hour", 23))
    minute = int(getattr(config, "open_questions_minute", 0))
    logger.info("Open questions scheduled for %02d:%02d UTC", hour, minute)
    await discord_client.wait_until_ready()
    wait = _seconds_until(hour, minute)
    logger.info("Waiting %.1f seconds until first open-questions post", wait)
    await asyncio.sleep(wait)
