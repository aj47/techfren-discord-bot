"""Promo-only history: delete a message only when every stored post is promo.

The messages table is pruned to about a day, so the verdict reads a durable
per-message record. These tests cover the decision, not Discord.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

import database
from promo_only import (
    Verdict,
    is_promotional,
    record_message,
    verdict_for,
)


@pytest.fixture
def temp_database():
    """Isolated database so the new table never touches production."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_file = os.path.join(temp_dir, "test_discord_messages.db")
        with patch.object(database, "DB_FILE", temp_db_file), \
             patch.object(database, "DB_DIRECTORY", temp_dir):
            database.init_database()
            yield temp_db_file


def test_invite_and_pitch_are_promotional():
    assert is_promotional("join my server https://discord.gg/abc123")
    assert is_promotional("DM me for a free airdrop, limited time")
    assert is_promotional("check this out https://t.me/coins")


def test_ordinary_chat_is_not_promotional():
    assert not is_promotional("how do I set the temperature on this model?")
    assert not is_promotional("https://github.com/aj47/techfren-discord-bot looks useful")
    assert not is_promotional("")


def test_a_members_own_earnings_are_not_promotional():
    """A member reporting their own creator fees is not a pitch. 'earning $5k' still is."""
    assert not is_promotional("but then i noticed i already earned $500 in creator fees lol")
    assert is_promotional("I am earning $5k per month")


def test_identity_proxy_pitch_is_promotional():
    """The North Korea pitch names AI training work and a country list. It matches no old phrase."""
    glse = (
        "Hello! I currently work with AI training platforms and am generating over "
        "$10K in monthly revenue. I am seeking to collaborate with reliable individuals "
        "based in the UK, the US, Canada, or Australia."
    )
    amon = (
        "I am handling AI training task and earning $5k per month. "
        "But we can only create one account on that platform on one computer. "
        "Who helps me? UK, US, CA, AU."
    )
    assert is_promotional(glse)
    assert is_promotional(amon)


def test_all_promo_history_says_delete(temp_database):
    for n, text in enumerate(("join https://discord.gg/aa", "free airdrop, DM me", "https://t.me/coins now")):
        record_message("42", "101", f"m{n}", text)

    verdict = verdict_for("42", "101", "another https://discord.gg/bb pitch")

    assert verdict.delete is True
    assert verdict.total == 4
    assert verdict.promo == 4
    assert verdict.reason == "all stored messages are promotional"


def test_one_ordinary_message_blocks_delete(temp_database):
    record_message("42", "101", "m1", "join https://discord.gg/aa")
    record_message("42", "101", "m2", "what model are you running?")
    record_message("42", "101", "m3", "https://t.me/coins")

    verdict = verdict_for("42", "101", "join https://discord.gg/bb")

    assert verdict.delete is False
    assert verdict.reason == "history is not all promotional"


def test_first_message_that_is_promo_is_deleted(temp_database):
    verdict = verdict_for("42", "101", "join https://discord.gg/aa")

    assert verdict.delete is True
    assert verdict.total == 1
    assert verdict.reason == "all stored messages are promotional"


def test_same_message_is_counted_once(temp_database):
    record_message("42", "101", "m1", "join https://discord.gg/aa")
    record_message("42", "101", "m1", "join https://discord.gg/aa")

    verdict = verdict_for("42", "101", "free airdrop")

    assert verdict.total == 2


def test_other_member_does_not_count(temp_database):
    record_message("7", "101", "m1", "hello, how does this work?")
    record_message("42", "101", "m2", "join https://discord.gg/aa")
    record_message("42", "101", "m3", "free airdrop, DM me")

    verdict = verdict_for("42", "101", "https://t.me/coins")

    assert verdict.delete is True
    assert verdict.total == 3


def test_verdict_names_its_fields():
    verdict = Verdict(delete=False, total=0, promo=0, reason="not enough history")
    assert verdict.delete is False


def test_judging_a_recorded_message_does_not_double_count(temp_database):
    record_message("42", "101", "m1", "join https://discord.gg/aa")
    record_message("42", "101", "m2", "free airdrop, DM me")
    record_message("42", "101", "m3", "https://t.me/coins")

    verdict = verdict_for("42", "101", "https://t.me/coins", message_id="m3")

    assert verdict.total == 3
    assert verdict.delete is True


def test_older_ordinary_message_blocks_delete(temp_database):
    """A message the bot already forgot still counts. One ordinary post, ever, stops the delete."""
    database.record_promo_message("42", "101", "old1", "how do I set the temperature?", False)
    record_message("42", "101", "new1", "join https://discord.gg/aa")

    verdict = verdict_for("42", "101", "free airdrop, DM me")

    assert verdict.delete is False
    assert verdict.reason == "history is not all promotional"


def test_exempt_role_is_never_deleted(temp_database):
    record_message("42", "101", "m1", "join https://discord.gg/aa")

    verdict = verdict_for("42", "101", "free airdrop, DM me", exempt=True)

    assert verdict.delete is False
    assert verdict.reason == "exempt role"


def test_archive_history_is_loaded_once_and_blocks_delete(temp_database, tmp_path):
    import sqlite3

    archive = tmp_path / "archive.db"
    conn = sqlite3.connect(archive)
    conn.execute("CREATE TABLE messages (id TEXT, guild_id TEXT, author_id TEXT, content TEXT)")
    conn.executemany(
        "INSERT INTO messages VALUES (?, ?, ?, ?)",
        [
            ("old1", "101", "42", "how do I set the temperature?"),
            ("old2", "101", "42", "join https://discord.gg/aa"),
        ],
    )
    conn.commit()
    conn.close()

    from promo_only import load_archive_history

    assert load_archive_history("42", "101", archive) == 2
    assert load_archive_history("42", "101", archive) == 0

    verdict = verdict_for("42", "101", "free airdrop, DM me")

    assert verdict.delete is False
    assert verdict.total == 3
