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
# PERPLEXITY_API_KEY=your_perplexity_api_key
# APIFY_API_TOKEN=your_apify_api_token (optional)
# LLM_MODEL=sonar
# RATE_LIMIT_SECONDS=10
# MAX_REQUESTS_PER_MINUTE=6
# SUMMARY_HOUR=0
# SUMMARY_MINUTE=0
# REPORTS_CHANNEL_ID=your_channel_id
# GENERAL_CHANNEL_ID=your_general_channel_id
#
# ============================================================
# LEGACY CONFIG (for reference only - not recommended)
# ============================================================

# Discord Bot Token (required)
# Environment variable: DISCORD_BOT_TOKEN
token = "YOUR_DISCORD_BOT_TOKEN"

# Perplexity API Key (required)
# Environment variable: PERPLEXITY_API_KEY
perplexity = "YOUR_PERPLEXITY_API_KEY"

# LLM Model Configuration (optional)
# Environment variable: LLM_MODEL
llm_model = "sonar"

# Rate Limiting Configuration (optional)
# Environment variables: RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE
rate_limit_seconds = 10
max_requests_per_minute = 6

# Apify API Token (optional for x.com/twitter.com link scraping)
# If not set, Crawl4AI will be used (no API key needed)
# Environment variable: APIFY_API_TOKEN
apify_api_token = "YOUR_APIFY_API_TOKEN"

# Daily Summary Configuration (optional)
# Environment variables: SUMMARY_HOUR, SUMMARY_MINUTE, REPORTS_CHANNEL_ID, SUMMARY_CHANNEL_IDS, GENERAL_CHANNEL_ID
summary_hour = 0
summary_minute = 0
reports_channel_id = "YOUR_CHANNEL_ID"  # For channel summaries
general_channel_id = "YOUR_GENERAL_CHANNEL_ID"  # For daily point awards
summary_channel_ids = ["YOUR_CHANNEL_ID_1", "YOUR_CHANNEL_ID_2"]  # Optional: restrict summaries to specific channels
