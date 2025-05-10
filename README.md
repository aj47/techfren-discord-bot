# TechFren Discord Bot

A simple Discord bot built with discord.py.

## Features

- Processes `/bot <query>` commands and responds with AI-generated answers using OpenRouter API
- Summarizes channel conversations with `/sum-day` command to get a summary of the day's messages
- Automatically splits long messages into multiple parts to handle Discord's 2000 character limit
- Rate limiting to prevent abuse (10 seconds between requests, max 6 requests per minute)
- `/bot` command only responds in the #bot-talk channel
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
   token = "YOUR_DISCORD_BOT_TOKEN"
   openrouter = "YOUR_OPENROUTER_API_KEY"
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

- `/bot <query>`: Sends your query to an AI model via OpenRouter and returns the response

### Channel Summarization

- `/sum-day`: Summarizes all messages in the current channel for the current day
  - Works in any channel (not restricted to #bot-talk)
  - The bot retrieves all messages from the channel (including bot responses) except command messages
  - Sends them to the AI model for summarization
  - Returns a formatted summary with the main topics and key points discussed

## Database

The bot stores all messages in a SQLite database located in the `data/` directory, including:
- User messages
- Bot responses to commands
- Error messages
- Rate limit notifications

This comprehensive message storage allows for:

- Complete conversation history tracking
- User activity analysis
- Command usage statistics
- Channel summarization functionality
- Debugging and troubleshooting

The database is initialized when the bot starts up and is used throughout the application to store and retrieve messages. Each message is stored with metadata including author information, timestamps, and whether it's a command or bot response.

### Database Utilities

You can use the `db_utils.py` script to interact with the database:

```bash
# List recent messages
python db_utils.py list -n 20

# Show message statistics
python db_utils.py stats
```

### Troubleshooting

If you encounter database-related errors:

1. Make sure the `data/` directory exists and is writable
2. Check that the database is properly initialized in the `on_ready` event
3. Avoid importing the database module multiple times in different scopes
4. Check the logs for detailed error messages

## Changelog

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
