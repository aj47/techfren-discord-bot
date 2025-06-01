"""
Discord bot configuration using environment variables and .env file support.

This module loads configuration from environment variables with fallback to .env file.
Environment variables take precedence over .env file values.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
# This will not override existing environment variables
load_dotenv()

# Discord Bot Token (required)
# Environment variable: DISCORD_BOT_TOKEN
token = os.getenv('DISCORD_BOT_TOKEN')
if not token:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is required")

# OpenRouter API Key (required)
# Environment variable: OPENROUTER_API_KEY
openrouter = os.getenv('OPENROUTER_API_KEY')
if not openrouter:
    raise ValueError("OPENROUTER_API_KEY environment variable is required")

# LLM Model Configuration (optional)
# Environment variable: LLM_MODEL
# Default model is "x-ai/grok-3-mini-beta"
llm_model = os.getenv('LLM_MODEL', 'x-ai/grok-3-mini-beta:online')

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

# Apify API Token (optional, for x.com/twitter.com link scraping)
# Environment variable: APIFY_API_TOKEN
# If not provided, Twitter/X.com links will be processed using Firecrawl
apify_api_token = os.getenv('APIFY_API_TOKEN')

# Daily Summary Configuration (optional)
# Environment variables: SUMMARY_HOUR, SUMMARY_MINUTE, REPORTS_CHANNEL_ID
# Default time: 00:00 UTC
summary_hour = int(os.getenv('SUMMARY_HOUR', '0'))
summary_minute = int(os.getenv('SUMMARY_MINUTE', '0'))
reports_channel_id = os.getenv('REPORTS_CHANNEL_ID')

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
