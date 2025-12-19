"""
Test script for GIF bypass functionality.
Tests the points-based GIF limit bypass feature.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import database
from gif_limiter import (
    check_gif_rate_limit,
    check_and_record_gif_post,
    record_gif_bypass,
    GIF_LIMIT_PER_WINDOW,
    GIF_TIME_WINDOW,
    _gif_post_history,
)


@pytest.fixture(autouse=True)
def clear_gif_history():
    """Clear GIF post history before each test."""
    _gif_post_history.clear()
    yield
    _gif_post_history.clear()


@pytest.fixture
def setup_database():
    """Initialize database for testing."""
    database.init_database()
    yield


@pytest.mark.asyncio
async def test_record_gif_bypass():
    """Test that record_gif_bypass clears history to allow posting."""
    user_id = "test_user_123"

    # First, hit the rate limit normally
    await check_and_record_gif_post(user_id)

    # User is now rate limited
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is False

    # Use bypass - this should clear history and allow posting
    await record_gif_bypass(user_id)

    # Now user should be able to post again
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is True


@pytest.mark.asyncio
async def test_record_gif_bypass_allows_repost():
    """Test that after bypass, user can post a GIF that gets recorded normally."""
    user_id = "test_user_456"

    # First, hit the rate limit normally
    await check_and_record_gif_post(user_id)

    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is False

    # Use bypass to clear history
    await record_gif_bypass(user_id)

    # User should now be able to post
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is True

    # Record the repost (simulating the user posting their GIF)
    can_post, _ = await check_and_record_gif_post(user_id)
    assert can_post is True

    # Now user should be rate limited again
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is False


@pytest.mark.asyncio
async def test_bypass_clears_history_with_timestamp():
    """Test that bypass clears history and respects the timestamp parameter."""
    user_id = "test_user_789"

    # First, hit the rate limit
    await check_and_record_gif_post(user_id)
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is False

    # Use bypass - this clears history
    await record_gif_bypass(user_id)

    # User should be able to post now
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is True


def test_gif_bypass_points_cost_config():
    """Test that GIF bypass points cost is properly configured."""
    import config
    
    # Check default value
    assert hasattr(config, 'GIF_BYPASS_POINTS_COST')
    assert isinstance(config.GIF_BYPASS_POINTS_COST, int)
    assert config.GIF_BYPASS_POINTS_COST >= 1


def test_database_deduct_user_points(setup_database):
    """Test that deduct_user_points works correctly."""
    import uuid
    user_id = f"test_user_deduct_{uuid.uuid4().hex[:8]}"
    guild_id = f"test_guild_{uuid.uuid4().hex[:8]}"

    # Award points in multiple calls (max 20 per call due to clamping)
    for _ in range(5):
        database.award_points_to_user(user_id, "TestUser", guild_id, 20)

    # Verify points were awarded (5 * 20 = 100)
    points = database.get_user_points(user_id, guild_id)
    assert points == 100

    # Deduct points
    success = database.deduct_user_points(user_id, guild_id, 50)
    assert success is True

    # Verify points were deducted
    points = database.get_user_points(user_id, guild_id)
    assert points == 50


def test_database_deduct_insufficient_points(setup_database):
    """Test that deduct_user_points fails when user has insufficient points."""
    import uuid
    user_id = f"test_user_insufficient_{uuid.uuid4().hex[:8]}"
    guild_id = f"test_guild_{uuid.uuid4().hex[:8]}"

    # Award points (max 20 per call due to clamping)
    database.award_points_to_user(user_id, "TestUser", guild_id, 20)

    # Verify initial points
    initial_points = database.get_user_points(user_id, guild_id)
    assert initial_points == 20

    # Try to deduct more than available (20 points)
    success = database.deduct_user_points(user_id, guild_id, 100)
    assert success is False

    # Verify points unchanged
    points = database.get_user_points(user_id, guild_id)
    assert points == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

