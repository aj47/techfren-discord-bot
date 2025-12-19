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

# Perplexity API Key (required)
# Environment variable: PERPLEXITY_API_KEY
perplexity = os.getenv('PERPLEXITY_API_KEY')
if not perplexity:
    raise ValueError("PERPLEXITY_API_KEY environment variable is required")

# LLM Model Configuration (optional)
# Environment variable: LLM_MODEL
# Default model is "sonar" for Perplexity
llm_model = os.getenv('LLM_MODEL', 'sonar')

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

# Optional: restrict daily summaries to specific channel IDs (comma-separated list of IDs)
_summary_channel_ids_raw = os.getenv('SUMMARY_CHANNEL_IDS')
if _summary_channel_ids_raw:
    summary_channel_ids = [cid.strip() for cid in _summary_channel_ids_raw.split(',') if cid.strip()]
else:
    summary_channel_ids = None

# Links Dump Channel Configuration (optional)
# Environment variable: LINKS_DUMP_CHANNEL_ID
# Channel where only links are allowed - text messages will be auto-deleted
links_dump_channel_id = os.getenv('LINKS_DUMP_CHANNEL_ID')

# LLM API Configuration (optional)
# Environment variable: PERPLEXITY_BASE_URL
# Base URL for Perplexity API (or compatible API)
perplexity_base_url = os.getenv('PERPLEXITY_BASE_URL', 'https://api.perplexity.ai')

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

# GIF Bypass Configuration
# Points required to bypass GIF rate limits
try:
    GIF_BYPASS_POINTS_COST = int(os.getenv('GIF_BYPASS_POINTS_COST', '100'))
    if GIF_BYPASS_POINTS_COST < 1:
        GIF_BYPASS_POINTS_COST = 1  # Minimum 1 point cost
except (ValueError, TypeError):
    GIF_BYPASS_POINTS_COST = 100  # Default to 100 if invalid value

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
    # Black & White
    'black': '#0c0c0c',
    'white': '#FFFFFF',
}
