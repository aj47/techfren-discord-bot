# Migration Guide: Config.py to Environment Variables

This guide helps you migrate from the old `config.py` file to the new environment variable configuration.

## Why the Change?

- **Security**: Environment variables are more secure and don't risk accidentally committing secrets to version control
- **Deployment**: Easier to deploy across different environments (development, staging, production)
- **Best Practices**: Follows the [12-factor app methodology](https://12factor.net/config)

## Migration Steps

### Step 1: Install the new dependency

```bash
pip install python-dotenv
# or if using uv:
uv pip install python-dotenv
```

### Step 2: Create your .env file

1. Copy the sample environment file:
   ```bash
   cp .env.sample .env
   ```

2. If you have an existing `config.py`, copy the values to your `.env` file:

   **Old config.py:**
   ```python
   token = "your_discord_token"
   openrouter = "your_openrouter_key"
   firecrawl_api_key = "your_firecrawl_key"
   apify_api_token = "your_apify_token"
   llm_model = "x-ai/grok-3-mini-beta"
   rate_limit_seconds = 10
   max_requests_per_minute = 6
   ```

   **New .env file:**
   ```bash
   DISCORD_BOT_TOKEN=your_discord_token
   OPENROUTER_API_KEY=your_openrouter_key
   FIRECRAWL_API_KEY=your_firecrawl_key
   APIFY_API_TOKEN=your_apify_token
   LLM_MODEL=x-ai/grok-3-mini-beta
   RATE_LIMIT_SECONDS=10
   MAX_REQUESTS_PER_MINUTE=6
   ```

### Step 3: Remove your old config.py

```bash
rm config.py  # The bot now uses the new config.py that loads from environment variables
```

### Step 4: Test the configuration

```bash
python -c "import config; print('Configuration loaded successfully')"
```

## Environment Variable Reference

| Old config.py variable | New environment variable | Required | Default |
|------------------------|--------------------------|----------|---------|
| `token` | `DISCORD_BOT_TOKEN` | Yes | - |
| `openrouter` | `OPENROUTER_API_KEY` | Yes | - |
| `firecrawl_api_key` | `FIRECRAWL_API_KEY` | Yes | - |
| `apify_api_token` | `APIFY_API_TOKEN` | No | - |
| `llm_model` | `LLM_MODEL` | No | `x-ai/grok-3-mini-beta` |
| `rate_limit_seconds` | `RATE_LIMIT_SECONDS` | No | `10` |
| `max_requests_per_minute` | `MAX_REQUESTS_PER_MINUTE` | No | `6` |
| `summary_hour` | `SUMMARY_HOUR` | No | `0` |
| `summary_minute` | `SUMMARY_MINUTE` | No | `0` |
| `reports_channel_id` | `REPORTS_CHANNEL_ID` | No | - |

## Deployment Options

### Option 1: .env file (Development)
- Create a `.env` file in your project root
- Add your environment variables
- The bot will automatically load them

### Option 2: System environment variables (Production)
```bash
export DISCORD_BOT_TOKEN="your_token"
export OPENROUTER_API_KEY="your_key"
# ... etc
```

### Option 3: Docker environment variables
```yaml
# docker-compose.yml
environment:
  - DISCORD_BOT_TOKEN=your_token
  - OPENROUTER_API_KEY=your_key
```

## Security Notes

- Never commit `.env` files to version control
- The `.env` file is already added to `.gitignore`
- Environment variables take precedence over `.env` file values
- Use different `.env` files for different environments if needed

## Troubleshooting

### "ModuleNotFoundError: No module named 'dotenv'"
Install the python-dotenv package:
```bash
pip install python-dotenv
```

### "Bot token is missing or empty"
Make sure your `.env` file contains:
```bash
DISCORD_BOT_TOKEN=your_actual_token_here
```

### Configuration not loading
1. Check that your `.env` file is in the same directory as the bot
2. Verify there are no spaces around the `=` in your `.env` file
3. Make sure your `.env` file doesn't have a `.txt` extension

## Need Help?

If you encounter any issues during migration, please check:
1. The `.env.sample` file for the correct format
2. The bot logs for specific error messages
3. The README.md for updated setup instructions
