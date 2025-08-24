# Discord Bot Debug CLI

A command-line interface for debugging and testing your Discord bot without connecting to Discord. This allows you to simulate sending messages to the bot as if they were coming from a #bot-devs channel.

## Features

- 🤖 **Full Bot Simulation**: Test all bot commands without Discord connection
- 💾 **Database Integration**: Messages are stored in the same database as the real bot
- 🔄 **Rate Limiting**: All rate limiting functionality works as expected
- 🧵 **Thread Support**: Thread creation and responses work correctly
- 🔗 **URL Processing**: URL scraping and processing functionality works if configured
- 📝 **Comprehensive Logging**: See detailed logs of bot operations
- 👤 **User Simulation**: Change your debug username on the fly

## Quick Start

1. **Install Dependencies** (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the Debug CLI**:
   ```bash
   python debug.py
   ```

3. **Start Testing**:
   ```
   [DebugUser] > @bot Hello, how are you?
   [DebugUser] > /sum-day
   [DebugUser] > /sum-hr 6
   ```

## Available Commands

### Bot Commands
- `@bot <query>` - Send a query to the bot (mention command)
  - Example: `@bot What is Python?`
- `/sum-day` - Generate daily summary of messages from past 24 hours
- `/sum-hr <hours>` - Generate summary of messages from past N hours
  - Example: `/sum-hr 6`

### CLI Controls
- `.help` - Show help message with all available commands
- `.user <name>` - Change your debug username
  - Example: `.user TestDeveloper`
- `.quit` or `.exit` - Exit the debug interface
- `Ctrl+C` - Force quit if needed

## Files Overview

### Core Files
- **`debug.py`** - Main launcher script (run this to start debugging)
- **`debug_cli.py`** - Command-line interface implementation
- **`debug_bot.py`** - Debug bot runner that initializes bot components
- **`mock_discord.py`** - Mock Discord objects that simulate Discord.py library

### How It Works

1. **Mock Objects**: The system uses mock Discord objects (`MockMessage`, `MockChannel`, `MockUser`, etc.) that provide the same interface as real Discord objects
2. **Bot Integration**: Your existing command handlers work unchanged - they receive mock objects instead of real Discord objects
3. **Database**: All messages and responses are stored in your actual bot database
4. **Logging**: Full logging shows you exactly what the bot is doing

## Example Session

```
🚀 Starting Discord Bot Debug CLI...
🔄 Initializing debug bot...
✅ Bot initialized successfully!
============================================================
🤖 Discord Bot Debug CLI
============================================================
This interface simulates sending messages to the #bot-devs channel.
You can test all bot commands here without connecting to Discord.

Available commands:
  @bot <query>     - Send a query to the bot (mention command)
  /sum-day         - Generate daily summary
  /sum-hr <hours>  - Generate summary for specified hours
  .help            - Show this help message
  .user <name>     - Change your username
  .quit or .exit   - Exit the debug CLI

Note: The bot will process your messages and respond as if you
      were in a real Discord channel.
============================================================

[DebugUser] > @bot What is the weather like?
[USER MESSAGE]: <@111111111> What is the weather like?
[BOT RESPONSE]: Processing your request, please wait...
[BOT RESPONSE]: I don't have access to real-time weather data...
[MESSAGE DELETED]: Processing your request, please wait...

[DebugUser] > /sum-day
[USER MESSAGE]: /sum-day
[BOT RESPONSE]: Generating channel summary, please wait... This may take a moment.
[THREAD CREATED]: Daily Summary
[BOT RESPONSE in Daily Summary]: Here's a summary of the past 24 hours...
[MESSAGE DELETED]: Generating channel summary, please wait... This ma...

[DebugUser] > .user TestDeveloper
✅ Username changed from 'DebugUser' to 'TestDeveloper'

[TestDeveloper] > .quit
👋 Goodbye!
🔄 Debug CLI shutting down...
```

## Benefits for Development

1. **Faster Testing**: No need to set up Discord channels or invite bots
2. **Isolated Environment**: Test without affecting real Discord servers
3. **Debug Logging**: See detailed logs of what your bot is doing
4. **Rate Limit Testing**: Verify rate limiting works correctly
5. **Database Testing**: Ensure database operations work as expected
6. **Command Testing**: Test all bot commands quickly and easily

## Troubleshooting

### Dependencies Missing
If you see dependency errors, install requirements:
```bash
pip install -r requirements.txt
```

### LLM API Errors
If you see 404 errors from the LLM API, check your model configuration in `config.py` or `.env` file. The debug CLI will still work for testing command flow even if the LLM calls fail.

### Database Issues
Ensure your bot's database is properly configured and accessible. The debug CLI uses the same database as your real bot.

## Integration with Existing Bot

The debug CLI integrates seamlessly with your existing bot code:

- ✅ Uses your existing command handlers
- ✅ Uses your existing database
- ✅ Uses your existing configuration
- ✅ Uses your existing rate limiting
- ✅ Uses your existing logging

No changes to your bot code are required!
