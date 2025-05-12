# TechFren Discord Bot

A simple Discord bot built with discord.py.

## Features

- Processes `/bot <query>` commands and responds with AI-generated answers using OpenRouter API
- Summarizes channel conversations with `/sum-day` command to get a summary of the day's messages
- Automatically generates daily summaries for all active channels at a scheduled time
- Stores summaries in a dedicated database table and optionally posts them to a reports channel
- Automatically cleans up old message records after summarization to manage database size
- Automatically splits long messages into multiple parts to handle Discord's 2000 character limit
- Rate limiting to prevent abuse (10 seconds between requests, max 6 requests per minute)
- `/bot` command only responds in the #bot-talk channel
- `/sum-day` command works in any channel
- Stores all messages in a libSQL database for logging and analysis

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
5. Create a `config.py` file (you can copy `config.sample.py`). This file is primarily for the Discord bot token and other bot-specific configurations. API keys for external services are now managed in `keys.json`.
   ```python
   # Required settings
   token = "YOUR_DISCORD_BOT_TOKEN"

   # Optional settings for bot behavior
   llm_model = "x-ai/grok-3-mini-beta"  # Default model to use for OpenRouter

   # Rate limiting settings for bot commands (distinct from API rate limits)
   rate_limit_seconds = 10  # Time between allowed requests per user for bot commands
   max_requests_per_minute = 6  # Maximum requests per user per minute for bot commands

   # Automated summarization settings
   summary_hour = 0  # Hour of the day to run summarization (UTC, 0-23)
   summary_minute = 0  # Minute of the hour to run summarization (0-59)
   reports_channel_id = "CHANNEL_ID"  # Optional: Channel to post daily summaries
   ```
6. Create a `keys.json` file with your API keys as described in the "API Key Management" section.
7. Initialize the database. The `init_database()` function in `database.py` will be called when the bot starts, creating tables if they don't exist. For a fresh setup, ensure your libSQL instance is running and accessible, and the `DB_FILE` path in `database.py` (e.g., `data/discord_messages.turso`) is appropriate for your setup. You might need to manually create the `data` directory or adjust the path.
8. Run the bot:
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

- `/bot <query>`: Sends your query to an AI model via OpenRouter and returns the response

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

## Database Management

The bot uses a libSQL database (transitioned from SQLite) to store messages, summaries, and scraped link information. The database schema is defined by the SQL statements in `setup.sql`.

**Important: If you make changes to the database schema (e.g., in `database.py` by adding new tables or altering existing ones), you MUST update the `setup.sql` file accordingly.**

This ensures that anyone setting up the bot from scratch will have the correct database structure.

To initialize or reset the database according to `setup.sql`, you would typically run the SQL commands within that file against your libSQL database instance. The `init_database()` function in `database.py` attempts to create tables if they don't exist, but `setup.sql` serves as the canonical reference for the full schema.

## API Key Management

API keys for services like OpenRouter and Firecrawl are managed in the `keys.json` file. This file should be structured as follows:

```json
{
    "openrouter_api_keys": [
        "YOUR_OPENROUTER_API_KEY_1",
        "YOUR_OPENROUTER_API_KEY_2"
    ],
    "firecrawl_api_keys": [
        "YOUR_FIRECRAWL_API_KEY_1",
        "YOUR_FIRECRAWL_API_KEY_2"
    ]
}
```

The bot implements an API key rotator. If a rate limit error is encountered with the current key for a service, it will automatically switch to the next available key in the list for that service. Ensure you provide valid keys in `keys.json`.

## Firecrawl Integration

When a message contains a URL, the bot will attempt to:
1. Check if the URL has been previously scraped and stored in the `scraped_links` table.
2. Use the Firecrawl API to scrape the content of the URL.
3. If the URL is new, a new entry is created in the database with the scraped content and metadata.
4. If the URL already exists, the existing entry's content is appended with the newly scraped information, and its metadata is updated.
5. The Firecrawl API key is also subject to rotation in case of rate limits.

## Database

The bot uses a libSQL database located in the `data/` directory with the following tables:

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
- Kept the `/bot` command restricted to the #bot-talk channel
- Updated documentation to reflect these changes

### 2023-05-20
- Removed the `$hello` command feature
- Simplified command handling in the bot

### 2023-05-15
- Fixed issue where bot responses to `/bot` commands were not being stored in the database
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
