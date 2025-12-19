"""
Anti-promo bot module for detecting and handling spam/promo bots.

This module provides functionality to detect promotional bots that join Discord servers
and send spam/advertising messages. It uses a combination of heuristics to identify
suspicious behavior and can automatically delete messages and kick/ban offenders.
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict, Any
import os

from dotenv import load_dotenv
from logging_config import logger

# Load environment variables from .env file before reading configuration.
# Explicit environment variables take precedence over .env file contents,
# which is the expected behavior for production deployments.
load_dotenv()

# Valid actions for anti-promo moderation
VALID_ANTI_PROMO_ACTIONS = {'delete', 'kick', 'ban'}

# Default configuration values
DEFAULT_MIN_ACCOUNT_AGE_DAYS = 7
DEFAULT_NEW_MEMBER_WINDOW_MINUTES = 30


def _parse_int_env(name: str, default: int) -> int:
    """Parse an integer environment variable with fallback to default on error."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"[ANTI-PROMO] Invalid integer value for {name}: '{value}', using default: {default}")
        return default


# Configuration from environment variables
ANTI_PROMO_ENABLED = os.getenv('ANTI_PROMO_ENABLED', 'true').lower() == 'true'
ANTI_PROMO_MIN_ACCOUNT_AGE_DAYS = _parse_int_env('ANTI_PROMO_MIN_ACCOUNT_AGE_DAYS', DEFAULT_MIN_ACCOUNT_AGE_DAYS)
ANTI_PROMO_NEW_MEMBER_WINDOW_MINUTES = _parse_int_env('ANTI_PROMO_NEW_MEMBER_WINDOW_MINUTES', DEFAULT_NEW_MEMBER_WINDOW_MINUTES)

# Normalize and validate ANTI_PROMO_ACTION
_anti_promo_action_raw = os.getenv('ANTI_PROMO_ACTION', 'kick').lower().strip()
if _anti_promo_action_raw not in VALID_ANTI_PROMO_ACTIONS:
    logger.warning(f"[ANTI-PROMO] Invalid ANTI_PROMO_ACTION '{_anti_promo_action_raw}', defaulting to 'kick'")
    ANTI_PROMO_ACTION = 'kick'
else:
    ANTI_PROMO_ACTION = _anti_promo_action_raw

ANTI_PROMO_LOG_CHANNEL_ID = os.getenv('ANTI_PROMO_LOG_CHANNEL_ID')

# Common promo bot patterns
PROMO_PATTERNS = [
    # Discord invite links
    r'discord\.gg/\S+',
    r'discord\.com/invite/\S+',
    r'discordapp\.com/invite/\S+',
    # Crypto/NFT spam
    r'(?:free|airdrop|claim)\s*(?:nft|crypto|token|eth|btc|coin)',
    r'(?:nft|crypto|token)\s*(?:airdrop|giveaway|free)',
    # Direct messages solicitation
    r'(?:dm|message|contact)\s*(?:me|us)\s*(?:for|to)\s*(?:free|more|details)',
    # Suspicious URLs with promo keywords
    r'https?://\S*(?:promo|airdrop|giveaway|claim|free-?mint)\S*',
    # Telegram links (often used by scammers)
    r't\.me/\S+',
    # Common scam phrases
    r'limited\s*time\s*(?:offer|only)',
    r'(?:click|tap)\s*(?:here|link)\s*(?:to|for)\s*(?:claim|get|receive)',
    r'(?:earn|make|get)\s*\$?\d+\s*(?:daily|hourly|weekly)',
    # WhatsApp links
    r'wa\.me/\S+',
    r'chat\.whatsapp\.com/\S+',
]

# Compile patterns for efficiency
COMPILED_PROMO_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in PROMO_PATTERNS]


def is_anti_promo_enabled() -> bool:
    """Check if anti-promo bot feature is enabled."""
    return ANTI_PROMO_ENABLED


def check_account_age(user_created_at: datetime) -> Tuple[bool, int]:
    """
    Check if a user's account is too new (suspicious).
    
    Args:
        user_created_at: The datetime when the user's Discord account was created
        
    Returns:
        Tuple of (is_too_new, age_in_days)
    """
    now = datetime.now(timezone.utc)
    
    # Ensure user_created_at is timezone-aware
    if user_created_at.tzinfo is None:
        user_created_at = user_created_at.replace(tzinfo=timezone.utc)
    
    account_age = now - user_created_at
    age_in_days = account_age.days
    
    is_too_new = age_in_days < ANTI_PROMO_MIN_ACCOUNT_AGE_DAYS
    return is_too_new, age_in_days


def check_member_join_time(member_joined_at: Optional[datetime]) -> Tuple[bool, int]:
    """
    Check if a member joined the server very recently.
    
    Args:
        member_joined_at: The datetime when the member joined the server
        
    Returns:
        Tuple of (is_new_member, minutes_since_join)
    """
    if member_joined_at is None:
        return False, -1
    
    now = datetime.now(timezone.utc)
    
    # Ensure member_joined_at is timezone-aware
    if member_joined_at.tzinfo is None:
        member_joined_at = member_joined_at.replace(tzinfo=timezone.utc)
    
    time_since_join = now - member_joined_at
    minutes_since_join = int(time_since_join.total_seconds() / 60)
    
    is_new_member = minutes_since_join < ANTI_PROMO_NEW_MEMBER_WINDOW_MINUTES
    return is_new_member, minutes_since_join


def check_message_for_promo_patterns(content: str) -> Tuple[bool, List[str]]:
    """
    Check if a message contains promotional/spam patterns.
    
    Args:
        content: The message content to check
        
    Returns:
        Tuple of (has_promo_pattern, list of matched patterns)
    """
    matched_patterns = []
    
    for i, pattern in enumerate(COMPILED_PROMO_PATTERNS):
        if pattern.search(content):
            matched_patterns.append(PROMO_PATTERNS[i])
    
    return bool(matched_patterns), matched_patterns


def analyze_message_for_spam(
    content: str,
    user_created_at: datetime,
    member_joined_at: Optional[datetime],
    is_bot: bool = False
) -> Dict[str, Any]:
    """
    Analyze a message for potential spam/promo bot activity.
    
    Args:
        content: The message content
        user_created_at: When the user's Discord account was created
        member_joined_at: When the member joined the server
        is_bot: Whether the user is a bot account
        
    Returns:
        Dictionary with analysis results
    """
    result = {
        'is_suspicious': False,
        'confidence': 0.0,
        'reasons': [],
        'account_age_days': 0,
        'minutes_since_join': -1,
        'matched_patterns': [],
        'recommended_action': None,
    }
    
    # Skip if user is a verified bot
    if is_bot:
        return result
    
    confidence_score = 0.0
    
    # Check for promo patterns
    has_promo, patterns = check_message_for_promo_patterns(content)
    if has_promo:
        result['matched_patterns'] = patterns
        result['reasons'].append(f"Message contains promotional patterns: {patterns}")
        confidence_score += 0.5

    # Check account age
    is_new_account, age_days = check_account_age(user_created_at)
    result['account_age_days'] = age_days
    if is_new_account:
        result['reasons'].append(f"Account is only {age_days} days old (threshold: {ANTI_PROMO_MIN_ACCOUNT_AGE_DAYS} days)")
        confidence_score += 0.3

    # Check member join time
    is_new_member, minutes_since = check_member_join_time(member_joined_at)
    result['minutes_since_join'] = minutes_since
    if is_new_member:
        result['reasons'].append(f"Member joined only {minutes_since} minutes ago (threshold: {ANTI_PROMO_NEW_MEMBER_WINDOW_MINUTES} minutes)")
        confidence_score += 0.2

    # Determine if suspicious based on combined factors
    # High confidence: promo patterns + new account OR promo patterns + just joined
    # Medium confidence: promo patterns alone (might be legitimate shares)
    result['confidence'] = min(confidence_score, 1.0)

    if has_promo and (is_new_account or is_new_member):
        result['is_suspicious'] = True
        result['recommended_action'] = ANTI_PROMO_ACTION
    elif confidence_score >= 0.7:
        result['is_suspicious'] = True
        result['recommended_action'] = 'delete'  # Be more conservative

    return result


async def handle_suspicious_message(
    message,  # discord.Message
    analysis: Dict[str, Any],
    bot_user=None
) -> bool:
    """
    Handle a message that has been flagged as suspicious.

    Args:
        message: The Discord message object
        analysis: The analysis result from analyze_message_for_spam
        bot_user: The bot's user object (optional, for logging)

    Returns:
        True if action was taken, False otherwise
    """
    if not analysis['is_suspicious']:
        return False

    action = analysis['recommended_action']
    user = message.author
    guild = message.guild

    logger.warning(
        f"[ANTI-PROMO] Suspicious message detected - "
        f"User: {user.name} ({user.id}) | "
        f"Guild: {guild.name if guild else 'DM'} | "
        f"Confidence: {analysis['confidence']:.0%} | "
        f"Reasons: {analysis['reasons']}"
    )

    try:
        # Try to delete the message first, but don't let failure prevent kick/ban
        try:
            await message.delete()
            logger.info(f"[ANTI-PROMO] Deleted suspicious message from {user.name} ({user.id})")
        except Exception as delete_error:
            logger.warning(f"[ANTI-PROMO] Failed to delete message from {user.name} ({user.id}): {delete_error}")

        if action == 'kick' and guild:
            await guild.kick(user, reason=f"Anti-promo bot: {', '.join(analysis['reasons'])}")
            logger.info(f"[ANTI-PROMO] Kicked user {user.name} ({user.id}) from {guild.name}")
        elif action == 'ban' and guild:
            await guild.ban(user, reason=f"Anti-promo bot: {', '.join(analysis['reasons'])}", delete_message_days=1)
            logger.info(f"[ANTI-PROMO] Banned user {user.name} ({user.id}) from {guild.name}")

        # Log to anti-promo log channel if configured
        if ANTI_PROMO_LOG_CHANNEL_ID and guild:
            await log_anti_promo_action(guild, user, analysis, action)

        return True

    except Exception as e:
        logger.error(f"[ANTI-PROMO] Failed to handle suspicious message: {e}", exc_info=True)
        return False


async def log_anti_promo_action(guild, user, analysis: Dict[str, Any], action: str):
    """Log anti-promo action to a designated channel."""
    try:
        channel = guild.get_channel(int(ANTI_PROMO_LOG_CHANNEL_ID))
        if not channel:
            return

        embed_color = 0xFF0000 if action in ('kick', 'ban') else 0xFFA500

        log_message = (
            f"**🚨 Anti-Promo Action Taken**\n"
            f"**User:** {user.name} ({user.id})\n"
            f"**Action:** {action.upper()}\n"
            f"**Confidence:** {analysis['confidence']:.0%}\n"
            f"**Account Age:** {analysis['account_age_days']} days\n"
            f"**Minutes Since Join:** {analysis['minutes_since_join']}\n"
            f"**Reasons:**\n" + "\n".join(f"• {r}" for r in analysis['reasons'])
        )

        await channel.send(log_message)
    except Exception as e:
        logger.error(f"[ANTI-PROMO] Failed to log action: {e}")

