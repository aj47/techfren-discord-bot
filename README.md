# TechFren Discord Bot

A simple Discord bot built with discord.py.

## Features

- Processes queries via mentions (`@botname <query>`) and responds with AI-generated answers using OpenRouter API
- Summarizes channel conversations with `/sum-day` command to get a summary of the day's messages
- Automatically generates daily summaries for all active channels at a scheduled time
- Stores summaries in a dedicated database table and optionally posts them to a reports channel
- Automatically cleans up old message records after summarization to manage database size
- Automatically splits long messages into multiple parts to handle Discord's 2000 character limit
- Rate limiting to prevent abuse (10 seconds between requests, max 6 requests per minute)
- Mention-based queries (e.g., `@botname <query>`) allow you to interact with the bot in any channel. While originally envisaged for a dedicated `#bot-talk` channel, the current implementation allows use in all channels.
- `/sum-day` command works in any channel
- Stores all messages in a SQLite database for logging and analysis

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```
   uv venv
   ```
3. Activate the virtual environment:
   ```
   source .venv/bin/activate  # On Unix/macOS
   .venv\Scripts\activate     # On Windows
   ```
4. Install dependencies:
   ```
   uv pip install -r requirements.txt
   ```
5. Create a `config.py` file with your Discord bot token and OpenRouter API key:
   ```python
   # Required settings
   token = "YOUR_DISCORD_BOT_TOKEN"
   openrouter = "YOUR_OPENROUTER_API_KEY"

   # Optional settings
   llm_model = "x-ai/grok-3-mini-beta"  # Default model to use

   # Rate limiting settings
   rate_limit_seconds = 10  # Time between allowed requests per user
   max_requests_per_minute = 6  # Maximum requests per user per minute

   # Automated summarization settings
   summary_hour = 0  # Hour of the day to run summarization (UTC, 0-23)
   summary_minute = 0  # Minute of the hour to run summarization (0-59)
   reports_channel_id = "CHANNEL_ID"  # Optional: Channel to post daily summaries
   ```
   You can get an OpenRouter API key by signing up at [OpenRouter.ai](https://openrouter.ai/)
6. Run the bot:
   ```
   python bot.py
   ```

## Discord Developer Portal Setup

To use the message content intent, you need to enable it in the Discord Developer Portal:

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications/)
2. Select your application/bot
3. Navigate to the "Bot" tab
4. Scroll down to the "Privileged Gateway Intents" section
5. Enable the "Message Content Intent"
6. Save your changes
7. Uncomment the message_content intent in the bot.py file

## Commands

### Basic Commands

- `@botname <query>`: Sends your query to an AI model via OpenRouter and returns the response. This command works in any channel.

### Channel Summarization

- `/sum-day`: Summarizes all messages in the current channel for the current day
  - Works in any channel (not restricted to #bot-talk)
  - The bot retrieves all messages from the channel (including bot responses) except command messages
  - Sends them to the AI model for summarization
  - Returns a formatted summary with the main topics and key points discussed

### Automated Daily Summarization

The bot automatically generates summaries for all active channels once per day:

- Runs at a configurable time (default: midnight UTC)
- Summarizes messages from the past 24 hours for each active channel
- Stores summaries in a dedicated database table with metadata including:
  - Channel information
  - Message count
  - Active users
  - Date
  - Summary text
- Optionally posts summaries to a designated reports channel
- Deletes messages older than 24 hours after successful summarization to manage database size

To configure the automated summarization:

```python
# In config.py
summary_hour = 0  # Hour of the day to run summarization (UTC, 0-23)
summary_minute = 0  # Minute of the hour to run summarization (0-59)
reports_channel_id = "CHANNEL_ID"  # Optional: Channel to post daily summaries
```

## Database

The bot uses a SQLite database located in the `data/` directory with the following tables:

### Messages Table
Stores all messages processed by the bot, including:
- User messages
- Bot responses to commands
- Error messages
- Rate limit notifications

Each message is stored with metadata including author information, timestamps, and whether it's a command or bot response.

### Channel Summaries Table
Stores the daily automated summaries for each channel, including:
- Channel information (ID, name, guild)
- Date of the summary
- Summary text
- Message count
- Active users count and list
- Metadata (start/end times, summary type)

This comprehensive database structure allows for:

- Complete conversation history tracking
- User activity analysis
- Command usage statistics
- Channel summarization functionality
- Historical summary access
- Debugging and troubleshooting

The database is initialized when the bot starts up and is used throughout the application to store and retrieve messages and summaries.

### Database Utilities

You can use the `db_utils.py` script to interact with the database:

```bash
# List recent messages
python db_utils.py list -n 20

# Show message statistics
python db_utils.py stats

# List channel summaries
python db_utils.py summaries -n 10

# Filter summaries by channel name
python db_utils.py summaries -c general

# Filter summaries by date
python db_utils.py summaries -d 2023-05-30

# View a specific summary in full
python db_utils.py view-summary 1
```

### Troubleshooting

If you encounter database-related errors:

1. Make sure the `data/` directory exists and is writable
2. Check that the database is properly initialized in the `on_ready` event
3. Avoid importing the database module multiple times in different scopes
4. Check the logs for detailed error messages

## Changelog

### 2023-05-30
- Added automated daily channel summarization feature
- Created a new channel_summaries table in the database
- Implemented scheduled task to run summarization at a configurable time
- Added functionality to delete old messages after summarization
- Added optional feature to post summaries to a designated reports channel
- Updated documentation with new configuration options

### 2023-05-25
- Modified the `/sum-day` command to work in any channel (not just #bot-talk)
- Mention-based queries (`@botname <query>`) are available in all channels.
- Updated documentation to reflect these changes

### 2023-05-20
- Removed the `$hello` command feature
- Simplified command handling in the bot

### 2023-05-15
- Fixed issue where bot responses to mention-based queries (`@botname <query>`) were not being stored in the database
- Now storing all bot responses in the database, including error messages and rate limit notifications
- Modified `/sum-day` command to include bot responses in the summary
- Improved error handling and logging for database operations

### 2023-05-10
- Added message splitting functionality to handle responses that exceed Discord's 2000 character limit
- Fixed an `UnboundLocalError` in the `/sum-day` command that was causing database access issues
- Improved error handling for database operations
- Added additional database troubleshooting information to the README

## License

MIT
