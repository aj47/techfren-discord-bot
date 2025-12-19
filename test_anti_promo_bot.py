"""
Tests for the anti-promo bot module.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
import os

# Set test environment variables before importing
os.environ['ANTI_PROMO_ENABLED'] = 'true'
os.environ['ANTI_PROMO_MIN_ACCOUNT_AGE_DAYS'] = '7'
os.environ['ANTI_PROMO_NEW_MEMBER_WINDOW_MINUTES'] = '30'
os.environ['ANTI_PROMO_ACTION'] = 'kick'

from anti_promo_bot import (
    is_anti_promo_enabled,
    check_account_age,
    check_member_join_time,
    check_message_for_promo_patterns,
    check_if_established_user,
    analyze_message_for_spam,
    handle_suspicious_message,
)


class TestIsAntiPromoEnabled:
    """Tests for is_anti_promo_enabled function."""
    
    def test_enabled_by_default(self):
        """Test that anti-promo is enabled by default."""
        assert is_anti_promo_enabled() is True
    
    @patch.dict(os.environ, {'ANTI_PROMO_ENABLED': 'false'})
    def test_can_be_disabled(self):
        """Test that anti-promo can be disabled via environment variable."""
        # Need to reimport to get new env var value
        import importlib
        import anti_promo_bot
        importlib.reload(anti_promo_bot)
        assert anti_promo_bot.is_anti_promo_enabled() is False
        # Reload with original value
        os.environ['ANTI_PROMO_ENABLED'] = 'true'
        importlib.reload(anti_promo_bot)


class TestCheckAccountAge:
    """Tests for check_account_age function."""
    
    def test_new_account_flagged(self):
        """Test that new accounts are flagged."""
        # Account created 3 days ago
        user_created_at = datetime.now(timezone.utc) - timedelta(days=3)
        is_too_new, age_days = check_account_age(user_created_at)
        assert is_too_new is True
        assert age_days == 3
    
    def test_old_account_not_flagged(self):
        """Test that old accounts are not flagged."""
        # Account created 30 days ago
        user_created_at = datetime.now(timezone.utc) - timedelta(days=30)
        is_too_new, age_days = check_account_age(user_created_at)
        assert is_too_new is False
        assert age_days == 30
    
    def test_handles_naive_datetime(self):
        """Test that naive datetime is handled correctly."""
        # Naive datetime (no timezone info)
        user_created_at = datetime.now() - timedelta(days=5)
        is_too_new, age_days = check_account_age(user_created_at)
        assert is_too_new is True
        assert age_days == 5


class TestCheckMemberJoinTime:
    """Tests for check_member_join_time function."""
    
    def test_new_member_flagged(self):
        """Test that new members are flagged."""
        # Joined 10 minutes ago
        joined_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        is_new, minutes = check_member_join_time(joined_at)
        assert is_new is True
        assert minutes == 10
    
    def test_old_member_not_flagged(self):
        """Test that members who joined long ago are not flagged."""
        # Joined 2 hours ago
        joined_at = datetime.now(timezone.utc) - timedelta(hours=2)
        is_new, minutes = check_member_join_time(joined_at)
        assert is_new is False
        assert minutes == 120
    
    def test_handles_none_join_time(self):
        """Test that None join time is handled."""
        is_new, minutes = check_member_join_time(None)
        assert is_new is False
        assert minutes == -1


class TestCheckMessageForPromoPatterns:
    """Tests for check_message_for_promo_patterns function."""
    
    def test_discord_invite_detected(self):
        """Test that Discord invite links are detected."""
        has_promo, patterns = check_message_for_promo_patterns("Join my server! discord.gg/xyz123")
        assert has_promo is True
        assert any('discord' in p.lower() for p in patterns)
    
    def test_crypto_scam_detected(self):
        """Test that crypto scam messages are detected."""
        has_promo, patterns = check_message_for_promo_patterns("Free crypto airdrop! Claim now!")
        assert has_promo is True
    
    def test_telegram_link_detected(self):
        """Test that Telegram links are detected."""
        has_promo, patterns = check_message_for_promo_patterns("Contact me on t.me/scammer")
        assert has_promo is True
    
    def test_normal_message_not_flagged(self):
        """Test that normal messages are not flagged."""
        has_promo, patterns = check_message_for_promo_patterns("Hello everyone! How are you?")
        assert has_promo is False
        assert patterns == []
    
    def test_multiple_patterns_detected(self):
        """Test that multiple patterns can be detected."""
        message = "Free NFT airdrop! Join discord.gg/scam and t.me/scammer"
        has_promo, patterns = check_message_for_promo_patterns(message)
        assert has_promo is True
        assert len(patterns) >= 2


class TestCheckIfEstablishedUser:
    """Tests for check_if_established_user function."""

    @patch('database.get_user_message_count_since')
    def test_user_with_many_messages_is_established(self, mock_get_count):
        """Test that a user with 25+ messages is considered established."""
        mock_get_count.return_value = 50

        is_established, message_count = check_if_established_user("123456789")

        assert is_established is True
        assert message_count == 50
        mock_get_count.assert_called_once()

    @patch('database.get_user_message_count_since')
    def test_user_with_few_messages_not_established(self, mock_get_count):
        """Test that a user with less than 25 messages is not established."""
        mock_get_count.return_value = 10

        is_established, message_count = check_if_established_user("123456789")

        assert is_established is False
        assert message_count == 10

    @patch('database.get_user_message_count_since')
    def test_user_at_threshold_is_established(self, mock_get_count):
        """Test that a user with exactly 25 messages is established."""
        mock_get_count.return_value = 25

        is_established, message_count = check_if_established_user("123456789")

        assert is_established is True
        assert message_count == 25


class TestAnalyzeMessageForSpam:
    """Tests for analyze_message_for_spam function."""

    def test_promo_from_new_account_is_suspicious(self):
        """Test that promo from new account is flagged as suspicious."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=2)
        joined_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        with patch('anti_promo_bot.check_if_established_user', return_value=(False, 0)):
            result = analyze_message_for_spam(
                content="Join discord.gg/scam for free crypto!",
                user_created_at=user_created_at,
                member_joined_at=joined_at,
                is_bot=False,
                user_id="123456789"
            )

        assert result['is_suspicious'] is True
        assert result['confidence'] > 0.5
        assert result['recommended_action'] in ('delete', 'kick', 'ban')

    def test_normal_message_from_new_account_not_suspicious(self):
        """Test that normal message from new account is not suspicious."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=2)
        joined_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        result = analyze_message_for_spam(
            content="Hello everyone! Nice to meet you!",
            user_created_at=user_created_at,
            member_joined_at=joined_at,
            is_bot=False
        )

        assert result['is_suspicious'] is False

    def test_promo_from_old_account_less_suspicious(self):
        """Test that promo from established account is less suspicious."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=365)
        joined_at = datetime.now(timezone.utc) - timedelta(days=30)

        result = analyze_message_for_spam(
            content="Check out discord.gg/mylegitserver",
            user_created_at=user_created_at,
            member_joined_at=joined_at,
            is_bot=False
        )

        # Should have some confidence but not be automatically suspicious
        assert result['confidence'] > 0
        # Old accounts with promo get more leniency
        assert result['is_suspicious'] is False or result['recommended_action'] == 'delete'

    def test_bot_accounts_skipped(self):
        """Test that verified bot accounts are skipped."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=1)

        result = analyze_message_for_spam(
            content="discord.gg/scam free crypto!",
            user_created_at=user_created_at,
            member_joined_at=None,
            is_bot=True
        )

        assert result['is_suspicious'] is False

    def test_established_user_protected_from_kick_ban(self):
        """Test that established users with 25+ messages are only deleted, not kicked/banned."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=2)
        joined_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Mock the established user check to return True with 30 messages
        with patch('anti_promo_bot.check_if_established_user', return_value=(True, 30)):
            result = analyze_message_for_spam(
                content="Join discord.gg/scam for free crypto!",
                user_created_at=user_created_at,
                member_joined_at=joined_at,
                is_bot=False,
                user_id="123456789"
            )

        assert result['is_suspicious'] is True
        assert result['is_established_user'] is True
        assert result['message_count_in_period'] == 30
        # Established users should only get delete, not kick/ban
        assert result['recommended_action'] == 'delete'
        # Check that the protection reason is included
        assert any('protected' in reason.lower() or 'established' in reason.lower()
                   for reason in result['reasons'])

    def test_non_established_user_can_be_kicked(self):
        """Test that non-established users posting promo can be kicked/banned."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=2)
        joined_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Mock the established user check to return False with only 5 messages
        with patch('anti_promo_bot.check_if_established_user', return_value=(False, 5)):
            result = analyze_message_for_spam(
                content="Join discord.gg/scam for free crypto!",
                user_created_at=user_created_at,
                member_joined_at=joined_at,
                is_bot=False,
                user_id="123456789"
            )

        assert result['is_suspicious'] is True
        assert result['is_established_user'] is False
        assert result['message_count_in_period'] == 5
        # Non-established users can be kicked/banned
        assert result['recommended_action'] in ('kick', 'ban')

    def test_result_includes_established_user_fields(self):
        """Test that analysis result includes established user fields."""
        user_created_at = datetime.now(timezone.utc) - timedelta(days=30)

        with patch('anti_promo_bot.check_if_established_user', return_value=(False, 0)):
            result = analyze_message_for_spam(
                content="Hello!",
                user_created_at=user_created_at,
                member_joined_at=None,
                is_bot=False,
                user_id="123456789"
            )

        assert 'is_established_user' in result
        assert 'message_count_in_period' in result


class TestHandleSuspiciousMessage:
    """Tests for handle_suspicious_message function."""

    @pytest.mark.asyncio
    async def test_non_suspicious_message_not_handled(self):
        """Test that non-suspicious messages are not handled."""
        message = MagicMock()
        analysis = {'is_suspicious': False}

        result = await handle_suspicious_message(message, analysis)

        assert result is False
        message.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_suspicious_message_deleted(self):
        """Test that suspicious messages are deleted."""
        message = AsyncMock()
        message.author = MagicMock()
        message.author.name = "spammer"
        message.author.id = 12345
        message.guild = MagicMock()
        message.guild.name = "Test Server"
        message.guild.kick = AsyncMock()

        analysis = {
            'is_suspicious': True,
            'confidence': 0.8,
            'reasons': ['Test reason'],
            'recommended_action': 'kick'
        }

        with patch('anti_promo_bot.ANTI_PROMO_LOG_CHANNEL_ID', None):
            result = await handle_suspicious_message(message, analysis)

        assert result is True
        message.delete.assert_called_once()
        message.guild.kick.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

