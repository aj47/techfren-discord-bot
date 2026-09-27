"""
Discord bot configuration using environment variables and .env file support.

This module loads configuration from environment variables with .env file taking precedence.
The .env file values override system environment variables to ensure consistent configuration.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
# Use override=True to prioritize .env file over system environment variables
load_dotenv(override=True)

# Discord Bot Token (required)
# Environment variable: DISCORD_BOT_TOKEN
token = os.getenv('DISCORD_BOT_TOKEN')
if not token:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is required")

# =============================================================================
# PRIMARY API CONFIGURATION (Exa + OpenRouter)
# =============================================================================

# Exa API Key (required for Exa search - primary search provider)
# Environment variable: EXA_API_KEY
exa_api_key = os.getenv('EXA_API_KEY')
if not exa_api_key:
    raise ValueError("EXA_API_KEY environment variable is required")

# Exa API Base URL
# Environment variable: EXA_BASE_URL
exa_base_url = os.getenv('EXA_BASE_URL', 'https://api.exa.ai')

# OpenRouter API Key (required for primary LLM provider)
# Environment variable: OPENROUTER_API_KEY
openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
if not openrouter_api_key:
    raise ValueError("OPENROUTER_API_KEY environment variable is required")

# OpenRouter OpenAI-compatible API Base URL
# Environment variable: OPENROUTER_BASE_URL
openrouter_base_url = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')

# LLM Model Configuration
# Environment variable: LLM_MODEL
llm_model = os.getenv('LLM_MODEL', 'deepseek/deepseek-v4-flash')

# Vision Model Configuration (used for Discord image attachment analysis)
# Runs through the same OpenRouter credentials as the primary LLM.
# Environment variable: VISION_MODEL
vision_model = os.getenv('VISION_MODEL', 'deepseek/deepseek-v4-flash-vision-exp')

# Environment variable: ENABLE_IMAGE_ANALYSIS
# Set to false to skip analyzing image attachments (saves on vision model usage)
enable_image_analysis = os.getenv('ENABLE_IMAGE_ANALYSIS', 'true').strip().lower() in ('1', 'true', 'yes', 'on')

# Rate Limiting Configuration (optional)
# Environment variables: RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE
# Default values: 10 seconds cooldown, 6 requests per minute
rate_limit_seconds = int(os.getenv('RATE_LIMIT_SECONDS', '10'))
max_requests_per_minute = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '6'))

# Firecrawl API Key (required for link scraping)
# Environment variable: FIRECRAWL_API_KEY
firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
if not firecrawl_api_key:
    raise ValueError("FIRECRAWL_API_KEY environment variable is required")

# Firecrawl Timeout Configuration (optional)
# Environment variable: FIRECRAWL_TIMEOUT_MS
# Maximum duration in milliseconds before aborting a scrape request
# Default: 900000ms (15 minutes) - maximum practical value
firecrawl_timeout_ms = int(os.getenv('FIRECRAWL_TIMEOUT_MS', '900000'))

# Apify API Token (optional, for x.com/twitter.com link scraping)
# Environment variable: APIFY_API_TOKEN
# If not provided, Twitter/X.com links will be processed using Firecrawl
apify_api_token = os.getenv('APIFY_API_TOKEN')


# Daily Summary Configuration (optional)
# Environment variables: SUMMARY_HOUR, SUMMARY_MINUTE, REPORTS_CHANNEL_ID, SUMMARY_CHANNEL_IDS, GENERAL_CHANNEL_ID
# Default time: 00:00 UTC
summary_hour = int(os.getenv('SUMMARY_HOUR', '0'))
summary_minute = int(os.getenv('SUMMARY_MINUTE', '0'))
reports_channel_id = os.getenv('REPORTS_CHANNEL_ID')
general_channel_id = os.getenv('GENERAL_CHANNEL_ID')

# Optional: restrict per-channel daily summaries to specific channel IDs (comma-separated list of IDs).
# The daily summary posted in GENERAL_CHANNEL_ID still uses all active channels as a server-wide digest.
_summary_channel_ids_raw = os.getenv('SUMMARY_CHANNEL_IDS')
if _summary_channel_ids_raw:
    summary_channel_ids = [cid.strip() for cid in _summary_channel_ids_raw.split(',') if cid.strip()]
else:
    summary_channel_ids = None

# Links Dump Channel Configuration (optional)
# Environment variable: LINKS_DUMP_CHANNEL_ID
# Channel where only links are allowed - text messages will be auto-deleted
links_dump_channel_id = os.getenv('LINKS_DUMP_CHANNEL_ID')

# X/Twitter Link Rewriting Configuration (optional)
# Environment variables: X_LINK_REWRITE_MODE, X_LINK_REWRITE_DOMAIN,
#                        X_LINK_REWRITE_LANGUAGE, X_LINK_REWRITE_MAX_LINKS,
#                        X_LINK_SUPPRESS_ORIGINAL_EMBED, X_LINK_REPOST_MAX_ATTACHMENTS
#
# When someone posts an x.com/twitter.com link, the bot serves the same link on an
# embed-friendly mirror (fixupx.com by default). The author's stored message row
# (and therefore their point credit) is keyed to them in every mode.
#
# Modes:
#   repost - post the author's full message under the bot with the links fixed
#            ("<name> posted: ..."), then delete the original (default).
#            Needs Manage Messages; falls back to thread mode when the message
#            can't be reproduced faithfully.
#   thread - create a thread on the original message and post the fixed link there
#   reply  - reply to the original message in-channel with the fixed link
#   off    - disable the feature
_x_link_rewrite_mode_raw = os.getenv('X_LINK_REWRITE_MODE', 'repost').strip().lower()
X_LINK_REWRITE_MODE = _x_link_rewrite_mode_raw if _x_link_rewrite_mode_raw in ('repost', 'thread', 'reply', 'off') else 'repost'

# Maximum number of attachments re-uploaded with a repost. A message carrying more
# than this is left alone (repost falls back to thread mode) rather than losing files.
try:
    X_LINK_REPOST_MAX_ATTACHMENTS = int(os.getenv('X_LINK_REPOST_MAX_ATTACHMENTS', '10'))
    if X_LINK_REPOST_MAX_ATTACHMENTS < 0:
        X_LINK_REPOST_MAX_ATTACHMENTS = 0
except (ValueError, TypeError):
    X_LINK_REPOST_MAX_ATTACHMENTS = 10

# Mirror domain used for the rewritten links (e.g. fixupx.com, fxtwitter.com, vxtwitter.com)
X_LINK_REWRITE_DOMAIN = os.getenv('X_LINK_REWRITE_DOMAIN', 'fixupx.com').strip() or 'fixupx.com'

# Language the mirror renders tweets in, appended as the last path segment
# (https://fixupx.com/user/status/123/en). Set to an empty string to keep the
# poster's original language.
X_LINK_REWRITE_LANGUAGE = os.getenv('X_LINK_REWRITE_LANGUAGE', 'en').strip()

# Maximum number of links rewritten per message (keeps the bot reply short)
try:
    X_LINK_REWRITE_MAX_LINKS = int(os.getenv('X_LINK_REWRITE_MAX_LINKS', '5'))
    if X_LINK_REWRITE_MAX_LINKS < 1:
        X_LINK_REWRITE_MAX_LINKS = 1
except (ValueError, TypeError):
    X_LINK_REWRITE_MAX_LINKS = 5

# Seconds to wait before creating the thread for a fixed link.
# Creating a thread the instant the message arrives races Discord's own message
# processing and renders a glitched/empty thread, so give it a moment to settle.
# Set to 0 to disable the delay.
try:
    X_LINK_REWRITE_THREAD_DELAY_SECONDS = float(os.getenv('X_LINK_REWRITE_THREAD_DELAY_SECONDS', '2'))
    if X_LINK_REWRITE_THREAD_DELAY_SECONDS < 0:
        X_LINK_REWRITE_THREAD_DELAY_SECONDS = 0.0
except (ValueError, TypeError):
    X_LINK_REWRITE_THREAD_DELAY_SECONDS = 2.0

# Suppress the original message's (broken) embed after posting the fixed one.
# Only applies to thread/reply mode - a repost deletes the original outright.
# Requires the Manage Messages permission; the original text is left untouched.
X_LINK_SUPPRESS_ORIGINAL_EMBED = os.getenv('X_LINK_SUPPRESS_ORIGINAL_EMBED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

# HTTP Headers Configuration (optional)
# Environment variables: HTTP_REFERER, X_TITLE
# Used in LLM API requests for tracking/identification
http_referer = os.getenv('HTTP_REFERER', 'https://techfren.net')
x_title = os.getenv('X_TITLE', 'TechFren Discord Bot')

# Summary Command Limits
# Maximum hours that can be requested in summary commands (7 days)
MAX_SUMMARY_HOURS = 168
# Performance threshold for large summaries (24 hours)
LARGE_SUMMARY_THRESHOLD = 24

# Error Messages
ERROR_MESSAGES = {
    'invalid_hours_range': f"Number of hours must be between 1 and {MAX_SUMMARY_HOURS} (7 days).",
    'invalid_hours_format': "Please provide a valid number of hours. Usage: `/sum-hr <number>` (e.g., `/sum-hr 10`)",
    'processing_error': "Sorry, an error occurred while processing your request. Please try again later.",
    'summary_error': "Sorry, an error occurred while generating the summary. Please try again later.",
    'large_summary_warning': "⚠️ Large summary requested ({hours} hours). This may take longer to process.",
    'no_query': "Please provide a query after mentioning the bot.",
    'rate_limit_cooldown': "Please wait {wait_time:.1f} seconds before making another request.",
    'rate_limit_exceeded': "You've reached the maximum number of requests per minute. Please try again in {wait_time:.1f} seconds.",
    'database_unavailable': "Sorry, a critical error occurred (database unavailable). Please try again later.",
    'database_error': "Sorry, a database connection error occurred. Please try again later.",
    'no_messages_found': "No messages found in this channel for the past {hours} hours."
}

# Role Color Configuration
# Points cost per day to maintain a custom role color
try:
    ROLE_COLOR_POINTS_PER_DAY = int(os.getenv('ROLE_COLOR_POINTS_PER_DAY', '1'))
    if ROLE_COLOR_POINTS_PER_DAY < 1:
        ROLE_COLOR_POINTS_PER_DAY = 1  # Minimum 1 point per day
except (ValueError, TypeError):
    ROLE_COLOR_POINTS_PER_DAY = 1  # Default to 1 if invalid value

# Role names/keywords eligible for one free color change per cooldown window
# Comma-separated list, matched case-insensitively against Discord role names
_free_role_keywords_raw = os.getenv('ROLE_COLOR_FREE_CHANGE_ROLE_KEYWORDS', 'legend,mvp')
ROLE_COLOR_FREE_CHANGE_ROLE_KEYWORDS = tuple(
    keyword.strip().lower()
    for keyword in _free_role_keywords_raw.split(',')
    if keyword.strip()
)

# Role names/keywords exempt from daily color-role point charges.
# Defaults to the same special roles that get free color changes.
_daily_charge_exempt_role_keywords_raw = os.getenv(
    'ROLE_COLOR_DAILY_CHARGE_EXEMPT_ROLE_KEYWORDS',
    _free_role_keywords_raw
)
ROLE_COLOR_DAILY_CHARGE_EXEMPT_ROLE_KEYWORDS = tuple(
    keyword.strip().lower()
    for keyword in _daily_charge_exempt_role_keywords_raw.split(',')
    if keyword.strip()
)

# Cooldown in days for free role color changes
try:
    ROLE_COLOR_FREE_CHANGE_COOLDOWN_DAYS = int(os.getenv('ROLE_COLOR_FREE_CHANGE_COOLDOWN_DAYS', '7'))
    if ROLE_COLOR_FREE_CHANGE_COOLDOWN_DAYS < 1:
        ROLE_COLOR_FREE_CHANGE_COOLDOWN_DAYS = 7
except (ValueError, TypeError):
    ROLE_COLOR_FREE_CHANGE_COOLDOWN_DAYS = 7

# GIF Bypass Configuration
# Points required to bypass GIF rate limits
try:
    GIF_BYPASS_POINTS_COST = int(os.getenv('GIF_BYPASS_POINTS_COST', '100'))
    if GIF_BYPASS_POINTS_COST < 1:
        GIF_BYPASS_POINTS_COST = 1  # Minimum 1 point cost
except (ValueError, TypeError):
    GIF_BYPASS_POINTS_COST = 100  # Default to 100 if invalid value

# Frenbot Access Configuration
# Points charged per block of frenbot (Hermes agent) access sold by /redeem-frenbot
try:
    FRENBOT_ACCESS_COST = int(os.getenv('FRENBOT_ACCESS_COST', '25'))
    if FRENBOT_ACCESS_COST < 1:
        FRENBOT_ACCESS_COST = 1  # Minimum 1 point cost
except (ValueError, TypeError):
    FRENBOT_ACCESS_COST = 25  # Default to 25 if invalid value

# Hours of access granted per redemption
try:
    FRENBOT_ACCESS_DURATION_HOURS = int(os.getenv('FRENBOT_ACCESS_DURATION_HOURS', '1'))
    if FRENBOT_ACCESS_DURATION_HOURS < 1:
        FRENBOT_ACCESS_DURATION_HOURS = 1  # Minimum 1 hour
except (ValueError, TypeError):
    FRENBOT_ACCESS_DURATION_HOURS = 1  # Default to 1 if invalid value

# Name of the Discord role that gates frenbot access
FRENBOT_ACCESS_ROLE_NAME = os.getenv('FRENBOT_ACCESS_ROLE_NAME', 'frenbot-access').strip() or 'frenbot-access'

# Maximum hours of access a user may hold at once (stacking cap). 0 disables the cap.
try:
    FRENBOT_ACCESS_MAX_HOURS = int(os.getenv('FRENBOT_ACCESS_MAX_HOURS', '24'))
    if FRENBOT_ACCESS_MAX_HOURS < 0:
        FRENBOT_ACCESS_MAX_HOURS = 0  # Treat negative as "no cap"
except (ValueError, TypeError):
    FRENBOT_ACCESS_MAX_HOURS = 24  # Default to 24 if invalid value

# Available colors for role customization
# Format: {color_name: hex_value}
# Each color has a light and dark variant
AVAILABLE_ROLE_COLORS = {
    # Reds
    'red': '#FF0000',
    'red-light': '#FF6B6B',
    'red-dark': '#8B0000',
    # Oranges
    'orange': '#FF8C00',
    'orange-light': '#FFB347',
    'orange-dark': '#CC5500',
    # Yellows
    'yellow': '#FFD700',
    'yellow-light': '#FFEC8B',
    'yellow-dark': '#DAA520',
    # Greens
    'green': '#00FF00',
    'green-light': '#90EE90',
    'green-dark': '#006400',
    # Blues
    'blue': '#0000FF',
    'blue-light': '#87CEEB',
    'blue-dark': '#00008B',
    # Purples
    'purple': '#800080',
    'purple-light': '#DDA0DD',
    'purple-dark': '#4B0082',
    # Pinks
    'pink': '#FF69B4',
    'pink-light': '#FFB6C1',
    'pink-dark': '#C71585',
    # Cyans
    'cyan': '#00FFFF',
    'cyan-light': '#E0FFFF',
    'cyan-dark': '#008B8B',
    # Teals
    'teal': '#008080',
    'teal-light': '#40E0D0',
    'teal-dark': '#004D4D',
    # Magentas
    'magenta': '#FF00FF',
    'magenta-light': '#FF77FF',
    'magenta-dark': '#8B008B',
    # Corals
    'coral': '#FF7F50',
    'coral-light': '#FFA07A',
    'coral-dark': '#CD5B45',
    # Golds
    'gold': '#FFD700',
    'gold-light': '#FFEC8B',
    'gold-dark': '#B8860B',
    # Grays
    'gray-dark': '#323338',
    # Black & White
    'black': '#0c0c0c',
    'white': '#FFFFFF',
}

# --- techfriendcommunity bridge (optional) ---------------------------------
# Mirrors public channels to the techfriendcommunity.com Convex backend.
bridge_enabled = os.getenv('BRIDGE_ENABLED', 'false').lower() in ('1', 'true', 'yes')
convex_ingest_url = os.getenv('CONVEX_INGEST_URL')          # e.g. https://<deployment>.convex.site
bridge_secret = os.getenv('BRIDGE_SECRET')                  # shared bearer secret
bridge_guild_id = os.getenv('BRIDGE_GUILD_ID')              # optional: only mirror this guild
bridge_exclude_channel_ids = os.getenv('BRIDGE_EXCLUDE_CHANNEL_IDS', '')  # optional: comma-separated


# --- honeypot trap ----------------------------------------------------------
# Catches spam/bot accounts that post in a designated trap channel. Only
# accounts that are neither holding a trusted role nor carrying any points
# history are ever actioned, so established members cannot be caught by it.
#
# Off by default: nothing is evaluated until HONEYPOT_ENABLED is set, and even
# then HONEYPOT_DRY_RUN still logs decisions without enforcing them.
honeypot_enabled = os.getenv('HONEYPOT_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')

# When true, hits are scored, recorded in the honeypot_hits table and reported to
# HONEYPOT_LOG_CHANNEL_ID, but no member is timed out or banned.
honeypot_dry_run = os.getenv('HONEYPOT_DRY_RUN', 'true').strip().lower() in ('1', 'true', 'yes', 'on')

HONEYPOT_ENABLED = honeypot_enabled
HONEYPOT_DRY_RUN = honeypot_dry_run

# Where honeypot decisions are reported. Optional: hits are always written to the
# database either way, this only adds the Discord embed.
HONEYPOT_LOG_CHANNEL_ID = os.getenv('HONEYPOT_LOG_CHANNEL_ID')

# Comma-separated role IDs whose holders are immune. Must be an explicit
# allow-list, not "any role above the join role": the self-assignable /color
# roles outrank the join role, so a positional rule would let a spam account
# immunise itself by picking a colour.
_honeypot_roles_raw = os.getenv('HONEYPOT_TRUSTED_ROLE_IDS', '')
HONEYPOT_TRUSTED_ROLE_IDS = [
    rid.strip() for rid in _honeypot_roles_raw.split(',') if rid.strip()
]

# Safety interlock. With this true (the default), the trap refuses to act at all
# while HONEYPOT_TRUSTED_ROLE_IDS is empty, so a half-configured deploy cannot
# degrade into "action everyone without points".
HONEYPOT_REQUIRE_TRUSTED_ROLES = os.getenv(
    'HONEYPOT_REQUIRE_TRUSTED_ROLES', 'true'
).strip().lower() in ('1', 'true', 'yes', 'on')

# Acknowledge hits in the trap channel. Off by default: replying in the channel
# tells automated spam that the channel is live.
HONEYPOT_ANNOUNCE_IN_CHANNEL = os.getenv(
    'HONEYPOT_ANNOUNCE_IN_CHANNEL', 'false'
).strip().lower() in ('1', 'true', 'yes', 'on')


def _honeypot_int(name: str, default: int) -> int:
    """Read an integer setting, falling back to the default when invalid."""
    try:
        value = int(os.getenv(name, str(default)))
        return value if value >= 0 else default
    except (ValueError, TypeError):
        return default


# Scoring thresholds. Banning requires a primary signal (a channel blast, a link
# in the trap channel, a same-day account, or identical text across channels)
# plus this many points, so circumstantial signals alone cannot ban anyone.
HONEYPOT_BAN_SCORE = _honeypot_int('HONEYPOT_BAN_SCORE', 5)
HONEYPOT_TIMEOUT_SCORE = _honeypot_int('HONEYPOT_TIMEOUT_SCORE', 2)
HONEYPOT_TIMEOUT_MINUTES = _honeypot_int('HONEYPOT_TIMEOUT_MINUTES', 60)
# Seconds of history purged on a ban; Discord caps this at 7 days.
HONEYPOT_PURGE_SECONDS = _honeypot_int('HONEYPOT_PURGE_SECONDS', 86400)

# Primary signal shapes.
HONEYPOT_BLAST_CHANNELS = _honeypot_int('HONEYPOT_BLAST_CHANNELS', 3)
HONEYPOT_BLAST_WINDOW_SECONDS = _honeypot_int('HONEYPOT_BLAST_WINDOW_SECONDS', 60)
HONEYPOT_FRESH_ACCOUNT_HOURS = _honeypot_int('HONEYPOT_FRESH_ACCOUNT_HOURS', 24)
HONEYPOT_DUPLICATE_CHANNELS = _honeypot_int('HONEYPOT_DUPLICATE_CHANNELS', 2)
HONEYPOT_DUPLICATE_WINDOW_MINUTES = _honeypot_int('HONEYPOT_DUPLICATE_WINDOW_MINUTES', 5)

# Corroborating signal shapes.
HONEYPOT_YOUNG_ACCOUNT_DAYS = _honeypot_int('HONEYPOT_YOUNG_ACCOUNT_DAYS', 30)
HONEYPOT_MENTION_SPAM_COUNT = _honeypot_int('HONEYPOT_MENTION_SPAM_COUNT', 5)

# Immunity by maturity: without it, "trusted role or any points history" covers
# only the members who have ever earned a point. The guild has thousands of quiet
# lurkers holding just the join role, so the trap would be aimed at them rather
# than at new accounts. An account this old that has been in the server this
# long counts as established regardless of roles or points.
HONEYPOT_MATURE_ACCOUNT_DAYS = _honeypot_int('HONEYPOT_MATURE_ACCOUNT_DAYS', 30)
HONEYPOT_SETTLED_JOIN_DAYS = _honeypot_int('HONEYPOT_SETTLED_JOIN_DAYS', 14)
HONEYPOT_IMMUNITY_NEEDS_MATURITY = os.getenv(
    'HONEYPOT_IMMUNITY_NEEDS_MATURITY', 'true'
).strip().lower() in ('1', 'true', 'yes', 'on')

# Never permaban on a first strike: with this on, a ban needs either this many
# independent primary signals or a previous recorded hit on the same account.
HONEYPOT_BAN_REQUIRES_REPEAT = os.getenv(
    'HONEYPOT_BAN_REQUIRES_REPEAT', 'true'
).strip().lower() in ('1', 'true', 'yes', 'on')
HONEYPOT_BAN_MIN_PRIMARY_SIGNALS = _honeypot_int('HONEYPOT_BAN_MIN_PRIMARY_SIGNALS', 2)
