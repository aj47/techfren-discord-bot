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
llm_model = os.getenv('LLM_MODEL', 'x-ai/grok-3-mini-beta')

# Rate Limiting Configuration (optional)
# Environment variables: RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE
# Default values: 10 seconds cooldown, 6 requests per minute
rate_limit_seconds = int(os.getenv('RATE_LIMIT_SECONDS', '10'))
max_requests_per_minute = int(os.getenv('MAX_REQUESTS_PER_MINUTE', '6'))

# Firecrawl API Key (required for link scraping)
# Environment variable: FIRECRAWL_API_KEY
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
