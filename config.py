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

# OpenRouter API Key (optional - required only for AI features)
# Environment variable: OPENROUTER_API_KEY
# To disable AI features, comment out the OPENROUTER_API_KEY line in your .env file
openrouter = os.getenv('OPENROUTER_API_KEY')

# Check if AI features should be enabled
ai_features_enabled = bool(openrouter and openrouter.strip() and openrouter != "YOUR_OPENROUTER_API_KEY")

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

# Links Channel Configuration (optional)
# Environment variables: LINKS_CHANNEL_ID, LINKS_CHANNEL_DELETE_DELAY, LINKS_CLEANUP_ON_STARTUP, LINKS_CLEANUP_MAX_AGE_HOURS
# Channel ID for the #links dump channel where only links are allowed
links_channel_id = os.getenv('LINKS_CHANNEL_ID')
# Time in seconds before deleting enforcement messages (default: 300 = 5 minutes)
links_channel_delete_delay = int(os.getenv('LINKS_CHANNEL_DELETE_DELAY', '300'))
# Whether to clean up orphaned messages on bot startup (default: True)
links_cleanup_on_startup = os.getenv('LINKS_CLEANUP_ON_STARTUP', 'true').lower() == 'true'
# Maximum age in hours for messages to be considered for cleanup (default: 24 hours)
links_cleanup_max_age_hours = int(os.getenv('LINKS_CLEANUP_MAX_AGE_HOURS', '24'))

# Links Channel Short Responses Configuration (optional)
# Environment variable: LINKS_ALLOWED_SHORT_RESPONSES
# Comma-separated list of short responses allowed in the links channel
# These are non-intrusive responses that won't disrupt the purpose of a links-only channel
default_short_responses = (
    'thanks,thank you,ty,thx,nice,cool,good,great,awesome,'
    'interesting,helpful,useful,wow,nice find,good find,solid,'
    'love it,like it,this,+1,👍,👏,🔥,💯,❤️,♥️,'
    'yep,yes,yeah,yup,nope,no,nah,maybe,possibly,'
    'lol,haha,hehe,omg,damn,shit,fuck,based,cringe,'
    'facts,true,real,fr,frfr,bet,word,same,mood,'
    'this is it,exactly,agree,disagree,idk,not sure,'
    'hmm,interesting take,hot take,bad take,good take'
)
links_allowed_short_responses_str = os.getenv('LINKS_ALLOWED_SHORT_RESPONSES', default_short_responses)
# Convert to set for efficient lookup
links_allowed_short_responses = set(response.strip().lower() for response in links_allowed_short_responses_str.split(',') if response.strip())

# Summary Command Limits
# Maximum hours that can be requested in summary commands (7 days)
MAX_SUMMARY_HOURS = 168
# Performance threshold for large summaries (24 hours)
LARGE_SUMMARY_THRESHOLD = 24

# Firecrawl Command Configuration (optional)
# Environment variable: FIRECRAWL_ALLOWED_USERS
# Comma-separated list of Discord user IDs allowed to use !firecrawl command
# Default: 200272755520700416
firecrawl_allowed_users = os.getenv('FIRECRAWL_ALLOWED_USERS', '200272755520700416').split(',')

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
    'no_messages_found': "No messages found in this channel for the past {hours} hours.",
    'firecrawl_permission_denied': "You don't have permission to use the !firecrawl command.",
    'firecrawl_invalid_url': "Please provide a valid URL. Usage: `!firecrawl <url>`",
    'firecrawl_missing_url': "Please provide a URL to scrape. Usage: `!firecrawl <url>`",
    'firecrawl_error': "Sorry, an error occurred while scraping the URL. Please try again later."
}
