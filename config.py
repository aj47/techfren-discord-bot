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

# Firecrawl API Key (optional - required for link scraping)
# Environment variable: FIRECRAWL_API_KEY
# If not set, link scraping features will be disabled
firecrawl_api_key = os.getenv('FIRECRAWL_API_KEY')
if not firecrawl_api_key or firecrawl_api_key == 'YOUR_FIRECRAWL_API_KEY':
    import warnings
    warnings.warn("FIRECRAWL_API_KEY not configured - link scraping features will be disabled", stacklevel=2)
    firecrawl_api_key = None

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

# Links Dump Channel Configuration (optional)
# Environment variable: LINKS_DUMP_CHANNEL_ID
# Channel where only links are allowed - text messages will be auto-deleted
links_dump_channel_id = os.getenv('LINKS_DUMP_CHANNEL_ID')

# Perplexity API Configuration (optional)
# Environment variable: PERPLEXITY_BASE_URL
# Base URL for Perplexity API (OpenAI-compatible endpoint)
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
