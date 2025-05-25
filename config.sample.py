# Discord bot configuration (LEGACY - Use .env file instead)
# ============================================================
#
# IMPORTANT: This configuration method is deprecated.
# Please use environment variables or .env file instead.
#
# New setup instructions:
# 1. Copy .env.sample to .env
# 2. Edit .env with your actual tokens and keys
# 3. The bot will automatically load from environment variables
#
# Environment variable names:
# DISCORD_BOT_TOKEN=your_discord_bot_token
# OPENROUTER_API_KEY=your_openrouter_api_key
# FIRECRAWL_API_KEY=your_firecrawl_api_key
# APIFY_API_TOKEN=your_apify_api_token
# LLM_MODEL=x-ai/grok-3-mini-beta
# RATE_LIMIT_SECONDS=10
# MAX_REQUESTS_PER_MINUTE=6
# SUMMARY_HOUR=0
# SUMMARY_MINUTE=0
# REPORTS_CHANNEL_ID=your_channel_id
#
# ============================================================
# LEGACY CONFIG (for reference only - not recommended)
# ============================================================

# Discord Bot Token (required)
# Environment variable: DISCORD_BOT_TOKEN
token = "YOUR_DISCORD_BOT_TOKEN"

# OpenRouter API Key (required)
# Environment variable: OPENROUTER_API_KEY
openrouter = "YOUR_OPENROUTER_API_KEY"

# LLM Model Configuration (optional)
# Environment variable: LLM_MODEL
llm_model = "x-ai/grok-3-mini-beta"

# Rate Limiting Configuration (optional)
# Environment variables: RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE
rate_limit_seconds = 10
max_requests_per_minute = 6

# Firecrawl API Key (required for link scraping)
# Environment variable: FIRECRAWL_API_KEY
firecrawl_api_key = "YOUR_FIRECRAWL_API_KEY"

# Apify API Token (optional for x.com/twitter.com link scraping)
# Environment variable: APIFY_API_TOKEN
apify_api_token = "YOUR_APIFY_API_TOKEN"

# Daily Summary Configuration (optional)
# Environment variables: SUMMARY_HOUR, SUMMARY_MINUTE, REPORTS_CHANNEL_ID
summary_hour = 0
summary_minute = 0
reports_channel_id = "YOUR_CHANNEL_ID"
