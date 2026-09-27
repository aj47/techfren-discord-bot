"""
Tests for the /leaderboard command's boards.

The board used to rank on the spendable balance, which meant a member who
bought a role colour slid down the rankings while a member who hoarded climbed
up. The default board now ranks on everything earned and shows the balance next
to it, so spending is visible rather than penalised.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

import database
from leaderboard_format import format_leaderboard_message


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

ROWS = [
    {
        'author_id': 'u1', 'author_name': 'tazr', 'total_points': 336,
        'lifetime_points': 1017, 'spent': 681,
    },
    {
        'author_id': 'u2', 'author_name': 'peas', 'total_points': 410,
        'lifetime_points': 531, 'spent': 121,
    },
]


def test_all_time_board_leads_with_and_shows_both_numbers():
    message = format_leaderboard_message(ROWS, 'lifetime')

    assert 'earned all-time' in message
    assert '🥇 **tazr**: 1017 earned · 336 left' in message
    assert '🥈 **peas**: 531 earned · 410 left' in message
    # The board explains itself, so a member cannot read a low balance as
    # "earned little".
    assert 'spending points never lowers it' in message


def test_balance_board_still_available_for_people_checking_their_wallet():
    message = format_leaderboard_message(ROWS, 'balance')

    assert 'points left to spend' in message
    assert '🥇 **tazr**: 336 left · 1017 earned' in message


def test_spenders_board_names_what_the_points_went_on():
    message = format_leaderboard_message(ROWS, 'spenders')

    assert 'points used in the server' in message
    assert '🥇 **tazr**: 681 spent · 336 left' in message
    assert 'role colour, a GIF bypass or frenbot access' in message


def test_spending_does_not_demote_a_member(setup_database):
    """End-to-end through the real database: tazr earns more and spends more,
    so he leads the boards that rank on earning and on spending, and only the
    wallet board puts the hoarder first."""
    database.award_points_to_user('u1', 'tazr', GUILD, 20)
    database.award_points_to_user('u1', 'tazr', GUILD, 5)
    database.deduct_user_points('u1', GUILD, 15)
    database.award_points_to_user('u2', 'peas', GUILD, 12)

    by_lifetime = database.get_leaderboard(GUILD, limit=10)
    assert [row['author_name'] for row in by_lifetime] == ['tazr', 'peas']
    assert '🥇 **tazr**: 25 earned · 10 left' in format_leaderboard_message(by_lifetime, 'lifetime')

    by_balance = database.get_leaderboard(GUILD, limit=10, order_by='balance')
    assert [row['author_name'] for row in by_balance] == ['peas', 'tazr']

    by_spent = database.get_leaderboard(GUILD, limit=10, order_by='spent')
    assert [row['author_name'] for row in by_spent] == ['tazr', 'peas']
    assert '🥇 **tazr**: 15 spent · 10 left' in format_leaderboard_message(by_spent, 'spenders')
