"""
Tests for automatic role-based point gifts.

Members holding `legend` (daily), `MVP` and `Server Booster` (weekly) are
gifted points by a once-a-day pass. The gifts are larger than the 20 point
per-award clamp on the LLM-scored daily awards, they must raise lifetime_points
as well as the spendable balance, and they must never pay twice for the same
period no matter how often the pass runs.
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import database
import summarization_tasks


@pytest.fixture
def setup_database():
    """Initialize a database in an isolated temp directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_file = os.path.join(temp_dir, "test_discord_messages.db")
        with patch.object(database, 'DB_FILE', temp_db_file), \
             patch.object(database, 'DB_DIRECTORY', temp_dir):
            database.init_database()
            yield temp_db_file


GUILD = "guild_1"
USER = "user_1"
TODAY = "2026-09-08"
THIS_WEEK = "2026-W37"


# ---------------------------------------------------------------- database --

def test_gift_above_the_award_clamp_is_paid_in_full(setup_database):
    """award_points_to_user() clamps to 20; the 50 point booster gift must not."""
    assert database.grant_role_point_gift(
        USER, "ada", GUILD, 'booster_weekly', THIS_WEEK, 50
    ) is True

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 50
    assert summary['lifetime_points'] == 50


def test_gift_counts_as_earned_and_survives_spending(setup_database):
    database.grant_role_point_gift(USER, "ada", GUILD, 'mvp_weekly', THIS_WEEK, 25)
    assert database.deduct_user_points(USER, GUILD, 25) is True

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 0
    assert summary['lifetime_points'] == 25
    assert summary['spent'] == 25


def test_same_period_never_gifts_twice(setup_database):
    assert database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, 10) is True
    assert database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, 10) is False

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 10
    assert summary['lifetime_points'] == 10
    assert len(database.get_role_point_gifts(GUILD, 'legend_daily', TODAY)) == 1


def test_a_new_period_gifts_again(setup_database):
    database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', "2026-09-08", 10)
    database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', "2026-09-09", 10)

    assert database.get_user_points(USER, GUILD) == 20


def test_gift_types_stack_in_the_same_period(setup_database):
    """A member holding every gift role collects every gift."""
    database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, 10)
    database.grant_role_point_gift(USER, "ada", GUILD, 'mvp_weekly', THIS_WEEK, 25)
    database.grant_role_point_gift(USER, "ada", GUILD, 'booster_weekly', THIS_WEEK, 50)

    assert database.get_user_points(USER, GUILD) == 85


def test_gifts_are_per_guild(setup_database):
    database.grant_role_point_gift(USER, "ada", "guild_a", 'legend_daily', TODAY, 10)
    database.grant_role_point_gift(USER, "ada", "guild_b", 'legend_daily', TODAY, 10)

    assert database.get_user_points(USER, "guild_a") == 10
    assert database.get_user_points(USER, "guild_b") == 10


def test_gifts_never_touch_the_daily_award_table(setup_database):
    """A row in daily_point_awards would cancel that night's real point awards."""
    database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, 10)

    awards = database.get_daily_point_awards(GUILD, datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert awards == []


def test_non_positive_and_oversized_gifts_are_refused(setup_database):
    assert database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, 0) is False
    assert database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, -5) is False
    assert database.grant_role_point_gift(
        USER, "ada", GUILD, 'legend_daily', TODAY, database.MAX_ROLE_GIFT_POINTS + 1
    ) is False
    assert database.grant_role_point_gift("", "ada", GUILD, 'legend_daily', TODAY, 10) is False
    assert database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, 10.7) is False
    assert database.grant_role_point_gift(USER, "ada", GUILD, 'legend_daily', TODAY, True) is False

    assert database.get_user_points(USER, GUILD) == 0
    assert database.get_role_point_gifts(GUILD) == []


def test_a_non_unique_constraint_failure_is_not_mistaken_for_a_repeat(setup_database):
    """A NOT NULL failure is a bug, not the routine "already gifted" no-op."""
    assert database.grant_role_point_gift(USER, None, GUILD, 'legend_daily', TODAY, 10) is False
    assert database.get_role_point_gifts(GUILD) == []
    # ... and the member was not credited by a half-applied transaction.
    assert database.get_user_points(USER, GUILD) == 0


def test_regular_awards_still_clamp_to_twenty(setup_database):
    """The gift path must not have loosened the ordinary award path."""
    database.award_points_to_user(USER, "ada", GUILD, 50)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 20
    assert summary['lifetime_points'] == 20


def test_refunds_still_skip_lifetime_points(setup_database):
    database.award_points_to_user(USER, "ada", GUILD, 20)
    database.deduct_user_points(USER, GUILD, 20)
    database.award_points_to_user(USER, "ada", GUILD, 5, counts_as_earned=False)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 5
    assert summary['lifetime_points'] == 20   # the refund did not re-earn anything


def test_migration_adds_the_table_to_an_older_database():
    """A database that predates the feature gains role_point_gifts on migrate."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_file = os.path.join(temp_dir, "legacy.db")

        # A "legacy" DB with the older tables but no role_point_gifts.
        with sqlite3.connect(temp_db_file) as conn:
            conn.execute(database.CREATE_MESSAGES_TABLE)
            conn.execute(database.CREATE_USER_POINTS_TABLE)
            conn.execute(database.CREATE_USER_ROLE_COLORS_TABLE)
            conn.commit()

        with patch.object(database, 'DB_FILE', temp_db_file), \
             patch.object(database, 'DB_DIRECTORY', temp_dir):
            database.migrate_database()
            assert database.grant_role_point_gift(
                USER, "ada", GUILD, 'legend_daily', TODAY, 10
            ) is True
            assert database.get_user_points(USER, GUILD) == 10


# ------------------------------------------------------------- period keys --

def test_daily_key_is_the_utc_date():
    now = datetime(2026, 9, 8, 23, 59, tzinfo=timezone.utc)
    assert summarization_tasks._daily_period_key(now) == "2026-09-08"


def test_weekly_key_is_stable_within_a_week_and_changes_across_weeks():
    monday = datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)
    sunday = datetime(2026, 9, 13, 23, 59, tzinfo=timezone.utc)
    next_monday = datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)

    assert summarization_tasks._weekly_period_key(monday) == "2026-W37"
    assert summarization_tasks._weekly_period_key(sunday) == "2026-W37"
    assert summarization_tasks._weekly_period_key(next_monday) == "2026-W38"


def test_weekly_key_uses_the_iso_week_year_across_new_year():
    """2026-12-31 is a Thursday in ISO week 2026-W53, 2027-01-01 is the same week."""
    assert summarization_tasks._weekly_period_key(
        datetime(2026, 12, 31, tzinfo=timezone.utc)
    ) == "2026-W53"
    assert summarization_tasks._weekly_period_key(
        datetime(2027, 1, 1, tzinfo=timezone.utc)
    ) == "2026-W53"
    assert summarization_tasks._weekly_period_key(
        datetime(2027, 1, 4, tzinfo=timezone.utc)
    ) == "2027-W01"


def test_period_key_matches_the_cadence():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    assert summarization_tasks._period_key_for('daily', now) == "2026-09-08"
    assert summarization_tasks._period_key_for('weekly', now) == "2026-W37"


# ---------------------------------------------------------- member filtering --

def _rest_member(member_id, name, role_ids, is_bot=False):
    """The raw payload shape returned by the list-guild-members REST endpoint."""
    return {
        'user': {'id': member_id, 'username': name, 'bot': is_bot},
        'roles': list(role_ids),
    }


def _cached_member(member_id, name, role_ids, is_bot=False):
    """A discord.Member-ish object, as found in the (partial) gateway cache."""
    member = MagicMock()
    member.id = member_id
    member.name = name
    member.bot = is_bot
    member.roles = [SimpleNamespace(id=role_id, name=str(role_id)) for role_id in role_ids]
    return member


def test_members_with_role_filters_rest_payloads():
    members = [
        summarization_tasks._normalize_member(_rest_member("1", "ada", ["100", "200"])),
        summarization_tasks._normalize_member(_rest_member("2", "bob", ["200"])),
        summarization_tasks._normalize_member(_rest_member("3", "cyd", [])),
    ]

    holders = summarization_tasks.members_with_role(members, 100)
    assert [m['id'] for m in holders] == ["1"]

    holders = summarization_tasks.members_with_role(members, "200")
    assert [m['id'] for m in holders] == ["1", "2"]


def test_members_with_role_filters_cached_member_objects():
    members = [
        summarization_tasks._normalize_member(_cached_member(1, "ada", [100])),
        summarization_tasks._normalize_member(_cached_member(2, "bob", [999])),
    ]

    holders = summarization_tasks.members_with_role(members, 100)
    assert [m['id'] for m in holders] == ["1"]
    assert holders[0]['name'] == "ada"


def test_bots_are_never_gifted():
    members = [
        summarization_tasks._normalize_member(_rest_member("1", "ada", ["100"])),
        summarization_tasks._normalize_member(_rest_member("2", "botty", ["100"], is_bot=True)),
    ]

    holders = summarization_tasks.members_with_role(members, "100")
    assert [m['id'] for m in holders] == ["1"]


def test_unreadable_member_records_are_dropped():
    assert summarization_tasks._normalize_member({'user': {}, 'roles': []}) is None
    assert summarization_tasks._normalize_member(None) is None


def test_find_role_matches_case_insensitively():
    guild = SimpleNamespace(
        id=1,
        roles=[SimpleNamespace(id=7, name="Server Booster"), SimpleNamespace(id=8, name="legend")],
    )

    assert summarization_tasks._find_role(guild, "server booster").id == 7
    assert summarization_tasks._find_role(guild, "LEGEND").id == 8
    assert summarization_tasks._find_role(guild, "MVP") is None


def test_a_duplicate_role_name_is_refused_rather_than_guessed():
    """A decoy 'legend' role must not be able to redirect the gift."""
    guild = SimpleNamespace(
        id=1,
        roles=[SimpleNamespace(id=7, name="legend"), SimpleNamespace(id=8, name="Legend")],
    )

    assert summarization_tasks._find_role(guild, "legend") is None


def test_the_booster_gift_falls_back_to_the_managed_boost_role():
    """Renaming 'Server Booster' must not silently stop paying boosters."""
    boost_role = SimpleNamespace(id=99, name="Nitro Friends")
    guild = SimpleNamespace(id=1, roles=[boost_role], premium_subscriber_role=boost_role)
    booster_spec = {'gift_type': 'booster_weekly', 'role_name': 'Server Booster'}
    legend_spec = {'gift_type': 'legend_daily', 'role_name': 'legend'}

    assert summarization_tasks._resolve_gift_role(guild, booster_spec) is boost_role
    # No such fallback exists for the other gifts.
    assert summarization_tasks._resolve_gift_role(guild, legend_spec) is None


# ---------------------------------------------------------------- schedule --

def test_the_gift_pass_is_scheduled_before_the_daily_colour_charge():
    """
    The colour charge strips roles from members who cannot pay, so the gifts
    have to land first - two tasks waking at the same instant have no order.
    """
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    run_at = summarization_tasks.next_gift_run_at(now, 0, 0)

    charge_at = datetime(2026, 9, 9, 0, 0, tzinfo=timezone.utc)
    assert run_at < charge_at
    assert charge_at - run_at == timedelta(minutes=summarization_tasks.ROLE_POINT_GIFT_LEAD_MINUTES)


def test_the_next_run_is_always_in_the_future():
    lead = timedelta(minutes=summarization_tasks.ROLE_POINT_GIFT_LEAD_MINUTES)

    # A moment before today's slot: run today.
    now = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)
    assert summarization_tasks.next_gift_run_at(now, 6, 30) == datetime(
        2026, 9, 8, 6, 30, tzinfo=timezone.utc
    ) - lead

    # A moment after it: run tomorrow, not in the past.
    now = datetime(2026, 9, 8, 6, 30, tzinfo=timezone.utc)
    assert summarization_tasks.next_gift_run_at(now, 6, 30) == datetime(
        2026, 9, 9, 6, 30, tzinfo=timezone.utc
    ) - lead

    # Exactly on the slot: never schedules zero seconds in the past.
    now = datetime(2026, 9, 8, 6, 20, tzinfo=timezone.utc)
    assert summarization_tasks.next_gift_run_at(now, 6, 30) > now


def test_successive_runs_are_a_day_apart():
    now = datetime(2026, 9, 8, 23, 55, tzinfo=timezone.utc)
    first = summarization_tasks.next_gift_run_at(now, 0, 0)
    second = summarization_tasks.next_gift_run_at(first, 0, 0)

    assert second - first == timedelta(days=1)
    # Consecutive runs fall on consecutive UTC dates, so each pays its own key.
    assert summarization_tasks._daily_period_key(first) != summarization_tasks._daily_period_key(second)


# --------------------------------------------------------------- gift pass --

class _FakeGuild:
    def __init__(self, guild_id, roles, members=()):
        self.id = guild_id
        self.roles = [SimpleNamespace(id=role_id, name=name) for role_id, name in roles]
        self.members = list(members)


def _fake_client(guilds, member_pages):
    """A stand-in bot exposing .guilds and .http.get_members pagination."""
    client = MagicMock()
    client.guilds = guilds
    pages = list(member_pages)

    async def get_members(guild_id, limit, after):
        return pages.pop(0) if pages else []

    client.http.get_members = AsyncMock(side_effect=get_members)
    return client


@pytest.fixture
def gift_config():
    """Config values for the gift pass, matching the shipped defaults."""
    return SimpleNamespace(
        ROLE_POINT_GIFTS_ENABLED=True,
        LEGEND_ROLE_NAME='legend',
        LEGEND_DAILY_GIFT_POINTS=10,
        MVP_ROLE_NAME='MVP',
        MVP_WEEKLY_GIFT_POINTS=25,
        BOOSTER_ROLE_NAME='Server Booster',
        BOOSTER_WEEKLY_GIFT_POINTS=50,
        summary_hour=0,
        summary_minute=0,
    )


@pytest.mark.asyncio
async def test_pass_gifts_every_matching_role_and_is_idempotent(setup_database, gift_config):
    guild = _FakeGuild(1, [(10, 'legend'), (20, 'MVP'), (30, 'Server Booster')])
    members = [
        _rest_member("100", "ada", ["10", "20", "30"]),   # holds everything
        _rest_member("200", "bob", ["10"]),               # legend only
        _rest_member("300", "cyd", ["30"]),               # booster only
        _rest_member("400", "botty", ["10"], is_bot=True),
    ]
    now = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', _fake_client([guild], [members])):
        await summarization_tasks.process_role_point_gifts(now=now)

    assert database.get_user_points("100", "1") == 85   # 10 + 25 + 50
    assert database.get_user_points("200", "1") == 10
    assert database.get_user_points("300", "1") == 50
    assert database.get_user_points("400", "1") == 0

    # A second pass in the same period must change nothing.
    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', _fake_client([guild], [members])):
        await summarization_tasks.process_role_point_gifts(now=now)

    assert database.get_user_points("100", "1") == 85
    assert database.get_user_points_summary("100", "1")['lifetime_points'] == 85


@pytest.mark.asyncio
async def test_next_day_pays_the_daily_gift_only(setup_database, gift_config):
    guild = _FakeGuild(1, [(10, 'legend'), (20, 'MVP'), (30, 'Server Booster')])
    members = [_rest_member("100", "ada", ["10", "20", "30"])]

    for day in (8, 9):
        now = datetime(2026, 9, day, tzinfo=timezone.utc)
        with patch.object(summarization_tasks, 'config', gift_config), \
             patch.object(summarization_tasks, 'discord_client', _fake_client([guild], [members])):
            await summarization_tasks.process_role_point_gifts(now=now)

    # 2026-09-08 and 2026-09-09 are both in ISO week 2026-W37.
    assert database.get_user_points("100", "1") == 85 + 10


@pytest.mark.asyncio
async def test_next_week_pays_the_weekly_gifts_again(setup_database, gift_config):
    guild = _FakeGuild(1, [(20, 'MVP'), (30, 'Server Booster')])
    members = [_rest_member("100", "ada", ["20", "30"])]

    for day in (8, 15):
        now = datetime(2026, 9, day, tzinfo=timezone.utc)
        with patch.object(summarization_tasks, 'config', gift_config), \
             patch.object(summarization_tasks, 'discord_client', _fake_client([guild], [members])):
            await summarization_tasks.process_role_point_gifts(now=now)

    assert database.get_user_points("100", "1") == 150   # (25 + 50) twice


@pytest.mark.asyncio
async def test_missing_roles_are_skipped_per_guild(setup_database, gift_config):
    """A guild without the MVP role still pays its legends."""
    guild = _FakeGuild(1, [(10, 'legend')])
    members = [_rest_member("100", "ada", ["10"])]

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', _fake_client([guild], [members])):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("100", "1") == 10
    assert database.get_role_point_gifts("1", 'mvp_weekly') == []


@pytest.mark.asyncio
async def test_every_guild_is_processed(setup_database, gift_config):
    guild_a = _FakeGuild(1, [(10, 'legend')])
    guild_b = _FakeGuild(2, [(11, 'legend')])
    client = _fake_client(
        [guild_a, guild_b],
        [[_rest_member("100", "ada", ["10"])], [_rest_member("200", "bob", ["11"])]],
    )

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("100", "1") == 10
    assert database.get_user_points("200", "2") == 10


@pytest.mark.asyncio
async def test_member_listing_paginates(setup_database, gift_config):
    """A guild larger than one page is fully enumerated."""
    guild = _FakeGuild(1, [(10, 'legend')])
    first_page = [_rest_member("100", "ada", ["10"]), _rest_member("200", "bob", ["10"])]
    second_page = [_rest_member("300", "cyd", ["10"])]
    client = _fake_client([guild], [first_page, second_page])

    with patch.object(summarization_tasks, '_MEMBER_PAGE_SIZE', 2), \
         patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("300", "1") == 10
    assert client.http.get_members.await_count == 2
    # The second page is requested after the last id of the first page.
    assert client.http.get_members.await_args_list[1].args[2] == "200"


@pytest.mark.asyncio
async def test_a_stuck_pagination_cursor_does_not_loop_forever(setup_database, gift_config):
    """A malformed page that repeats the same last id must end the walk."""
    guild = _FakeGuild(1, [(10, 'legend')])
    page = [_rest_member("100", "ada", ["10"]), _rest_member("200", "bob", ["10"])]
    client = MagicMock()
    client.guilds = [guild]
    client.http.get_members = AsyncMock(return_value=page)

    with patch.object(summarization_tasks, '_MEMBER_PAGE_SIZE', 2), \
         patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert client.http.get_members.await_count == 2
    assert database.get_user_points("200", "1") == 10


@pytest.mark.asyncio
async def test_forbidden_member_listing_skips_the_guild(setup_database, gift_config):
    """
    Without the members intent the REST list 403s.

    The gateway cache holds a near-arbitrary handful of members, so paying out
    of it would gift whoever happened to be cached and silently skip everyone
    else. Skip the guild instead and log loudly.
    """
    guild = _FakeGuild(
        1,
        [(10, 'legend')],
        members=[_cached_member(100, "ada", [10]), _cached_member(200, "bob", [10])],
    )
    client = _fake_client([guild], [])
    response = MagicMock(status=403, reason='Forbidden')
    client.http.get_members = AsyncMock(
        side_effect=discord.Forbidden(response, {'code': 50001, 'message': 'Missing Access'})
    )

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("100", "1") == 0
    assert database.get_user_points("200", "1") == 0


@pytest.mark.asyncio
async def test_a_mid_pagination_failure_keeps_the_members_already_listed(setup_database, gift_config):
    """A transient error on page two must not throw away page one."""
    guild = _FakeGuild(1, [(10, 'legend')])
    first_page = [_rest_member("100", "ada", ["10"]), _rest_member("200", "bob", ["10"])]
    response = MagicMock(status=500, reason='Internal Server Error')
    client = MagicMock()
    client.guilds = [guild]
    pages = [first_page]

    async def get_members(guild_id, limit, after):
        if pages:
            return pages.pop(0)
        raise discord.HTTPException(response, {'code': 0, 'message': 'Server error'})

    client.http.get_members = AsyncMock(side_effect=get_members)

    with patch.object(summarization_tasks, '_MEMBER_PAGE_SIZE', 2), \
         patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("100", "1") == 10
    assert database.get_user_points("200", "1") == 10


@pytest.mark.asyncio
async def test_a_broken_guild_does_not_block_the_others(setup_database, gift_config):
    good = _FakeGuild(2, [(11, 'legend')])
    broken = MagicMock()
    broken.id = 1
    type(broken).roles = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    client = _fake_client([broken, good], [[_rest_member("200", "bob", ["11"])]])

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("200", "2") == 10


@pytest.mark.asyncio
async def test_disabled_by_config(setup_database, gift_config):
    gift_config.ROLE_POINT_GIFTS_ENABLED = False
    guild = _FakeGuild(1, [(10, 'legend')])
    client = _fake_client([guild], [[_rest_member("100", "ada", ["10"])]])

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("100", "1") == 0
    client.http.get_members.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_zero_point_gift_is_configured_off(setup_database, gift_config):
    gift_config.LEGEND_DAILY_GIFT_POINTS = 0
    guild = _FakeGuild(1, [(10, 'legend'), (20, 'MVP')])
    members = [_rest_member("100", "ada", ["10", "20"])]
    client = _fake_client([guild], [members])

    with patch.object(summarization_tasks, 'config', gift_config), \
         patch.object(summarization_tasks, 'discord_client', client):
        await summarization_tasks.process_role_point_gifts(now=datetime(2026, 9, 8, tzinfo=timezone.utc))

    assert database.get_user_points("100", "1") == 25
    assert database.get_role_point_gifts("1", 'legend_daily') == []


def test_documented_defaults_are_what_an_unconfigured_bot_gifts():
    """A config module with none of the gift settings still gifts 10/25/50."""
    with patch.object(summarization_tasks, 'config', SimpleNamespace()):
        specs = {spec['gift_type']: spec for spec in summarization_tasks.get_role_gift_specs()}

    assert specs['legend_daily']['role_name'] == 'legend'
    assert specs['legend_daily']['points'] == 10
    assert specs['legend_daily']['cadence'] == 'daily'
    assert specs['mvp_weekly']['role_name'] == 'MVP'
    assert specs['mvp_weekly']['points'] == 25
    assert specs['mvp_weekly']['cadence'] == 'weekly'
    assert specs['booster_weekly']['role_name'] == 'Server Booster'
    assert specs['booster_weekly']['points'] == 50
    assert specs['booster_weekly']['cadence'] == 'weekly'


def test_configured_amounts_are_read_and_clamped():
    """A mis-set environment variable must not be able to mint points."""
    import config as real_config

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop('LEGEND_DAILY_GIFT_POINTS', None)
        assert real_config._gift_points('LEGEND_DAILY_GIFT_POINTS', 10) == 10

        os.environ['LEGEND_DAILY_GIFT_POINTS'] = '7'
        assert real_config._gift_points('LEGEND_DAILY_GIFT_POINTS', 10) == 7

        os.environ['LEGEND_DAILY_GIFT_POINTS'] = '999999'
        assert real_config._gift_points('LEGEND_DAILY_GIFT_POINTS', 10) == database.MAX_ROLE_GIFT_POINTS

        os.environ['LEGEND_DAILY_GIFT_POINTS'] = '-5'
        assert real_config._gift_points('LEGEND_DAILY_GIFT_POINTS', 10) == 0

        os.environ['LEGEND_DAILY_GIFT_POINTS'] = 'ten'
        assert real_config._gift_points('LEGEND_DAILY_GIFT_POINTS', 10) == 10


def test_the_config_ceiling_is_the_database_ceiling():
    """Two ceilings that drift apart would turn every gift into an error log."""
    import config as real_config

    assert real_config.MAX_ROLE_GIFT_POINTS == database.MAX_ROLE_GIFT_POINTS
