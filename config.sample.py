# Discord bot configuration
# Copy this file to config.py and replace with your actual tokens
# ---------------------------------------------------------------

# Discord Bot Token (required)
# Get this from the Discord Developer Portal: https://discord.com/developers/applications
token = "YOUR_DISCORD_BOT_TOKEN"

# OpenRouter API Key (required)
# Get this from OpenRouter: https://openrouter.ai/
openrouter = "YOUR_OPENROUTER_API_KEY"

# LLM Model Configuration (optional)
# Default model is "x-ai/grok-3-mini-beta"
# You can change this to any model supported by OpenRouter
llm_model = "x-ai/grok-3-mini-beta"

# Rate Limiting Configuration (optional)
# Uncomment and modify these values to change the default rate limiting
# rate_limit_seconds = 10  # Time between allowed requests per user
# max_requests_per_minute = 6  # Maximum requests per user per minute

# Reports Channel Configuration (optional)
# ID of the channel where summary reports will be posted
# Leave commented out to disable automatic report posting
# reports_channel_id = 123456789012345678  # Replace with your channel ID

# Daily Summarization Schedule (optional)
# The time when daily channel summarization will run (in UTC)
# Default is midnight UTC (00:00)
# summary_hour = 0    # Hour in 24-hour format (0-23)
# summary_minute = 0  # Minute (0-59)
