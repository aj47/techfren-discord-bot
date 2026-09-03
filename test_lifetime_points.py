"""
Tests for lifetime point tracking.

total_points is a wallet — role colours, GIF bypasses, frenbot access and
/ask-fred all spend it — so it cannot answer "how much has this member earned".
lifetime_points answers that, and nothing may ever reduce it.
"""

import os
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest

import database


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


def test_award_raises_balance_and_lifetime(setup_database):
    database.award_points_to_user(USER, "ada", GUILD, 10)
    database.award_points_to_user(USER, "ada", GUILD, 5)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary == {'points': 15, 'lifetime_points': 15, 'spent': 0}


def test_spending_leaves_the_lifetime_total_alone(setup_database):
    database.award_points_to_user(USER, "ada", GUILD, 20)
    assert database.deduct_user_points(USER, GUILD, 12) is True

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 8
    assert summary['lifetime_points'] == 20
    assert summary['spent'] == 12


def test_spending_everything_still_remembers_what_was_earned(setup_database):
    database.award_points_to_user(USER, "ada", GUILD, 20)
    database.deduct_user_points(USER, GUILD, 20)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 0
    assert summary['lifetime_points'] == 20
    assert summary['spent'] == 20


def test_earning_after_spending_accumulates(setup_database):
    database.award_points_to_user(USER, "ada", GUILD, 10)
    database.deduct_user_points(USER, GUILD, 10)
    database.award_points_to_user(USER, "ada", GUILD, 7)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 7
    assert summary['lifetime_points'] == 17
    assert summary['spent'] == 10


def test_a_refund_is_not_an_earning(setup_database):
    """The role-colour rollback hands points back; counting them again would
    inflate the lifetime total for something the member earned once."""
    database.award_points_to_user(USER, "ada", GUILD, 10)
    database.deduct_user_points(USER, GUILD, 4)
    database.award_points_to_user(USER, "ada", GUILD, 4, counts_as_earned=False)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 10
    assert summary['lifetime_points'] == 10
    assert summary['spent'] == 0


def test_award_clamp_applies_to_both_totals(setup_database):
    """Awards are clamped to 20; the lifetime total must not bank the excess."""
    database.award_points_to_user(USER, "ada", GUILD, 50)

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 20
    assert summary['lifetime_points'] == 20


def test_summary_of_an_unknown_user_is_zero(setup_database):
    assert database.get_user_points_summary("nobody", GUILD) == {
        'points': 0, 'lifetime_points': 0, 'spent': 0
    }


def test_leaderboard_carries_the_lifetime_total(setup_database):
    database.award_points_to_user("u1", "ada", GUILD, 20)
    database.deduct_user_points("u1", GUILD, 15)
    database.award_points_to_user("u2", "bo", GUILD, 12)

    board = {row['author_id']: row for row in database.get_leaderboard(GUILD, limit=10)}
    assert board['u1']['total_points'] == 5
    assert board['u1']['lifetime_points'] == 20
    assert board['u2']['total_points'] == 12
    assert board['u2']['lifetime_points'] == 12


def _legacy_points_table(db_file):
    """Recreate the pre-migration user_points table (no lifetime_points)."""
    with sqlite3.connect(db_file) as conn:
        conn.execute("DROP TABLE user_points")
        conn.execute(
            """
            CREATE TABLE user_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                total_points INTEGER DEFAULT 0,
                last_updated TIMESTAMP NOT NULL,
                UNIQUE(author_id, guild_id)
            )
            """
        )
        conn.commit()


def _insert_legacy_user(db_file, author_id, name, points):
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO user_points (author_id, author_name, guild_id, total_points, last_updated) "
            "VALUES (?, ?, ?, ?, ?)",
            (author_id, name, GUILD, points, datetime.now().isoformat()),
        )
        conn.commit()


def test_migration_backfills_from_the_award_history(setup_database):
    """An existing database has no lifetime column, but daily_point_awards has
    recorded every award ever made — that history is the backfill."""
    db_file = setup_database
    _legacy_points_table(db_file)
    # Earned 50 across three days, spent down to 12.
    _insert_legacy_user(db_file, "spender", "ada", 12)
    for day, pts in (("2026-01-01", 20), ("2026-01-02", 20), ("2026-01-03", 10)):
        database.store_daily_point_award(
            author_id="spender", author_name="ada", guild_id=GUILD,
            date=datetime.fromisoformat(day), points=pts, reason="contribution",
        )

    database.migrate_database()

    summary = database.get_user_points_summary("spender", GUILD)
    assert summary['points'] == 12
    assert summary['lifetime_points'] == 50
    assert summary['spent'] == 38


def test_migration_never_lowers_a_balance(setup_database):
    """A member whose awards predate the daily ledger must not end up with a
    lifetime total below the points they are actually holding."""
    db_file = setup_database
    _legacy_points_table(db_file)
    _insert_legacy_user(db_file, "veteran", "bo", 40)

    database.migrate_database()

    summary = database.get_user_points_summary("veteran", GUILD)
    assert summary['points'] == 40
    assert summary['lifetime_points'] == 40
    assert summary['spent'] == 0


def test_migration_is_idempotent(setup_database):
    """Startup runs migrations every time; a second pass must not re-backfill
    over a lifetime total that has since moved on."""
    database.award_points_to_user(USER, "ada", GUILD, 20)
    database.deduct_user_points(USER, GUILD, 20)

    database.migrate_database()
    database.migrate_database()

    summary = database.get_user_points_summary(USER, GUILD)
    assert summary['points'] == 0
    assert summary['lifetime_points'] == 20
