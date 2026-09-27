"""
Honeypot trap for new and inactive accounts.

A honeypot channel is a channel that real members have no reason to post in. It
is left visible (so link-spamming bots and raid accounts can find it) and marked
with an unmistakable warning in its topic. Anything that posts there is a signal
in itself, because a human who reads the warning does not post.

The handler runs in two stages:

1. IMMUNITY - established members are never actioned. Two tests, either one is
   enough:
     * the member holds a trusted role (see ``Rules.trusted_role_ids``)
     * the member has any lifetime points history in this guild
   Membership of neither means the account has never contributed here, which for
   a channel members are told not to post in is itself the finding.

2. SCORING - non-immune accounts are scored. A "primary" signal is behaviour that
   has no innocent reading: a message blast across channels, a link dropped in
   the trap channel, an account that did not exist yesterday, identical text
   repeated across channels. Corroborating signals (account age, no prior
   messages, mention spam) never ban on their own - they raise the response from
   a timeout to a ban.

``Rules.dry_run`` defaults to True: decisions are logged and announced but no
member is timed out or banned until it is explicitly switched off.

Trusted roles are an explicit allow-list rather than "any role above the join
role", because self-assignable cosmetic roles (the ``/color`` roles) sit above
the join role and would otherwise let a spam account immunise itself.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

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


# Signal weights. A primary signal is decisive behaviour; a corroborating signal
# is only meaningful alongside one.
PRIMARY_WEIGHT = 3
CORROBORATING_WEIGHT = 2
WEAK_WEIGHT = 1

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
    # When True, decisions are logged/announced but never enforced.
    dry_run: bool = True

    # Explicit allow-list of role IDs whose holders are immune.
    trusted_role_ids: frozenset = field(default_factory=frozenset)
    # Safety interlock: refuse to act when no trusted roles are configured, so a
    # half-finished setup cannot become "ban everyone without points". Set this
    # to False only if points history alone should decide immunity.
    require_trusted_role_ids: bool = True

    # Where decisions are reported. None disables the mod-log post (a DB row is
    # still written for every hit).
    log_channel_id: Optional[str] = None

    # Acknowledge the hit in the trap channel. Off by default: replying in the
    # channel teaches bots that it is live.
    announce_in_channel: bool = False

    # Scoring thresholds.
    ban_score: int = 5
    timeout_score: int = 2

    timeout_minutes: int = 60
    # Seconds of history purged when banning (Discord caps this at 7 days).
    purge_seconds: int = 86400

    # Primary signal shapes.
    blast_channels: int = 3
    blast_window_seconds: int = 60
    fresh_account_hours: int = 24
    duplicate_channels: int = 2
    duplicate_window_minutes: int = 5

    # Corroborating signal shapes.
    young_account_days: int = 30
    mention_spam_count: int = 5
    recent_join_minutes: int = 30

    # Immunity by maturity: an account at least this old, in the guild at least
    # this long, counts as established even with no role and no points history.
    mature_account_days: int = 30
    settled_join_days: int = 14
    immunity_needs_maturity: bool = True

    # Never permaban on a first strike: a ban additionally needs either a prior
    # recorded hit on this account or this many independent primary signals.
    ban_requires_repeat: bool = True
    ban_min_primary_signals: int = 2


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
        require_trusted_role_ids=getattr(
            config, "HONEYPOT_REQUIRE_TRUSTED_ROLES", True
        ),
        log_channel_id=getattr(config, "HONEYPOT_LOG_CHANNEL_ID", None),
        announce_in_channel=getattr(config, "HONEYPOT_ANNOUNCE_IN_CHANNEL", False),
        ban_score=getattr(config, "HONEYPOT_BAN_SCORE", 5),
        timeout_score=getattr(config, "HONEYPOT_TIMEOUT_SCORE", 2),
        timeout_minutes=getattr(config, "HONEYPOT_TIMEOUT_MINUTES", 60),
        purge_seconds=getattr(config, "HONEYPOT_PURGE_SECONDS", 86400),
        blast_channels=getattr(config, "HONEYPOT_BLAST_CHANNELS", 3),
        blast_window_seconds=getattr(config, "HONEYPOT_BLAST_WINDOW_SECONDS", 60),
        fresh_account_hours=getattr(config, "HONEYPOT_FRESH_ACCOUNT_HOURS", 24),
        duplicate_channels=getattr(config, "HONEYPOT_DUPLICATE_CHANNELS", 2),
        duplicate_window_minutes=getattr(config, "HONEYPOT_DUPLICATE_WINDOW_MINUTES", 5),
        young_account_days=getattr(config, "HONEYPOT_YOUNG_ACCOUNT_DAYS", 30),
        mention_spam_count=getattr(config, "HONEYPOT_MENTION_SPAM_COUNT", 5),
        mature_account_days=getattr(config, "HONEYPOT_MATURE_ACCOUNT_DAYS", 30),
        settled_join_days=getattr(config, "HONEYPOT_SETTLED_JOIN_DAYS", 14),
        immunity_needs_maturity=getattr(
            config, "HONEYPOT_IMMUNITY_NEEDS_MATURITY", True
        ),
        ban_requires_repeat=getattr(config, "HONEYPOT_BAN_REQUIRES_REPEAT", True),
        ban_min_primary_signals=getattr(
            config, "HONEYPOT_BAN_MIN_PRIMARY_SIGNALS", 2
        ),
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
    score: int = 0
    immune_reason: Optional[str] = None
    primary: Tuple[str, ...] = ()
    corroborating: Tuple[str, ...] = ()

    @property
    def actionable(self) -> bool:
        """True when the decision asks for a real moderation action."""
        return self.action in (Action.TIMEOUT, Action.BAN)

    def explain(self) -> str:
        """One-line human-readable summary, for logs and mod-log embeds."""
        if self.immune:
            return f"immune ({self.immune_reason})"
        if not self.primary and not self.corroborating:
            return "no signals"
        parts = [f"score {self.score}"]
        if self.primary:
            parts.append("primary: " + ", ".join(self.primary))
        if self.corroborating:
            parts.append("corroborating: " + ", ".join(self.corroborating))
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


def immunity_reason(
    facts: HitFacts,
    rules: Rules,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """
    Return why this account must not be actioned, or None if it is not immune.

    Bots and webhooks are never actioned. Beyond that, an account is established
    if it holds a trusted role, has ever earned points, or is simply old enough to
    have proved itself (see ``rules.mature_account_days``).
    """
    if facts.is_bot:
        return "bot account"
    if facts.is_webhook:
        return "webhook"
    if facts.trusted_role_names:
        return "trusted role: " + ", ".join(sorted(facts.trusted_role_names))
    if facts.lifetime_points >= 1:
        return f"points history ({facts.lifetime_points} lifetime)"

    # Immunity by maturity. Without this, "trusted role or points" covers only the
    # few hundred members who have ever earned a point: the rest of the roster are
    # quiet lurkers who hold just the join role, and the trap would be pointed at
    # them rather than at new accounts.
    if rules.immunity_needs_maturity:
        created = _as_utc(facts.account_created_at)
        joined = _as_utc(facts.joined_at)
        if created is not None and joined is not None:
            current = _as_utc(now) or datetime.now(timezone.utc)
            account_days = (current - created).days
            join_days = (current - joined).days
            if (
                account_days >= rules.mature_account_days
                and join_days >= rules.settled_join_days
            ):
                return (
                    f"established account ({account_days}d old, joined {join_days}d ago)"
                )
    return None


def score_facts(
    facts: HitFacts,
    rules: Rules,
    now: Optional[datetime] = None,
) -> Tuple[int, List[str], List[str]]:
    """
    Score an account that has already failed immunity.

    Returns ``(total, primary_signals, corroborating_signals)``.
    """
    now = _as_utc(now) or datetime.now(timezone.utc)
    total = 0
    primary: List[str] = []
    corroborating: List[str] = []

    # --- primary: behaviour with no innocent reading ------------------------

    if len(facts.channels_in_blast_window) >= rules.blast_channels:
        primary.append(
            f"blast:{len(facts.channels_in_blast_window)} channels/"
            f"{rules.blast_window_seconds}s"
        )
        total += PRIMARY_WEIGHT

    if contains_invite(facts.content):
        primary.append("invite_in_trap_channel")
        total += PRIMARY_WEIGHT
    elif _URL_RE.search(facts.content or ""):
        primary.append("link_in_trap_channel")
        total += PRIMARY_WEIGHT
    elif _BARE_DOMAIN_RE.search(facts.content or ""):
        # Weaker than a real URL: "spam.com" in prose is suspect but could be an
        # honest mention, so it corroborates rather than triggering a timeout on
        # its own.
        corroborating.append("bare_domain_in_trap_channel")
        total += CORROBORATING_WEIGHT

    account_age = None
    created = _as_utc(facts.account_created_at)
    if created is not None:
        account_age = now - created
        if account_age < timedelta(hours=rules.fresh_account_hours):
            primary.append(f"account_age:{account_age.days}d{account_age.seconds // 3600}h")
            total += PRIMARY_WEIGHT

    if len(facts.channels_with_duplicate_content) >= rules.duplicate_channels:
        primary.append(
            f"duplicate_content:{len(facts.channels_with_duplicate_content)} channels"
        )
        total += PRIMARY_WEIGHT

    # --- corroborating: raises the response, never bans alone ---------------

    if account_age is not None and account_age < timedelta(days=rules.young_account_days):
        corroborating.append(f"young_account:{account_age.days}d")
        total += CORROBORATING_WEIGHT

    if facts.prior_message_count == 0:
        corroborating.append("no_prior_messages")
        total += CORROBORATING_WEIGHT
    elif facts.prior_message_count is None:
        # Unknown history is not evidence of a clean one. Worth recording only.
        corroborating.append("prior_history_unknown")
        total += WEAK_WEIGHT

    if facts.mention_count >= rules.mention_spam_count:
        corroborating.append(f"mention_spam:{facts.mention_count}")
        total += CORROBORATING_WEIGHT

    joined = _as_utc(facts.joined_at)
    if joined is not None and (now - joined) < timedelta(minutes=rules.recent_join_minutes):
        corroborating.append("just_joined")
        total += WEAK_WEIGHT

    if matches_scam_phrasing(facts.content):
        corroborating.append("scam_phrasing")
        total += WEAK_WEIGHT

    return total, primary, corroborating


def classify(
    facts: HitFacts,
    rules: Optional[Rules] = None,
    now: Optional[datetime] = None,
) -> Decision:
    """
    Decide what to do about a message posted in a honeypot channel.

    Banning requires both a primary signal and ``rules.ban_score`` points, so a
    pile of weak circumstantial signals can never permaban an active member.
    """
    rules = rules or Rules()

    reason = immunity_reason(facts, rules, now=now)
    if reason is not None:
        return Decision(immune=True, action=Action.NONE, immune_reason=reason)

    total, primary, corroborating = score_facts(facts, rules, now=now)

    ban_ok = bool(primary) and total >= rules.ban_score
    if ban_ok and rules.ban_requires_repeat:
        # "Never permaban on a first strike": a ban needs either this many
        # independent primary signals, or this account having been caught before.
        ban_ok = (
            len(primary) >= rules.ban_min_primary_signals or facts.prior_hits >= 1
        )

    if ban_ok:
        action = Action.BAN
    elif total >= rules.timeout_score:
        action = Action.TIMEOUT
    elif total > 0:
        action = Action.LOG
    else:
        action = Action.NONE

    return Decision(
        immune=False,
        action=action,
        score=total,
        primary=tuple(primary),
        corroborating=tuple(corroborating),
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
    names = []
    for role in getattr(member, "roles", ()) or ():
        if role.id in rules.trusted_role_ids and not role.managed:
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
        # store_message runs after the trap check, so a trap-channel message is
        # never counted here: the count is exactly the messages that preceded it.
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
                user_id, guild_id, seconds=rules.blast_window_seconds
            )
        )
        duplicates = tuple(
            database.get_recent_duplicate_channels(
                user_id,
                guild_id,
                normalize_content(message.content),
                minutes=rules.duplicate_window_minutes,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Honeypot: behaviour lookup failed for {user_id}: {exc}")

    current_channel = str(message.channel.id)
    if current_channel not in channels_in_window:
        channels_in_window = channels_in_window + (current_channel,)
    if normalize_content(message.content) and current_channel not in duplicates:
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
    colour = {
        Action.BAN: discord.Color.red(),
        Action.TIMEOUT: discord.Color.orange(),
        Action.LOG: discord.Color.gold(),
    }.get(decision.action, discord.Color.light_grey())

    embed = discord.Embed(
        title=f"🍯 Honeypot {decision.action.upper()} ({mode})",
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
    me = message.guild.me
    if me is not None and getattr(message.channel, "permissions_for", None):
        if message.channel.permissions_for(me).read_message_history:
            embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
    body = (message.content or "").strip() or "*(no text content)*"
    embed.add_field(name="Content", value=body[:1000], inline=False)

    try:
        await channel.send(embed=embed)
    except Exception as exc:  # pragma: no cover - network/permission dependent
        logger.error(f"Honeypot: failed to post log embed: {exc}", exc_info=True)


async def _enforce(
    message: discord.Message,
    decision: Decision,
    rules: Rules,
) -> bool:
    """Apply the decided action. Returns True when Discord accepted it."""
    member = message.author
    if not isinstance(member, discord.Member):
        logger.warning(
            f"Honeypot: refusing to act on non-member author {member.id} "
            f"(no guild membership object)"
        )
        return False

    reason = f"Honeypot channel #{getattr(message.channel, 'name', message.channel.id)}: {decision.explain()}"

    try:
        if decision.action == Action.BAN:
            await member.ban(reason=reason, delete_message_seconds=rules.purge_seconds)
            return True
        if decision.action == Action.TIMEOUT:
            await message.delete()
            await member.timeout(
                timedelta(minutes=rules.timeout_minutes), reason=reason
            )
            return True
        return False
    except discord.Forbidden:
        logger.error(
            f"Honeypot: cannot {decision.action} {member.id} - missing permission or "
            f"role hierarchy ({reason})"
        )
    except discord.HTTPException as exc:
        logger.error(f"Honeypot: {decision.action} failed for {member.id}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            f"Honeypot: unexpected error during {decision.action} for {member.id}: {exc}",
            exc_info=True,
        )
    return False


async def handle_honeypot_message(
    message: discord.Message,
    rules: Optional[Rules] = None,
) -> Optional[Decision]:
    """
    Score and (unless dry-running) act on a message posted in a honeypot channel.

    Returns the decision, or None when the message was ignored because the
    member is immune. Never raises: a honeypot failure must not break normal
    message handling.
    """
    rules = rules or load_rules()

    if not rules.enabled:
        return None
    if rules.require_trusted_role_ids and not rules.trusted_role_ids:
        logger.error(
            "Honeypot: refusing to act - HONEYPOT_TRUSTED_ROLE_IDS is empty. "
            "Set the trusted role IDs or set HONEYPOT_REQUIRE_TRUSTED_ROLES=false."
        )
        return None

    try:
        facts = await collect_facts(message, rules)
        decision = classify(facts, rules)

        if decision.immune:
            logger.info(
                f"Honeypot: ignoring {facts.user_id} in #{getattr(message.channel, 'name', '?')} - "
                f"{decision.immune_reason}"
            )
            return None

        enforced = False
        if decision.actionable and not rules.dry_run:
            enforced = await _enforce(message, decision, rules)
        elif decision.actionable:
            logger.warning(
                f"Honeypot DRY RUN: would {decision.action} {facts.user_id} "
                f"(#{getattr(message.channel, 'name', '?')}) - {decision.explain()}"
            )

        if decision.action != Action.NONE:
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

            if rules.announce_in_channel and enforced:
                try:
                    await message.channel.send(
                        embed=discord.Embed(
                            description=(
                                "🍯 That channel is a trap for spam accounts. "
                                "Nothing posted here is read."
                            ),
                            color=discord.Color.dark_grey(),
                        ),
                        delete_after=15,
                    )
                except Exception:  # pragma: no cover - best effort
                    pass

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
    return await unregister_honeypot_channel_by_id(str(channel.id), channel.guild)


async def unregister_honeypot_channel_by_id(
    channel_id: str,
    guild: Optional[discord.Guild] = None,
) -> bool:
    """
    Remove honeypot status without a channel object.

    Needed by ``/honeypot-clear``, which only has IDs from the database and must
    still work for a channel that has since been deleted. The topic warning is
    cleared when the channel can still be resolved.
    """
    guild_id = str(getattr(guild, "id", "") or "")
    removed = database.remove_honeypot_channel(str(channel_id), guild_id)
    if not removed:
        return False

    logger.info(f"Honeypot: channel {channel_id} removed")
    invalidate_channel_cache()

    channel = None
    if guild is not None:
        try:
            channel = guild.get_channel(int(channel_id))
        except (TypeError, ValueError):
            channel = None

    # Clear the topic warning so a former trap does not keep a stale sign on it.
    if channel is not None:
        try:
            await channel.edit(topic=None, reason="Honeypot channel removed")  # type: ignore[arg-type]
        except discord.Forbidden:
            logger.warning(f"Honeypot: cannot clear topic on {channel_id} - missing permission")
        except Exception as exc:
            logger.warning(f"Honeypot: could not clear topic on {channel_id}: {exc}")

    return True


def list_honeypot_channels(guild_id: str) -> List[Dict]:
    """Registered honeypot channels for a guild."""
    return database.get_honeypot_channels_for_guild(str(guild_id))
