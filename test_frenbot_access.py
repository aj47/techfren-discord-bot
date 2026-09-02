"""
Tests for the /redeem-frenbot points-for-access feature.

Covers the grant/stacking arithmetic in the database layer and the expiry
sweep that actually removes the role when access lapses.
"""

import os
import sqlite3
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import database
import summarization_tasks


@pytest.fixture
def setup_database():
    """Initialize database for testing with isolated temp directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_file = os.path.join(temp_dir, "test_discord_messages.db")
        with patch.object(database, 'DB_FILE', temp_db_file), \
             patch.object(database, 'DB_DIRECTORY', temp_dir):
            database.init_database()
            yield temp_db_file


def _ids():
    """
    Fresh user/guild id pair so tests never collide.

    Numeric, because Discord IDs are snowflakes and the sweeper calls
    int(guild_id) to look the guild up.
    """
    return str(uuid.uuid4().int % 10**18), str(uuid.uuid4().int % 10**18)


def _insert_raw_grant(author_id, guild_id, expires_at, swept=0, hours=1, points=25):
    """Insert a grant row directly, to set up expired/stale state."""
    now = datetime.now(timezone.utc)
    with database.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO frenbot_access_grants (
                author_id, author_name, guild_id, points_spent,
                hours_granted, granted_at, expires_at, swept
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (author_id, "TestUser", guild_id, points, hours,
             now.isoformat(), expires_at.isoformat(), swept)
        )
        conn.commit()


def _make_guild(role_name="frenbot-access", member_has_role=True, remove_side_effect=None):
    """Build a mock guild/role/member trio for sweeper tests."""
    role = MagicMock()
    role.name = role_name
    role.position = 5

    member = MagicMock()
    member.roles = [role] if member_has_role else []
    member.remove_roles = AsyncMock(side_effect=remove_side_effect)

    guild = MagicMock()
    guild.roles = [role]

    return guild, role, member


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

def test_frenbot_config_defaults():
    """Frenbot access constants exist and are sane."""
    import config

    assert config.FRENBOT_ACCESS_COST >= 1
    assert config.FRENBOT_ACCESS_DURATION_HOURS >= 1
    assert isinstance(config.FRENBOT_ACCESS_ROLE_NAME, str)
    assert config.FRENBOT_ACCESS_ROLE_NAME
    assert config.FRENBOT_ACCESS_MAX_HOURS >= 0


# ---------------------------------------------------------------------------
# grant + stacking arithmetic
# ---------------------------------------------------------------------------

def test_no_expiry_for_user_who_never_redeemed(setup_database):
    """A user with no grants has no expiry."""
    user_id, guild_id = _ids()
    assert database.get_frenbot_access_expiry(user_id, guild_id) is None


def test_fresh_grant_expires_one_hour_out(setup_database):
    """A first redemption expires `hours` from now and is not marked stacked."""
    user_id, guild_id = _ids()
    before = datetime.now(timezone.utc)

    grant = database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    assert grant is not None
    assert grant['stacked'] is False
    delta = grant['expires_at'] - before
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)


def test_redeeming_while_active_stacks(setup_database):
    """Redeeming during an active grant extends from the existing expiry."""
    user_id, guild_id = _ids()

    first = database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)
    second = database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    assert first['stacked'] is False
    assert second['stacked'] is True
    # Second grant starts where the first ended, not from "now".
    assert second['expires_at'] - first['expires_at'] == timedelta(hours=1)

    # Two purchases recorded, not one row overwritten.
    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT COUNT(*) AS c FROM frenbot_access_grants WHERE author_id = ?",
            (user_id,)
        ).fetchone()['c']
    assert rows == 2


def test_expired_unswept_grant_stacks_from_now(setup_database):
    """
    A lapsed grant the sweeper has not processed yet must not be stacked onto.

    Otherwise the user pays for access that has already elapsed.
    """
    user_id, guild_id = _ids()
    stale_expiry = datetime.now(timezone.utc) - timedelta(hours=3)
    _insert_raw_grant(user_id, guild_id, stale_expiry, swept=0)

    before = datetime.now(timezone.utc)
    grant = database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    assert grant['stacked'] is False
    delta = grant['expires_at'] - before
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)
    assert grant['expires_at'] > before


def test_concurrent_redemptions_do_not_lose_an_hour(setup_database):
    """
    Two simultaneous redemptions must yield two hours, not one.

    The read-then-insert runs inside BEGIN IMMEDIATE, so the second
    redemption cannot stack onto the same base timestamp as the first.
    """
    user_id, guild_id = _ids()
    before = datetime.now(timezone.utc)

    def redeem():
        return database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: redeem(), range(2)))

    assert all(r is not None for r in results)

    final = database.get_frenbot_access_expiry(user_id, guild_id)
    delta = final - before
    assert timedelta(minutes=119) < delta < timedelta(minutes=121), (
        f"expected ~2h of stacked access, got {delta}"
    )


def test_grant_records_points_and_hours(setup_database):
    """The purchase history keeps what was charged - this is the audit trail."""
    user_id, guild_id = _ids()
    database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT points_spent, hours_granted, swept FROM frenbot_access_grants WHERE author_id = ?",
            (user_id,)
        ).fetchone()

    assert row['points_spent'] == 25
    assert row['hours_granted'] == 1
    assert row['swept'] == 0


def test_grant_does_not_touch_daily_point_awards(setup_database):
    """
    Redeeming must leave daily_point_awards untouched.

    A row there would collide with UNIQUE(author_id, guild_id, date) and make
    the nightly summarizer skip point awards for the whole guild.
    """
    user_id, guild_id = _ids()
    database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    with database.get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM daily_point_awards").fetchone()['c']
    assert count == 0


# ---------------------------------------------------------------------------
# expiry query
# ---------------------------------------------------------------------------

def test_active_grant_not_reported_expired(setup_database):
    """A user with live access is not swept."""
    user_id, guild_id = _ids()
    database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    expired = database.get_expired_frenbot_access_users()
    assert not any(e['author_id'] == user_id for e in expired)


def test_expired_grant_reported(setup_database):
    """A lapsed, unswept grant is reported for sweeping."""
    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    expired = database.get_expired_frenbot_access_users()
    match = [e for e in expired if e['author_id'] == user_id]
    assert len(match) == 1
    assert match[0]['guild_id'] == guild_id


def test_partially_expired_stack_not_reported(setup_database):
    """
    A user with one lapsed and one still-active grant keeps their access.

    Sweeping on any expired row would revoke stacked access early.
    """
    user_id, guild_id = _ids()
    now = datetime.now(timezone.utc)
    _insert_raw_grant(user_id, guild_id, now - timedelta(hours=1))
    _insert_raw_grant(user_id, guild_id, now + timedelta(hours=1))

    expired = database.get_expired_frenbot_access_users()
    assert not any(e['author_id'] == user_id for e in expired)


def test_swept_grant_not_reported_again(setup_database):
    """Sweeping is idempotent - handled users stop coming back."""
    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    assert any(e['author_id'] == user_id for e in database.get_expired_frenbot_access_users())

    database.mark_frenbot_access_swept(user_id, guild_id)

    assert not any(e['author_id'] == user_id for e in database.get_expired_frenbot_access_users())


def test_mark_swept_leaves_active_rows_alone(setup_database):
    """A redemption landing mid-sweep must not be marked swept."""
    user_id, guild_id = _ids()
    now = datetime.now(timezone.utc)
    _insert_raw_grant(user_id, guild_id, now - timedelta(hours=1))   # expired
    _insert_raw_grant(user_id, guild_id, now + timedelta(hours=1))   # just purchased

    database.mark_frenbot_access_swept(user_id, guild_id)

    with database.get_connection() as conn:
        rows = conn.execute(
            "SELECT expires_at, swept FROM frenbot_access_grants WHERE author_id = ? ORDER BY expires_at",
            (user_id,)
        ).fetchall()

    assert rows[0]['swept'] == 1   # expired row swept
    assert rows[1]['swept'] == 0   # active row untouched
    # And the user still has access.
    assert database.get_frenbot_access_expiry(user_id, guild_id) > now


# ---------------------------------------------------------------------------
# expiry sweeper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sweeper_removes_role_on_expiry(setup_database):
    """The sweep removes the access role once every grant has lapsed."""
    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    guild, role, member = _make_guild()
    client = MagicMock()
    client.get_guild.return_value = guild

    with patch.object(summarization_tasks, 'discord_client', client), \
         patch.object(summarization_tasks, '_get_guild_member', AsyncMock(return_value=member)):
        await summarization_tasks.process_frenbot_access_expiries()

    member.remove_roles.assert_awaited_once()
    assert member.remove_roles.await_args.args[0] is role
    assert not database.get_expired_frenbot_access_users()


@pytest.mark.asyncio
async def test_sweeper_leaves_active_access_alone(setup_database):
    """Live access is never revoked."""
    user_id, guild_id = _ids()
    database.record_frenbot_access_grant(user_id, "TestUser", guild_id, 25, 1)

    guild, role, member = _make_guild()
    client = MagicMock()
    client.get_guild.return_value = guild

    with patch.object(summarization_tasks, 'discord_client', client), \
         patch.object(summarization_tasks, '_get_guild_member', AsyncMock(return_value=member)):
        await summarization_tasks.process_frenbot_access_expiries()

    member.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweeper_marks_swept_when_member_left(setup_database):
    """A departed member's rows are swept rather than retried forever."""
    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    guild, role, member = _make_guild()
    client = MagicMock()
    client.get_guild.return_value = guild

    with patch.object(summarization_tasks, 'discord_client', client), \
         patch.object(summarization_tasks, '_get_guild_member', AsyncMock(return_value=None)):
        await summarization_tasks.process_frenbot_access_expiries()

    assert not database.get_expired_frenbot_access_users()


@pytest.mark.asyncio
async def test_sweeper_retries_after_permission_failure(setup_database):
    """
    A Forbidden on role removal leaves the rows unswept.

    The next pass retries once an admin fixes the role hierarchy.
    """
    import discord

    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    forbidden = discord.Forbidden(MagicMock(status=403), "missing permissions")
    guild, role, member = _make_guild(remove_side_effect=forbidden)
    client = MagicMock()
    client.get_guild.return_value = guild

    with patch.object(summarization_tasks, 'discord_client', client), \
         patch.object(summarization_tasks, '_get_guild_member', AsyncMock(return_value=member)):
        await summarization_tasks.process_frenbot_access_expiries()

    # Still pending, so the next sweep will try again.
    assert any(e['author_id'] == user_id for e in database.get_expired_frenbot_access_users())


@pytest.mark.asyncio
async def test_sweeper_handles_missing_role(setup_database):
    """If the role was deleted there is nothing to remove; stop retrying."""
    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    guild, role, member = _make_guild(role_name="some-other-role")
    client = MagicMock()
    client.get_guild.return_value = guild

    with patch.object(summarization_tasks, 'discord_client', client), \
         patch.object(summarization_tasks, '_get_guild_member', AsyncMock(return_value=member)):
        await summarization_tasks.process_frenbot_access_expiries()

    member.remove_roles.assert_not_awaited()
    assert not database.get_expired_frenbot_access_users()


@pytest.mark.asyncio
async def test_sweeper_noop_without_client(setup_database):
    """No discord client - the sweep logs and returns without touching rows."""
    user_id, guild_id = _ids()
    _insert_raw_grant(user_id, guild_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    with patch.object(summarization_tasks, 'discord_client', None):
        await summarization_tasks.process_frenbot_access_expiries()

    assert any(e['author_id'] == user_id for e in database.get_expired_frenbot_access_users())


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

def test_migration_creates_table_on_existing_db():
    """
    migrate_database() adds the table to a database that predates it.

    This is the path the production DB takes on deploy.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_file = os.path.join(temp_dir, "legacy.db")

        # A "legacy" DB with the messages table but no frenbot table.
        with sqlite3.connect(temp_db_file) as conn:
            conn.execute(database.CREATE_MESSAGES_TABLE)
            conn.execute(database.CREATE_USER_ROLE_COLORS_TABLE)
            conn.commit()

        with patch.object(database, 'DB_FILE', temp_db_file), \
             patch.object(database, 'DB_DIRECTORY', temp_dir):
            database.migrate_database()

            with sqlite3.connect(temp_db_file) as conn:
                found = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='frenbot_access_grants'"
                ).fetchone()

        assert found is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
