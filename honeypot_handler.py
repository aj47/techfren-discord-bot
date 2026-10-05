"""
Guild-wide anti-spam for new and inactive accounts.

No decoy channel. Every guild message is checked, but nothing happens unless the
account fails immunity AND shows raid-shaped behaviour: blasting 3+ channels in
60s, or posting identical text in 3+ channels. A first post, a link, or a young
account on its own is never enough — those only made sense as triggers inside a
channel members were told not to post in.

1. IMMUNITY - established members are never actioned. Two tests, either one is
   enough:
     * the member holds a trusted role (see ``Rules.trusted_role_ids``)
     * the member has any lifetime points history in this guild

2. TRIGGERS - blast (3+ channels / 60s) or duplicate text (3+ channels / 5min).
   Neighbouring context (no prior messages, mention spam, young account, scam
   phrasing) is recorded on a hit but never causes an action on its own.

3. RESPONSE - any trigger is a 24h timeout, delete of the blast copies, and a ping
   to the owner in the log channel. This never bans; a human decides that.

``Rules.dry_run`` defaults to True: decisions are logged and announced but no
member is timed out or banned until it is explicitly switched off.

Trusted roles are an explicit allow-list rather than "any role above the join
role", because self-assignable cosmetic roles (the ``/color`` roles) sit above
the join role and would otherwise let a spam account immunise itself.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional, Sequence, Tuple

import discord

import database
from logging_config import logger


# ---------------------------------------------------------------------------
# Response actions
# ---------------------------------------------------------------------------

class Action:
    """Response to a honeypot hit, in increasing severity."""

    NONE = "none"          # immune, or nothing scored
    LOG = "log"            # record only, no member-visible effect
    TIMEOUT = "timeout"    # delete the message and time the member out
    BAN = "ban"            # delete recent messages and ban


# Signals. A trigger is behaviour decisive enough to act on alone; a context
# signal only ever adds colour to the log.
# ---------------------------------------------------------------------------
# Policy
#
# Deliberately constants rather than settings. The whole behaviour is "any
# trigger = delete the blast + 24h timeout + ping the owner"; it never bans.
# ---------------------------------------------------------------------------

# Trigger: posting in this many distinct channels within the window.
BLAST_CHANNELS = 3
BLAST_WINDOW_SECONDS = 60
# Trigger: identical text in this many distinct channels within the window.
# 3, not 2: pasting the same question in two rooms is a real (if messy) human
# move; the raid pattern is the same copy in three places.
DUPLICATE_CHANNELS = 3
DUPLICATE_WINDOW_MINUTES = 5

# How far back to delete copies of the blast (covers both trigger windows).
PURGE_WINDOW_SECONDS = max(BLAST_WINDOW_SECONDS, DUPLICATE_WINDOW_MINUTES * 60)

# In-memory copy of recent posts. ``on_message`` runs the honeypot *before*
# ``store_message``, and image posts wait on vision analysis before they are
# stored. A 5-channel image blast can therefore fire (or be purged) while the
# earlier copies are still in-flight and missing from the DB. Bound by the
# longer trigger window; a restart empties it (the DB is the fallback).
_RECENT_POST_MAX_PER_USER = 40
_recent_posts: Dict[Tuple[str, str], Deque["_RecentPost"]] = defaultdict(deque)


@dataclass(frozen=True)
class _RecentPost:
    message_id: str
    channel_id: str
    created_at: float  # time.monotonic()
    normalized_content: str


def reset_recent_posts() -> None:
    """Drop the in-memory ring. Tests only."""
    _recent_posts.clear()


def remember_message(message: discord.Message) -> None:
    """Record a guild message so blast/purge can see it before it is stored."""
    guild = getattr(message, "guild", None)
    author = getattr(message, "author", None)
    channel = getattr(message, "channel", None)
    if guild is None or author is None or channel is None:
        return
    key = (str(guild.id), str(author.id))
    post = _RecentPost(
        message_id=str(message.id),
        channel_id=str(channel.id),
        created_at=time.monotonic(),
        normalized_content=normalize_content(getattr(message, "content", "") or ""),
    )
    bucket = _recent_posts[key]
    bucket.append(post)
    _prune_recent_posts(bucket)
    while len(bucket) > _RECENT_POST_MAX_PER_USER:
        bucket.popleft()


def _prune_recent_posts(bucket: Deque[_RecentPost], now: Optional[float] = None) -> None:
    cutoff = (now if now is not None else time.monotonic()) - PURGE_WINDOW_SECONDS
    while bucket and bucket[0].created_at < cutoff:
        bucket.popleft()


def remembered_posts(
    user_id: str,
    guild_id: str,
    seconds: int,
    now: Optional[float] = None,
) -> List[_RecentPost]:
    """Posts remembered for this author inside ``seconds``."""
    bucket = _recent_posts.get((str(guild_id), str(user_id)))
    if not bucket:
        return []
    current = now if now is not None else time.monotonic()
    _prune_recent_posts(bucket, now=current)
    cutoff = current - int(seconds)
    return [post for post in bucket if post.created_at >= cutoff]

# Owner pinged on every actionable hit (AJ). A constant, not a setting: there
# is one person who asked to be notified, and a mis-set env would silently
# notify nobody.
NOTIFY_USER_ID = "200272755520700416"

# Immunity: an account at least this old, in the server at least this long, is
# established even with no role and no points history. Without this, "trusted
# role or any points" exempts only ~160 of this guild's 3,555 humans and aims the
# trap at 95% of the roster, mostly long-standing lurkers.
MATURE_ACCOUNT_DAYS = 30
SETTLED_JOIN_DAYS = 14

# Context signals: recorded and shown in the hit log, but never a trigger and
# never the reason for an action on their own.
YOUNG_ACCOUNT_DAYS = 30
MENTION_SPAM_COUNT = 5
RECENT_JOIN_MINUTES = 30

# What a trigger does. Discord timeouts cap at 28 days; 24h is the ask.
DEFAULT_TIMEOUT_MINUTES = 24 * 60

# Scam/recruitment phrasing seen in this server's own ban history.
_SCAM_PHRASES = (
    "join me on my",
    "come check us out",
    "looking for collaborators",
    "we are looking for",
    "free giveaway",
    "claim your",
    "dm me",
    "check my bio",
    "investment opportunity",
    "guaranteed returns",
)

_INVITE_RE = re.compile(
    r"(?:discord(?:app)?\.(?:gg|com/invite)|\.gg)/[A-Za-z0-9\-_]+",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
# A scheme-less domain is still a link as far as moderation is concerned;
# "visit spam.com" would otherwise slip past the link check.
_BARE_DOMAIN_RE = re.compile(
    r"(?:^|[\s(])(?:www\.)?[a-z0-9][a-z0-9\-]*\.(?:com|net|org|io|gg|xyz|info|biz|ru|cn|to|me|tv|co|site|online|shop|app|dev|link|club|live|icu|top|vip|cc|ws|su|tk|ml|ga|cf|gq)\b",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
# Zero-width and bidi/formatting characters, plus soft hyphen: invisible padding
# used to break naive duplicate matching.
_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\u00ad]")


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# Memoized result of :func:`load_rules`.
_RULES_CACHE: Optional["Rules"] = None

# {guild_id: (monotonic_timestamp, frozenset_of_channel_ids)}. The honeypot check
# runs on every message, so the registration set is held in memory.
_HONEYPOT_CHANNEL_CACHE: Dict[str, Tuple[float, frozenset]] = {}
_HONEYPOT_CHANNEL_CACHE_TTL = 300.0


@dataclass(frozen=True)
class Rules:
    """
    Resolved honeypot configuration.

    Held as plain values (rather than reading ``config`` directly) so the scoring
    logic can be exercised in tests without an environment.
    """

    enabled: bool = True
    # True: decide and log hits, never punish.
    dry_run: bool = True

    # Explicit allow-list of role IDs whose holders are immune -- never "any role
    # above the join role", because the self-assignable /color roles outrank the
    # join role and a positional rule could be self-granted.
    trusted_role_ids: frozenset = field(default_factory=frozenset)

    # Where decisions are reported. None writes the database row only.
    log_channel_id: Optional[str] = None

    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES


def load_rules(refresh: bool = False) -> Rules:
    """
    Build :class:`Rules` from ``config``.

    Imported lazily so this module can be imported (e.g. by tests) without a
    populated environment, and memoized because the result is consulted on every
    message.
    """
    global _RULES_CACHE
    if _RULES_CACHE is not None and not refresh:
        return _RULES_CACHE

    import config

    _RULES_CACHE = Rules(
        enabled=getattr(config, "HONEYPOT_ENABLED", False),
        dry_run=getattr(config, "HONEYPOT_DRY_RUN", True),
        trusted_role_ids=frozenset(getattr(config, "HONEYPOT_TRUSTED_ROLE_IDS", ())),
        log_channel_id=getattr(config, "HONEYPOT_LOG_CHANNEL_ID", None),
        timeout_minutes=getattr(config, "HONEYPOT_TIMEOUT_MINUTES", 60),
    )
    return _RULES_CACHE


# ---------------------------------------------------------------------------
# Facts and decisions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HitFacts:
    """Everything the scoring rules are allowed to look at."""

    user_id: str
    author_name: str = ""

    # Account creation, from the user ID snowflake (discord.py exposes this as
    # ``User.created_at``). None when unknown.
    account_created_at: Optional[datetime] = None
    # When the member joined this guild, if known.
    joined_at: Optional[datetime] = None

    # Lifetime points in this guild (never decreases when points are spent).
    lifetime_points: int = 0
    # Names of trusted roles held. Empty means none.
    trusted_role_names: Tuple[str, ...] = ()

    is_bot: bool = False
    is_webhook: bool = False

    # Messages this account sent before this one, if known. None means unknown
    # (treated as "not enough evidence" rather than zero).
    prior_message_count: Optional[int] = None

    # Distinct channels this author posted in during the blast window, including
    # the current one.
    channels_in_blast_window: Tuple[str, ...] = ()
    # Distinct channels where this author posted identical content, including the
    # current one.
    channels_with_duplicate_content: Tuple[str, ...] = ()

    content: str = ""
    mention_count: int = 0

    # Honeypot hits already recorded against this account in this guild. A prior
    # strike is what allows a ban on the next one.
    prior_hits: int = 0


@dataclass(frozen=True)
class Decision:
    """The outcome of scoring one honeypot hit."""

    immune: bool
    action: str
    immune_reason: Optional[str] = None
    # Reasons this account was acted on at all.
    triggers: Tuple[str, ...] = ()
    # Context that informed the log but never caused the action.
    context: Tuple[str, ...] = ()
    # Set when an established account earned a ban and was timed out instead.
    ban_withheld: Optional[str] = None

    @property
    def score(self) -> int:
        """Number of independent triggers -- what the tiers are decided on."""
        return len(self.triggers)

    @property
    def actionable(self) -> bool:
        """True when the decision asks for a real moderation action."""
        return self.action in (Action.TIMEOUT, Action.BAN)

    def explain(self) -> str:
        """One-line human-readable summary, for logs and mod-log embeds."""
        if self.immune:
            return f"immune ({self.immune_reason})"
        if not self.triggers and not self.context:
            return "no signals"
        parts = []
        if self.triggers:
            parts.append(f"{len(self.triggers)} trigger(s): " + ", ".join(self.triggers))
        else:
            parts.append("no triggers")
        if self.context:
            parts.append("context: " + ", ".join(self.context))
        if self.ban_withheld:
            parts.append(f"ban withheld: {self.ban_withheld}")
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# Pure scoring
# ---------------------------------------------------------------------------

def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as an aware UTC datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_content(content: str) -> str:
    """
    Fold a message to a form suitable for duplicate comparison.

    Invisible characters are removed before collapsing whitespace: spammers pad
    repeated text with zero-width joiners and soft hyphens precisely so that an
    exact-match duplicate check misses it.
    """
    text = _INVISIBLE_RE.sub("", content or "")
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def contains_invite(content: str) -> bool:
    """True when the message carries a Discord invite link."""
    return bool(_INVITE_RE.search(content or ""))


def contains_link(content: str) -> bool:
    """True when the message carries a URL, with or without a scheme."""
    return bool(_URL_RE.search(content or "") or _BARE_DOMAIN_RE.search(content or ""))


def matches_scam_phrasing(content: str) -> bool:
    """True when the message contains phrasing from known spam pitches."""
    lowered = (content or "").lower()
    return any(phrase in lowered for phrase in _SCAM_PHRASES)


def established_reason(
    facts: HitFacts,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """
    Return why this account is too established to ban, or None.

    Established accounts are not immune: a blast still means a deleted message
    and a timeout. But an account this old, in the server this long, has earned
    the benefit of the doubt on intent, and a permaban is the one response it can
    never receive -- however it behaves, and however often.
    """
    created = _as_utc(facts.account_created_at)
    joined = _as_utc(facts.joined_at)
    if created is None or joined is None:
        return None

    current = _as_utc(now) or datetime.now(timezone.utc)
    account_days = (current - created).days
    join_days = (current - joined).days
    if account_days >= MATURE_ACCOUNT_DAYS and join_days >= SETTLED_JOIN_DAYS:
        return f"established account ({account_days}d old, joined {join_days}d ago)"
    return None


def immunity_reason(
    facts: HitFacts,
    rules: Rules,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """
    Return why this account must not be actioned, or None if it is not immune.

    Bots and webhooks are never actioned. Beyond that, an account holding a trusted
    role or with any points history has contributed here, and is left alone
    entirely. Age alone does not grant that: see :func:`established_reason`.
    """
    if facts.is_bot:
        return "bot account"
    if facts.is_webhook:
        return "webhook"
    if facts.trusted_role_names:
        return "trusted role: " + ", ".join(sorted(facts.trusted_role_names))
    if facts.lifetime_points >= 1:
        return f"points history ({facts.lifetime_points} lifetime)"
    return None


def find_triggers(
    facts: HitFacts,
    rules: Rules,
    now: Optional[datetime] = None,
) -> Tuple[List[str], List[str]]:
    """
    Find the triggers and context signals for a message that failed immunity.

    A trigger is behaviour with no innocent reading, and one is enough to punish.
    Context never causes an action on its own; it is recorded so a moderator
    reading the log can see the whole picture.
    """
    now = _as_utc(now) or datetime.now(timezone.utc)
    triggers: List[str] = []
    context: List[str] = []

    # --- triggers -----------------------------------------------------------

    created = _as_utc(facts.account_created_at)
    account_age = now - created if created is not None else None

    if len(facts.channels_in_blast_window) >= BLAST_CHANNELS:
        triggers.append(
            f"blast:{len(facts.channels_in_blast_window)} channels/"
            f"{BLAST_WINDOW_SECONDS}s"
        )

    if len(facts.channels_with_duplicate_content) >= DUPLICATE_CHANNELS:
        triggers.append(
            f"duplicate_content:{len(facts.channels_with_duplicate_content)} channels"
        )

    # --- context ------------------------------------------------------------

    if account_age is not None and account_age < timedelta(days=YOUNG_ACCOUNT_DAYS):
        context.append(f"young_account:{account_age.days}d")

    if facts.prior_message_count == 0:
        context.append("no_prior_messages")
    elif facts.prior_message_count is None:
        # Unknown history is not evidence of a clean one.
        context.append("prior_history_unknown")

    if facts.mention_count >= MENTION_SPAM_COUNT:
        context.append(f"mention_spam:{facts.mention_count}")

    joined = _as_utc(facts.joined_at)
    if joined is not None and (now - joined) < timedelta(minutes=RECENT_JOIN_MINUTES):
        context.append("just_joined")

    if matches_scam_phrasing(facts.content):
        context.append("scam_phrasing")

    if facts.prior_hits:
        context.append(f"prior_strikes:{facts.prior_hits}")

    return triggers, context


def classify(
    facts: HitFacts,
    rules: Optional[Rules] = None,
    now: Optional[datetime] = None,
) -> Decision:
    """
    Decide what to do about a guild message from a non-immune account.

    Any trigger is a 24h timeout. This function never returns ``Action.BAN`` —
    a human decides bans. Context-only messages are ignored (not logged): this
    runs on every message.
    """
    rules = rules or Rules()

    reason = immunity_reason(facts, rules, now=now)
    if reason is not None:
        return Decision(immune=True, action=Action.NONE, immune_reason=reason)

    triggers, context = find_triggers(facts, rules, now=now)

    action = Action.TIMEOUT if triggers else Action.NONE

    return Decision(
        immune=False,
        action=action,
        triggers=tuple(triggers),
        context=tuple(context),
    )



# ---------------------------------------------------------------------------
# Discord glue
# ---------------------------------------------------------------------------

async def is_honeypot_channel(channel_id: str, guild_id: str) -> bool:
    """
    True when this channel is registered as a honeypot in this guild.

    The registration set is cached in memory because this is consulted on every
    single message; without the cache it would be a database round-trip per
    message in every channel.
    """
    return str(channel_id) in _cached_honeypot_channel_ids(str(guild_id))


def _cached_honeypot_channel_ids(guild_id: str) -> frozenset:
    """Registered honeypot channel IDs for a guild, refreshed at most every TTL."""
    now = time.monotonic()
    entry = _HONEYPOT_CHANNEL_CACHE.get(guild_id)
    if entry is not None and now - entry[0] < _HONEYPOT_CHANNEL_CACHE_TTL:
        return entry[1]

    ids = frozenset(
        str(row['channel_id'])
        for row in database.get_honeypot_channels_for_guild(guild_id)
    )
    _HONEYPOT_CHANNEL_CACHE[guild_id] = (now, ids)
    return ids


def invalidate_channel_cache() -> None:
    """Drop the cached honeypot channel set (call after register/unregister)."""
    _HONEYPOT_CHANNEL_CACHE.clear()


def trusted_role_names(member: discord.Member, rules: Rules) -> Tuple[str, ...]:
    """
    Names of the trusted roles this member holds.

    Managed roles (integration/bot roles) are ignored, and the allow-list is
    consulted by ID so cosmetic roles cannot count as trust.
    """
    if not rules.trusted_role_ids:
        return ()
    trusted = {str(rid) for rid in rules.trusted_role_ids}
    names = []
    for role in getattr(member, "roles", ()) or ():
        if str(role.id) in trusted and not role.managed:
            names.append(role.name)
    return tuple(names)


def _count_mentions(message: discord.Message) -> int:
    """Mentions plus role pings, which Discord reports separately."""
    return len(getattr(message, "mentions", ()) or ()) + len(
        getattr(message, "role_mentions", ()) or ()
    )


async def collect_facts(message: discord.Message, rules: Rules) -> HitFacts:
    """
    Gather the scoring inputs for a message from Discord and the database.

    Every database read is best-effort: a lookup failure yields an unknown value
    rather than aborting the check, so a spam message is never let through
    because a query failed.
    """
    author = message.author
    guild_id = str(getattr(message.guild, "id", "") or "")
    user_id = str(author.id)

    lifetime_points = 0
    try:
        summary = database.get_user_points_summary(user_id, guild_id)
        lifetime_points = int(summary.get("lifetime_points", 0))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: points lookup failed for {user_id}: {exc}")

    prior_message_count: Optional[int] = None
    try:
        activity = database.get_member_activity(user_id, guild_id)
        # store_message runs after this check, so the current message is not
        # counted here: the count is exactly the messages that preceded it.
        if activity is None or activity.get("message_count") is None:
            prior_message_count = None
        else:
            prior_message_count = int(activity["message_count"])
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: activity lookup failed for {user_id}: {exc}")

    channels_in_window: Tuple[str, ...] = ()
    duplicates: Tuple[str, ...] = ()
    try:
        channels_in_window = tuple(
            database.get_recent_channel_ids(
                user_id, guild_id, seconds=BLAST_WINDOW_SECONDS
            )
        )
        duplicates = tuple(
            database.get_recent_duplicate_channels(
                user_id,
                guild_id,
                normalize_content(message.content),
                minutes=DUPLICATE_WINDOW_MINUTES,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: behaviour lookup failed for {user_id}: {exc}")

    # Union in-flight posts the DB has not stored yet (image analysis holds
    # store_message until after this handler has already run on later copies).
    for post in remembered_posts(user_id, guild_id, BLAST_WINDOW_SECONDS):
        if post.channel_id not in channels_in_window:
            channels_in_window = channels_in_window + (post.channel_id,)
    current_norm = normalize_content(message.content)
    if current_norm:
        for post in remembered_posts(
            user_id, guild_id, DUPLICATE_WINDOW_MINUTES * 60
        ):
            if (
                post.normalized_content == current_norm
                and post.channel_id not in duplicates
            ):
                duplicates = duplicates + (post.channel_id,)

    current_channel = str(message.channel.id)
    if current_channel not in channels_in_window:
        channels_in_window = channels_in_window + (current_channel,)
    if current_norm and current_channel not in duplicates:
        duplicates = duplicates + (current_channel,)

    member = author if isinstance(author, discord.Member) else None

    prior_hits = 0
    try:
        prior_hits = int(
            database.count_honeypot_hits(user_id, guild_id)
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: prior hit lookup failed for {user_id}: {exc}")

    return HitFacts(
        user_id=user_id,
        author_name=str(author),
        account_created_at=getattr(author, "created_at", None),
        joined_at=getattr(member, "joined_at", None),
        lifetime_points=lifetime_points,
        trusted_role_names=trusted_role_names(member, rules) if member else (),
        is_bot=bool(getattr(author, "bot", False)),
        is_webhook=bool(getattr(message, "webhook_id", None)),
        prior_message_count=prior_message_count,
        channels_in_blast_window=channels_in_window,
        channels_with_duplicate_content=duplicates,
        content=message.content or "",
        mention_count=_count_mentions(message),
        prior_hits=prior_hits,
    )


async def _post_log_embed(
    message: discord.Message,
    decision: Decision,
    rules: Rules,
    enforced: bool,
) -> None:
    """Report a hit to the configured honeypot log channel."""
    if not rules.log_channel_id or not message.guild:
        return
    channel = message.guild.get_channel(int(rules.log_channel_id))
    if channel is None:
        logger.warning(
            f"Honeypot: log channel {rules.log_channel_id} not found in guild "
            f"{message.guild.id}"
        )
        return
    if not isinstance(channel, discord.abc.Messageable):
        logger.warning(
            f"Honeypot: log channel {rules.log_channel_id} is not messageable"
        )
        return

    mode = "enforced" if enforced else "DRY RUN"
    colour = discord.Color.orange() if decision.action == Action.TIMEOUT else discord.Color.gold()

    embed = discord.Embed(
        title=f"🍯 Anti-spam TIMEOUT ({mode})",
        description=decision.explain(),
        color=colour,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Account",
        value=f"{message.author.mention} (`{message.author.id}`)",
        inline=False,
    )
    embed.add_field(
        name="Channel",
        value=f"{getattr(message.channel, 'mention', f'#{message.channel.id}')} "
        f"(`{message.channel.id}`)",
        inline=False,
    )
    created = _as_utc(getattr(message.author, "created_at", None))
    if created is not None:
        age_days = (datetime.now(timezone.utc) - created).days
        embed.add_field(name="Account age", value=f"{age_days}d", inline=True)
    embed.add_field(
        name="Timeout",
        value=f"{rules.timeout_minutes}m — not banned, ban by hand if needed",
        inline=True,
    )
    body = (message.content or "").strip() or "*(no text content)*"
    embed.add_field(name="Content", value=body[:1000], inline=False)

    try:
        await channel.send(content=f"<@{NOTIFY_USER_ID}>", embed=embed)
    except Exception as exc:  # pragma: no cover - network/permission dependent
        logger.error(f"Honeypot: failed to post log embed: {exc}", exc_info=True)


def _resolve_purge_channel(guild: discord.Guild, channel_id: int):
    """Text channel or thread; ``get_channel`` alone misses threads."""
    getter = getattr(guild, "get_channel_or_thread", None)
    if getter is not None:
        return getter(channel_id)
    channel = guild.get_channel(channel_id)
    if channel is not None:
        return channel
    get_thread = getattr(guild, "get_thread", None)
    return get_thread(channel_id) if get_thread is not None else None


async def _purge_recent_messages(message: discord.Message) -> int:
    """Delete this author's recent messages across channels. Best-effort."""
    guild = message.guild
    if guild is None:
        return 0
    user_id = str(message.author.id)
    guild_id = str(guild.id)
    rows = []
    try:
        rows = list(
            database.get_recent_message_ids(
                user_id, guild_id, seconds=PURGE_WINDOW_SECONDS
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: purge lookup failed for {user_id}: {exc}")

    for post in remembered_posts(user_id, guild_id, PURGE_WINDOW_SECONDS):
        rows.append(
            {"message_id": post.message_id, "channel_id": post.channel_id}
        )

    seen = {(str(message.channel.id), str(message.id))}
    deleted = 0
    try:
        await message.delete()
        deleted += 1
    except discord.NotFound:
        pass
    except Exception as exc:
        logger.warning(f"Honeypot: could not delete triggering message {message.id}: {exc}")

    for row in rows:
        key = (str(row["channel_id"]), str(row["message_id"]))
        if key in seen:
            continue
        seen.add(key)
        try:
            channel = _resolve_purge_channel(guild, int(row["channel_id"]))
        except (TypeError, ValueError):
            continue
        if channel is None or not hasattr(channel, "get_partial_message"):
            logger.warning(
                f"Honeypot: purge skipped {row['message_id']} — "
                f"channel {row['channel_id']} not in cache"
            )
            continue
        try:
            await channel.get_partial_message(int(row["message_id"])).delete()
            deleted += 1
        except discord.NotFound:
            continue
        except (discord.Forbidden, discord.HTTPException, ValueError) as exc:
            logger.warning(
                f"Honeypot: could not delete {row['message_id']} in {row['channel_id']}: {exc}"
            )
            continue
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                f"Honeypot: could not delete {row['message_id']} in {row['channel_id']}: {exc}"
            )
    return deleted


async def _enforce(
    message: discord.Message,
    decision: Decision,
    rules: Rules,
) -> bool:
    """Timeout and delete the blast. Never bans. Returns True when the timeout landed."""
    if decision.action != Action.TIMEOUT:
        return False
    member = message.author
    if not isinstance(member, discord.Member):
        logger.warning(
            f"Honeypot: refusing to act on non-member author {member.id} "
            f"(no guild membership object)"
        )
        return False

    reason = (
        f"Anti-spam #{getattr(message.channel, 'name', message.channel.id)}: "
        f"{decision.explain()}"
    )

    timed_out = False
    try:
        await member.timeout(
            timedelta(minutes=rules.timeout_minutes), reason=reason
        )
        timed_out = True
    except discord.Forbidden:
        logger.error(
            f"Honeypot: cannot timeout {member.id} - missing permission or "
            f"role hierarchy ({reason})"
        )
    except discord.HTTPException as exc:
        logger.error(f"Honeypot: timeout failed for {member.id}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            f"Honeypot: unexpected error during timeout for {member.id}: {exc}",
            exc_info=True,
        )

    try:
        deleted = await _purge_recent_messages(message)
        logger.info(
            f"Honeypot: purged {deleted} message(s) for {member.id} "
            f"({decision.explain()})"
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: purge failed for {member.id}: {exc}", exc_info=True)

    return timed_out


async def handle_honeypot_message(
    message: discord.Message,
    rules: Optional[Rules] = None,
) -> Optional[Decision]:
    """
    Score and (unless dry-running) act on a guild message.

    Returns the decision, or None when the message was ignored (disabled,
    immune, or no trigger). Never raises: a failure must not break normal
    message handling. Immune members are skipped before any database work so
    this is cheap on ordinary chat.
    """
    rules = rules or load_rules()

    if not rules.enabled:
        return None
    if not rules.trusted_role_ids:
        # Safety interlock, deliberately not configurable: with no trusted roles
        # the only remaining immunity is points history, which would point the
        # trap at most of the server. Refuse to act rather than degrade into that.
        logger.error(
            "Honeypot: refusing to act - HONEYPOT_TRUSTED_ROLE_IDS is empty. "
            "Set the trusted role IDs before enabling."
        )
        return None

    author = message.author
    if getattr(author, "bot", False) or getattr(message, "webhook_id", None):
        return None
    if isinstance(author, discord.Member) and trusted_role_names(author, rules):
        return None

    # Record before scoring so a later copy in the same blast can see this one
    # even if store_message has not run yet.
    remember_message(message)

    try:
        facts = await collect_facts(message, rules)
        decision = classify(facts, rules)

        if decision.immune or not decision.actionable:
            return None

        enforced = False
        if not rules.dry_run:
            enforced = await _enforce(message, decision, rules)
        else:
            logger.warning(
                f"Honeypot DRY RUN: would {decision.action} {facts.user_id} "
                f"(#{getattr(message.channel, 'name', '?')}) - {decision.explain()}"
            )

        try:
            database.record_honeypot_hit(
                user_id=facts.user_id,
                user_name=facts.author_name,
                channel_id=str(message.channel.id),
                channel_name=str(getattr(message.channel, "name", "")),
                guild_id=str(getattr(message.guild, "id", "")),
                score=decision.score,
                action=decision.action,
                enforced=enforced,
                reasons=decision.explain(),
                content=message.content or "",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Honeypot: failed to record hit: {exc}", exc_info=True)

        await _post_log_embed(message, decision, rules, enforced)
        return decision

    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: handler error: {exc}", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Channel registration
# ---------------------------------------------------------------------------

async def register_honeypot_channel(
    channel: discord.TextChannel,
    actor: discord.abc.User,
) -> bool:
    """
    Mark a channel as a honeypot and warn humans in the topic.

    The topic is the only thing standing between a curious member and a
    timeout, so it is set with the warning first.
    """
    guild = channel.guild
    added = database.add_honeypot_channel(
        channel_id=str(channel.id),
        channel_name=channel.name,
        guild_id=str(guild.id),
        guild_name=guild.name,
        created_by_id=str(actor.id),
        created_by_name=str(actor),
    )
    if not added:
        return False

    logger.warning(
        f"Honeypot: #{channel.name} ({channel.id}) registered by {actor} in {guild.name}"
    )
    invalidate_channel_cache()

    warning = (
        "🍯 TRAP CHANNEL - DO NOT POST HERE. "
        "Messages posted in this channel are treated as spam and are actioned "
        "automatically. Read-only for members."
    )
    try:
        await channel.edit(topic=warning, reason=f"Honeypot channel set by {actor}")
    except discord.Forbidden:
        logger.warning(f"Honeypot: cannot set topic on {channel.id} - missing permission")
    except Exception as exc:
        logger.warning(f"Honeypot: could not set topic on {channel.id}: {exc}")

    return True


async def unregister_honeypot_channel(channel: discord.TextChannel) -> bool:
    """Remove honeypot status from a channel and clear the topic warning."""
    guild_id = str(getattr(channel.guild, "id", "") or "")
    if not database.remove_honeypot_channel(str(channel.id), guild_id):
        return False

    logger.info(f"Honeypot: channel {channel.id} removed")
    invalidate_channel_cache()

    # Clear the topic warning so a former trap does not keep a stale sign on it.
    try:
        await channel.edit(topic=None, reason="Honeypot channel removed")  # type: ignore[arg-type]
    except discord.Forbidden:
        logger.warning(f"Honeypot: cannot clear topic on {channel.id} - missing permission")
    except Exception as exc:
        logger.warning(f"Honeypot: could not clear topic on {channel.id}: {exc}")

    return True


def list_honeypot_channels(guild_id: str) -> List[Dict]:
    """Registered honeypot channels for a guild."""
    return database.get_honeypot_channels_for_guild(str(guild_id))
