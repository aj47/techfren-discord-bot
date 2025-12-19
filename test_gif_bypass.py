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
    """Test that record_gif_bypass properly records a GIF post."""
    user_id = "test_user_123"
    
    # Initially user can post
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is True
    
    # Record a bypass
    await record_gif_bypass(user_id)
    
    # Now user should be rate limited
    can_post, seconds = await check_gif_rate_limit(user_id)
    assert can_post is False
    assert seconds > 0


@pytest.mark.asyncio
async def test_record_gif_bypass_when_already_rate_limited():
    """Test that bypass still records when user is already rate limited."""
    user_id = "test_user_456"
    
    # First, hit the rate limit normally
    await check_and_record_gif_post(user_id)
    
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is False
    
    # Record another bypass (this is allowed when user pays points)
    await record_gif_bypass(user_id)
    
    # User should still be rate limited
    can_post, _ = await check_gif_rate_limit(user_id)
    assert can_post is False


@pytest.mark.asyncio
async def test_bypass_records_with_timestamp():
    """Test that bypass respects the timestamp parameter."""
    user_id = "test_user_789"
    past_time = datetime.now(timezone.utc) - GIF_TIME_WINDOW - timedelta(seconds=1)
    
    # Record a bypass in the past
    await record_gif_bypass(user_id, past_time)
    
    # User should be able to post now since the bypass was in the past
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

