"""
Tests for the honeypot trap (honeypot_handler.py + its database layer).

The point of the design is that a member can only be punished if they fail every
immunity check AND show behaviour with no innocent reading, so most of these
tests are about who is *not* actioned: trusted-role holders, anyone with points
history, bots, and accounts showing only circumstantial signals.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
import honeypot_handler as hp
from honeypot_handler import (
    Action,
    HitFacts,
    Rules,
    classify,
    contains_invite,
    contains_link,
    established_reason,
    immunity_reason,
    matches_scam_phrasing,
    normalize_content,
    find_triggers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_database():
    """Isolated database file so honeypot tables never touch production."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_file = os.path.join(temp_dir, "test_discord_messages.db")
        with patch.object(database, 'DB_FILE', temp_db_file), \
             patch.object(database, 'DB_DIRECTORY', temp_dir):
            database.init_database()
            yield temp_db_file


@pytest.fixture
def trusted_rules():
    """Rules with the trusted-role allow-list satisfied so the trap will act."""
    return Rules(
        enabled=True,
        dry_run=False,
        trusted_role_ids=frozenset({"999"}),
        log_channel_id=None,
    )


def make_young_facts(**overrides) -> HitFacts:
    """Facts for a newly created account that has just joined."""
    now = datetime.now(timezone.utc)
    base = dict(
        account_created_at=now - timedelta(days=5),
        joined_at=now - timedelta(days=2),
    )
    base.update(overrides)
    return make_facts(**base)


def make_facts(**overrides) -> HitFacts:
    """Build HitFacts with sane defaults for an unknown new account."""
    defaults: dict = dict(
        user_id="100000000000000001",
        author_name="suspicious",
        account_created_at=datetime.now(timezone.utc) - timedelta(days=400),
        joined_at=datetime.now(timezone.utc) - timedelta(days=200),
        lifetime_points=0,
        trusted_role_names=(),
        is_bot=False,
        is_webhook=False,
        prior_message_count=50,
        channels_in_blast_window=(),
        channels_with_duplicate_content=(),
        content="hello",
        mention_count=0,
    )
    defaults.update(overrides)
    return HitFacts(**defaults)


# ---------------------------------------------------------------------------
# Immunity: the whitelist gate
# ---------------------------------------------------------------------------

class TestImmunity:
    """An established account must never be actioned, however it behaves."""

    def test_trusted_role_is_immune(self):
        facts = make_facts(trusted_role_names=("Moderator",))
        assert "Moderator" in immunity_reason(facts, Rules())

    def test_points_history_is_immune(self):
        facts = make_facts(lifetime_points=1)
        assert "points history" in immunity_reason(facts, Rules())

    def test_bot_account_is_immune(self):
        assert immunity_reason(make_facts(is_bot=True), Rules()) == "bot account"

    def test_webhook_is_immune(self):
        assert immunity_reason(make_facts(is_webhook=True), Rules()) == "webhook"

    def test_new_account_fails_immunity(self):
        """A young account with no role and no points is the target population."""
        assert immunity_reason(make_young_facts(), Rules()) is None

    def test_age_alone_is_not_immunity(self):
        """The guild is mostly quiet lurkers with no role and no points, so age
        cannot grant full immunity or the trap would never act on anyone."""
        assert immunity_reason(make_facts(), Rules()) is None


class TestBanShield:
    """An established account can be timed out, never banned."""

    def test_established_account_is_shielded(self):
        assert established_reason(make_facts()) is not None

    def test_young_account_is_not_shielded(self):
        assert established_reason(make_young_facts()) is None

    def test_old_account_that_just_joined_is_not_shielded(self):
        """A 10-year-old Discord account that joined yesterday is still new here."""
        now = datetime.now(timezone.utc)
        facts = make_facts(
            account_created_at=now - timedelta(days=3650),
            joined_at=now - timedelta(days=1),
        )
        assert established_reason(facts) is None

    def test_needs_both_age_and_tenure(self):
        """45 days old but 5 days in the server is still a new arrival here."""
        now = datetime.now(timezone.utc)
        facts = make_facts(
            account_created_at=now - timedelta(days=45),
            joined_at=now - timedelta(days=5),
        )
        assert established_reason(facts) is None

    def test_shielded_account_is_still_timed_out(self, trusted_rules):
        """A blast is deleted and timed out even for an established account."""
        facts = make_facts(channels_in_blast_window=("1", "2", "3"))
        decision = classify(facts, trusted_rules)
        assert decision.action == Action.TIMEOUT
        assert decision.actionable is True

    def test_shield_downgrades_a_ban_to_a_timeout(self, trusted_rules):
        """Two triggers would ban a new account; an established one is timed out."""
        facts = make_facts(
            channels_in_blast_window=("1", "2", "3"),
            channels_with_duplicate_content=("1", "2", "3"),
        )
        decision = classify(facts, trusted_rules)
        assert len(decision.triggers) >= 2
        assert decision.action == Action.TIMEOUT
        assert decision.ban_withheld is not None

    def test_shield_holds_on_a_repeat(self, trusted_rules):
        """Even caught before, an established account is not banned."""
        facts = make_facts(
            channels_in_blast_window=("1", "2", "3"),
            prior_hits=3,
        )
        decision = classify(facts, trusted_rules)
        assert decision.action == Action.TIMEOUT
        assert decision.ban_withheld is not None

    def test_new_account_with_the_same_profile_is_banned(self, trusted_rules):
        """The shield must not leak onto the accounts the trap is actually for."""
        facts = make_young_facts(
            channels_in_blast_window=("1", "2", "3"),
            channels_with_duplicate_content=("1", "2", "3"),
        )
        decision = classify(facts, trusted_rules)
        assert decision.action == Action.BAN
        assert decision.ban_withheld is None

    def test_immunity_beats_an_egregious_score(self):
        """Even a channel blast is ignored for a trusted member."""
        facts = make_young_facts(
            trusted_role_names=("active",),
            content="https://discord.gg/spam invite",
            channels_in_blast_window=("1", "2", "3", "4", "5"),
            account_created_at=datetime.now(timezone.utc),
        )
        decision = classify(facts, Rules())
        assert decision.immune is True
        assert decision.action == Action.NONE
        assert decision.actionable is False

    def test_points_holder_posting_an_invite_is_immune(self):
        """The 132 known members exit here; they can never be timed out."""
        facts = make_young_facts(
            lifetime_points=7,
            content="come join https://discord.gg/xyz",
            channels_in_blast_window=("1", "2", "3"),
        )
        decision = classify(facts, Rules())
        assert decision.immune is True
        assert decision.action == Action.NONE


# ---------------------------------------------------------------------------
# Triggers and classification
# ---------------------------------------------------------------------------

class TestTriggers:
    """A trigger acts on its own; context never does."""

    def test_clean_message_is_never_punished(self, trusted_rules):
        """A first post in a real channel, even from a new account, is ignored."""
        decision = classify(
            make_young_facts(content="good morning everyone"), trusted_rules
        )
        assert decision.triggers == ()
        assert decision.actionable is False
        assert decision.action == Action.NONE

    def test_link_is_not_a_trigger(self, trusted_rules):
        """A URL in a real channel is not enough — that was a decoy-channel rule."""
        facts = make_facts(content="https://example.com/promo")
        triggers, _ = find_triggers(facts, trusted_rules)
        assert triggers == []

    def test_invite_is_not_a_trigger(self, trusted_rules):
        facts = make_facts(content="join https://discord.gg/spam now")
        triggers, _ = find_triggers(facts, trusted_rules)
        assert triggers == []

    def test_fresh_account_is_not_a_trigger(self, trusted_rules):
        facts = make_facts(
            account_created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            prior_message_count=100,
        )
        triggers, _ = find_triggers(facts, trusted_rules)
        assert not any(s.startswith("account_age:") for s in triggers)

    def test_channel_blast_is_a_trigger(self, trusted_rules):
        facts = make_facts(channels_in_blast_window=("1", "2", "3"))
        triggers, _ = find_triggers(facts, trusted_rules)
        assert any(s.startswith("blast:") for s in triggers)

    def test_duplicate_content_across_channels_is_a_trigger(self, trusted_rules):
        facts = make_facts(channels_with_duplicate_content=("1", "2", "3"))
        triggers, _ = find_triggers(facts, trusted_rules)
        assert any(s.startswith("duplicate_content:") for s in triggers)

    def test_duplicate_in_two_channels_is_not_a_trigger(self, trusted_rules):
        """Pasting the same question in two rooms is a messy human, not a raid."""
        facts = make_facts(channels_with_duplicate_content=("1", "2"))
        triggers, _ = find_triggers(facts, trusted_rules)
        assert not any(s.startswith("duplicate_content:") for s in triggers)

    def test_blast_below_threshold_is_not_a_trigger(self, trusted_rules):
        facts = make_facts(channels_in_blast_window=("1", "2"))  # needs 3
        triggers, _ = find_triggers(facts, trusted_rules)
        assert not any(s.startswith("blast:") for s in triggers)

    def test_unknown_history_is_not_treated_as_zero(self, trusted_rules):
        """Absent data must not count as evidence of a clean or dirty history."""
        facts = make_facts(prior_message_count=None)
        _, context = find_triggers(facts, trusted_rules)
        assert "no_prior_messages" not in context
        assert "prior_history_unknown" in context

    def test_scam_phrasing_is_recorded_as_context(self, trusted_rules):
        facts = make_facts(content="come check us out, free giveaway inside")
        _, context = find_triggers(facts, trusted_rules)
        assert any("scam_phrasing" in s for s in context)

    def test_scam_phrasing_alone_cannot_act(self, trusted_rules):
        """A single context signal is recorded but never punished."""
        decision = classify(make_young_facts(content="come check us out"), trusted_rules)
        assert decision.action == Action.NONE
        assert decision.actionable is False

    def test_context_in_bulk_never_bans(self, trusted_rules):
        """Weak signals in bulk must not permaban anyone."""
        facts = make_facts(
            account_created_at=datetime.now(timezone.utc) - timedelta(days=2),
            prior_message_count=0,
            joined_at=datetime.now(timezone.utc) - timedelta(hours=1),
            mention_count=10,
            content="hey everyone " + " ".join(f"<@{i}>" for i in range(10)),
        )
        decision = classify(facts, trusted_rules)
        assert decision.triggers == ()
        assert decision.action == Action.NONE


class TestResponse:
    """One trigger times out; two, or a repeat, bans."""

    def test_one_trigger_times_out(self, trusted_rules):
        decision = classify(
            make_young_facts(channels_in_blast_window=("1", "2", "3")), trusted_rules
        )
        assert decision.action == Action.TIMEOUT
        assert decision.actionable is True

    def test_first_strike_with_context_still_only_times_out(self, trusted_rules):
        """One trigger plus as much context as you like is still a first strike."""
        facts = make_facts(
            channels_in_blast_window=("1", "2", "3"),
            account_created_at=datetime.now(timezone.utc) - timedelta(days=3),
            prior_message_count=0,
        )
        decision = classify(facts, trusted_rules)
        assert len(decision.triggers) == 1
        assert decision.action == Action.TIMEOUT

    def test_two_triggers_ban_on_a_first_strike(self, trusted_rules):
        """Blast + duplicate is unambiguous, so no prior strike is required."""
        facts = make_young_facts(
            channels_in_blast_window=("1", "2", "3"),
            channels_with_duplicate_content=("1", "2", "3"),
        )
        decision = classify(facts, trusted_rules)
        assert len(decision.triggers) >= 2
        assert decision.action == Action.BAN

    def test_repeat_offender_bans_on_the_same_evidence(self, trusted_rules):
        """The identical blast bans once the account has a recorded hit."""
        facts = make_facts(
            channels_in_blast_window=("1", "2", "3"),
            account_created_at=datetime.now(timezone.utc) - timedelta(days=3),
            prior_message_count=0,
            prior_hits=1,
        )
        assert classify(facts, trusted_rules).action == Action.BAN

    def test_blast_alone_is_a_timeout_not_a_ban(self, trusted_rules):
        """Three channels in 60s with different text is a first strike."""
        facts = make_facts(
            account_created_at=datetime.now(timezone.utc) - timedelta(days=5),
            prior_message_count=0,
            channels_in_blast_window=("links", "ai", "llm"),
        )
        decision = classify(facts, trusted_rules)
        assert decision.action == Action.TIMEOUT

    def test_the_kitty_incident_bans(self, trusted_rules):
        """2026-09-30: 5-day-old account pasted the same pitch in 5 channels in 2.5 min."""
        facts = make_facts(
            account_created_at=datetime.now(timezone.utc) - timedelta(days=5),
            joined_at=datetime.now(timezone.utc) - timedelta(minutes=54),
            prior_message_count=0,
            channels_in_blast_window=("collabs", "introductions", "general"),
            channels_with_duplicate_content=(
                "collabs", "introductions", "general", "ai-models", "paid-work",
            ),
        )
        decision = classify(facts, trusted_rules)
        assert decision.action == Action.BAN

    def test_scam_phrasing_is_recorded(self, trusted_rules):
        facts = make_facts(content="come check us out, free giveaway inside")
        _, context = find_triggers(facts, trusted_rules)
        assert any("scam_phrasing" in s for s in context)


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

class TestContentHelpers:

    def test_normalize_collapses_whitespace_and_case(self):
        assert normalize_content("  Hello   WORLD \n") == "hello world"

    def test_normalize_strips_zero_width_characters(self):
        """Spammers pad text with invisible characters to dodge duplicate checks."""
        assert normalize_content("fr\u200bee \u00a0nitro") == "free nitro"

    def test_invite_detection(self):
        assert contains_invite("join https://discord.gg/abc123")
        assert contains_invite("join https://discord.com/invite/abc123")
        assert not contains_invite("join https://example.com")

    def test_link_detection(self):
        assert contains_link("see https://example.com/x")
        assert contains_link("see www.example.com")
        assert not contains_link("no links here")

    def test_scam_phrasing_detection(self):
        assert matches_scam_phrasing("COME CHECK US OUT")
        assert not matches_scam_phrasing("how do I install pytorch")


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------

class TestDatabaseLayer:

    def test_register_and_lookup_channel(self, temp_database):
        assert database.add_honeypot_channel(
            channel_id="111", channel_name="trap", guild_id="999",
            guild_name="Test", created_by_id="1", created_by_name="admin",
        ) is True
        assert database.is_honeypot_channel("111", "999") is True
        assert database.is_honeypot_channel("222", "999") is False

    def test_registering_twice_is_idempotent(self, temp_database):
        for _ in range(2):
            database.add_honeypot_channel(
                channel_id="111", channel_name="trap", guild_id="999",
                guild_name="Test", created_by_id="1", created_by_name="admin",
            )
        assert len(database.get_honeypot_channels_for_guild("999")) == 1

    def test_remove_channel(self, temp_database):
        database.add_honeypot_channel(
            channel_id="111", channel_name="trap", guild_id="999",
            guild_name="Test", created_by_id="1", created_by_name="admin",
        )
        assert database.remove_honeypot_channel("111", "999") is True
        assert database.is_honeypot_channel("111", "999") is False
        # Removing again reports False so the command can say "not registered".
        assert database.remove_honeypot_channel("111", "999") is False

    def test_channels_are_scoped_per_guild(self, temp_database):
        database.add_honeypot_channel(
            channel_id="111", channel_name="trap", guild_id="999",
            guild_name="Test", created_by_id="1", created_by_name="admin",
        )
        assert database.is_honeypot_channel("111", "888") is False

    def test_join_then_first_message_keeps_join_date(self, temp_database):
        joined = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        assert database.record_member_join("42", "999", "newbie", joined_at=joined) is True
        database.touch_member_activity("42", "999", "newbie")

        activity = database.get_member_activity("42", "999")
        assert activity["message_count"] == 1
        assert activity["joined_at"].startswith("2026-01-01T12:00")
        assert activity["first_message_at"] is not None

    def test_activity_counter_increments(self, temp_database):
        for _ in range(3):
            database.touch_member_activity("42", "999", "chatty")
        assert database.get_member_activity("42", "999")["message_count"] == 3

    def test_activity_unknown_member_returns_none(self, temp_database):
        assert database.get_member_activity("404", "999") is None

    def test_join_does_not_reset_message_count(self, temp_database):
        database.touch_member_activity("42", "999", "chatty")
        database.record_member_join("42", "999", "chatty")
        assert database.get_member_activity("42", "999")["message_count"] == 1

    def test_recent_channel_ids_within_window(self, temp_database):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        database.store_message(
            message_id="1", channel_id="111", channel_name="a", author_id="42",
            author_name="spammer", content="hi", created_at=now, is_bot=False,
            guild_id="999",
        )
        database.store_message(
            message_id="2", channel_id="222", channel_name="b", author_id="42",
            author_name="spammer", content="hi", created_at=now, is_bot=False,
            guild_id="999",
        )
        channels = database.get_recent_channel_ids("42", "999", seconds=60)
        assert set(channels) == {"111", "222"}

    def test_old_messages_fall_outside_blast_window(self, temp_database):
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)
        database.store_message(
            message_id="1", channel_id="111", channel_name="a", author_id="42",
            author_name="spammer", content="hi", created_at=old, is_bot=False,
            guild_id="999",
        )
        assert database.get_recent_channel_ids("42", "999", seconds=60) == []

    def test_duplicate_content_across_channels(self, temp_database):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i, channel in enumerate(("111", "222")):
            database.store_message(
                message_id=str(i), channel_id=channel, channel_name="c",
                author_id="42", author_name="spammer",
                content="Join  Here\tNow", created_at=now, is_bot=False,
                guild_id="999",
            )
        # Case/whitespace differences must not hide the duplicate.
        channels = database.get_recent_duplicate_channels(
            "42", "999", normalize_content("join here now"), minutes=5
        )
        assert set(channels) == {"111", "222"}

    def test_record_and_list_hits(self, temp_database):
        database.record_honeypot_hit(
            user_id="42", user_name="spammer", channel_id="111",
            channel_name="trap", guild_id="999", score=6, action=Action.BAN,
            enforced=True, reasons="blast", content="spam",
        )
        hits = database.get_recent_honeypot_hits("999", limit=10)
        assert len(hits) == 1
        assert hits[0]["user_id"] == "42"
        assert hits[0]["action"] == Action.BAN
        assert hits[0]["enforced"] == 1

    def test_store_message_updates_activity_record(self, temp_database):
        """The activity counter must ride along with normal message storage."""
        database.store_message(
            message_id="1", channel_id="111", channel_name="a", author_id="42",
            author_name="member", content="hello", created_at=datetime.now(timezone.utc),
            is_bot=False, guild_id="999",
        )
        assert database.get_member_activity("42", "999")["message_count"] == 1

    def test_bot_messages_do_not_create_activity(self, temp_database):
        database.store_message(
            message_id="1", channel_id="111", channel_name="a", author_id="9",
            author_name="bot", content="beep", created_at=datetime.now(timezone.utc),
            is_bot=True, guild_id="999",
        )
        assert database.get_member_activity("9", "999") is None


# ---------------------------------------------------------------------------
# Handler: interlocks and dry run
# ---------------------------------------------------------------------------

def make_message(content="hello", *, is_bot=False, member_spec=True, joined_days_ago=200,
                 account_days_old=400, guild_id=999, channel_id=111):
    """Build a message double that satisfies the handler's isinstance checks."""
    member = MagicMock(spec=__import__("discord").Member)
    member.id = 42
    member.bot = is_bot
    member.roles = [MagicMock(id=9999, name="fren")]
    member.created_at = datetime.now(timezone.utc) - timedelta(days=account_days_old)
    member.joined_at = datetime.now(timezone.utc) - timedelta(days=joined_days_ago)
    member.__str__ = lambda self: "suspicious#0001"

    message = MagicMock()
    message.id = 555
    message.content = content
    message.author = member
    message.mentions = []
    message.role_mentions = []
    # Explicit: an unset MagicMock attribute is truthy, which would make the
    # handler classify this double as a webhook.
    message.webhook_id = None
    message.guild.id = guild_id
    message.channel.id = channel_id
    message.channel.name = "trap"
    message.channel.mention = "<#111>"
    message.guild.name = "Test Guild"
    return message


class TestHandlerInterlocks:
    """Misconfiguration must fail closed: do nothing, loudly."""

    @pytest.mark.asyncio
    async def test_disabled_honeypot_is_a_no_op(self):
        with patch.object(hp, "load_rules", return_value=Rules(enabled=False, dry_run=False)):
            assert await hp.handle_honeypot_message(make_message()) is None

    @pytest.mark.asyncio
    async def test_no_trusted_roles_refuses_to_act(self):
        """Without an allow-list the trap would flag every member; refuse instead."""
        rules = Rules(
            enabled=True, dry_run=False,
            trusted_role_ids=frozenset(),
        )
        with patch.object(hp, "load_rules", return_value=rules), \
             patch.object(hp, "collect_facts", new=AsyncMock()) as collect:
            result = await hp.handle_honeypot_message(make_message())
            assert result is None
            collect.assert_not_awaited()  # never even scored

    @pytest.mark.asyncio
    async def test_dry_run_never_punishes(self, temp_database):
        """A dry-run hit is recorded but must not touch the member."""
        rules = Rules(
            enabled=True, dry_run=True,
            trusted_role_ids=frozenset({"999"}),
        )
        facts = make_young_facts(
            user_id="42", channels_in_blast_window=("1", "2", "3"),
        )
        with patch.object(hp, "load_rules", return_value=rules), \
             patch.object(hp, "collect_facts", new=AsyncMock(return_value=facts)), \
             patch.object(hp, "_enforce", new=AsyncMock()) as enforce:
            decision = await hp.handle_honeypot_message(make_message())
            assert decision is not None
            assert decision.actionable is True
            enforce.assert_not_awaited()

        hits = database.get_recent_honeypot_hits("999", limit=5)
        assert len(hits) == 1
        assert hits[0]["enforced"] == 0

    @pytest.mark.asyncio
    async def test_enforced_hit_calls_enforce(self, temp_database):
        """The same blast is acted on once dry run is off."""
        rules = Rules(
            enabled=True, dry_run=False,
            trusted_role_ids=frozenset({"999"}),
        )
        facts = make_young_facts(
            user_id="42", channels_in_blast_window=("1", "2", "3"),
        )
        with patch.object(hp, "load_rules", return_value=rules), \
             patch.object(hp, "collect_facts", new=AsyncMock(return_value=facts)), \
             patch.object(hp, "_enforce", new=AsyncMock(return_value=True)) as enforce:
            decision = await hp.handle_honeypot_message(make_message())
            assert decision is not None
            enforce.assert_awaited_once()

        hits = database.get_recent_honeypot_hits("999", limit=5)
        assert len(hits) == 1
        assert hits[0]["enforced"] == 1

    @pytest.mark.asyncio
    async def test_established_member_is_timed_out_but_never_banned(self, temp_database):
        """An established account blasting is timed out, not banned --
        and the hit is still recorded so a moderator can see it."""
        rules = Rules(
            enabled=True, dry_run=False,
            trusted_role_ids=frozenset({"999"}),
        )
        facts = make_facts(
            user_id="42", channels_in_blast_window=("1", "2", "3"),
        )
        with patch.object(hp, "load_rules", return_value=rules), \
             patch.object(hp, "collect_facts", new=AsyncMock(return_value=facts)), \
             patch.object(hp, "_enforce", new=AsyncMock(return_value=True)) as enforce:
            decision = await hp.handle_honeypot_message(make_message())
            assert decision is not None
            assert decision.action == Action.TIMEOUT
            enforce.assert_awaited_once()

        hits = database.get_recent_honeypot_hits("999", limit=5)
        assert len(hits) == 1
        assert hits[0]["action"] == Action.TIMEOUT

    @pytest.mark.asyncio
    async def test_ordinary_chat_is_not_recorded(self, temp_database):
        """A first message with no blast/duplicate must not write a hit row."""
        rules = Rules(
            enabled=True, dry_run=False,
            trusted_role_ids=frozenset({"999"}),
        )
        with patch.object(hp, "load_rules", return_value=rules), \
             patch.object(hp, "_enforce", new=AsyncMock()) as enforce:
            decision = await hp.handle_honeypot_message(make_message())
            assert decision is None
            enforce.assert_not_awaited()
        assert database.get_recent_honeypot_hits("999", limit=5) == []


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
