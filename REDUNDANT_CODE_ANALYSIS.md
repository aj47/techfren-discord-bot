# Redundant Code Analysis

This document identifies redundant code patterns and duplicate logic found in the codebase that should be refactored to improve maintainability and reduce code duplication.

## 1. Duplicate Rate Limiting Checks

**Location**: `command_handler.py`
- Lines 25-32 in `handle_bot_command`
- Lines 62-69 in `handle_sum_day_command`
- Lines 220-227 in `handle_sum_hr_command`

**Issue**: All three command handlers use identical rate limiting logic:
```python
if not await rate_limiter.check_rate_limit(message.author.id, message.guild.id if message.guild else None):
    error_msg = "Rate limit exceeded. Please wait before sending another command."
    bot_response = await message.channel.send(error_msg)
    await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
    return
```

**Recommendation**: Create a rate limiting decorator or utility function.

## 2. Duplicate Error Handling for Message Deletion

**Location**: `command_handler.py`
- Lines 43-56 in `handle_bot_command`
- Lines 182-194 in `handle_sum_day_command`
- Lines 285-297 in `handle_sum_hr_command`

**Issue**: Identical try-catch blocks for deleting processing messages:
```python
try:
    await processing_msg.delete()
except Exception as del_e:
    logger.warning(f"Could not delete processing message: {del_e}")
```

**Recommendation**: Extract into a shared utility function `safe_delete_message()`.

## 3. Duplicate LLM Client Initialization

**Location**: `llm_handler.py`
- Lines 27-30 in `call_llm_api`
- Lines 164-167 in `call_llm_for_summary`
- Lines 233-236 in `summarize_scraped_content`

**Issue**: OpenAI client created identically in three functions:
```python
client = OpenAI(
    base_url=config.openrouter_base_url,
    api_key=config.openrouter_api_key,
)
```

**Recommendation**: Create a singleton LLM client or module-level instance.

## 4. Duplicate Database Error Logging

**Location**: `database.py`
- Lines 152, 175, 219, 297, 356, 375, 447, 529, 591, 660, 697, 748

**Issue**: Same error logging pattern repeated 12+ times:
```python
logger.error(f"Error {operation}: {str(e)}", exc_info=True)
```

**Recommendation**: Create a database error logging utility function.

## 5. Duplicate Config Validation Patterns

**Location**: Multiple files
- `llm_handler.py` lines 22-24, 158-161, 227-230
- `apify_handler.py` lines 33-35, 107-109
- `firecrawl_handler.py` lines 31-33
- `config_validator.py` lines 18-29, 27-33, 36-42

**Issue**: Repeated API key validation checks:
```python
if not hasattr(config, 'api_key') or not config.api_key:
    logger.error("API key not found in config")
    return None
```

**Recommendation**: Create shared config validation decorators or utilities.

## 6. Duplicate Bot Response Storage

**Location**: `command_handler.py`
- Lines 20, 30, 41, 48, 67, 81, 90, 146, 163, 168, 174, 179, 188, 224, 239, 248, 267, 278, 290

**Issue**: Identical `store_bot_response_db()` calls throughout:
```python
await store_bot_response_db(bot_response, client_user, message.guild, message.channel, content)
```

**Recommendation**: Create a wrapper function that combines message sending and database storage.

## 7. Duplicate Thread Creation Logic

**Location**: `command_handler.py`
- Lines 152-180 in `handle_sum_day_command` (with fallback)
- Lines 274-283 in `handle_sum_hr_command` (without fallback)

**Issue**: Similar thread creation patterns but inconsistent error handling:
```python
try:
    thread = await message.channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
    # ... send messages to thread
except discord.Forbidden as e:
    # ... fallback logic
```

**Recommendation**: Create a unified thread creation utility with consistent error handling.

## 8. Duplicate Database Connection Validation

**Location**: `command_handler.py`
- Lines 77-83 in `handle_sum_day_command`
- Lines 86-92 in `handle_sum_day_command`
- Lines 235-241 in `handle_sum_hr_command`
- Lines 244-250 in `handle_sum_hr_command`

**Issue**: Repeated database availability checks:
```python
if not database.db_connection:
    error_msg = "Database connection not available"
    bot_response = await message.channel.send(error_msg)
    await store_bot_response_db(bot_response, client_user, message.guild, message.channel, error_msg)
    return
```

**Recommendation**: Create a database availability decorator.

## 9. Duplicate URL Processing Logic

**Location**: Multiple files
- `apify_handler.py` lines 47-52, 115-120
- Similar URL validation patterns across handlers

**Issue**: Similar URL validation and formatting logic repeated across different handlers.

**Recommendation**: Create shared URL validation utilities.

## 10. Duplicate Message Processing Logic

**Location**: 
- `bot.py` lines 206-220 (command type detection)
- `llm_handler.py` lines 81-86 (filtering command messages)

**Issue**: Similar message filtering and processing logic.

**Recommendation**: Create shared message processing utilities.

## Proposed Refactoring Solutions

### 1. Create Utility Decorators
```python
# utils/decorators.py
def rate_limited(func):
    async def wrapper(message, client_user, *args, **kwargs):
        if not await rate_limiter.check_rate_limit(message.author.id, message.guild.id if message.guild else None):
            # Handle rate limit
            return
        return await func(message, client_user, *args, **kwargs)
    return wrapper

def database_required(func):
    async def wrapper(message, client_user, *args, **kwargs):
        if not database.db_connection:
            # Handle missing database
            return
        return await func(message, client_user, *args, **kwargs)
    return wrapper
```

### 2. Create Shared Utilities
```python
# utils/message_utils.py
async def safe_delete_message(message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")

async def send_and_store_response(channel, content, client_user, guild):
    response = await channel.send(content)
    await store_bot_response_db(response, client_user, guild, channel, content)
    return response

async def create_thread_with_fallback(channel, name, messages, client_user, guild):
    try:
        thread = await channel.create_thread(name=name, type=discord.ChannelType.public_thread)
        for msg in messages:
            await send_and_store_response(thread, msg, client_user, guild)
        return thread
    except discord.Forbidden:
        # Fallback to channel
        for msg in messages:
            await send_and_store_response(channel, msg, client_user, guild)
        return channel
```

### 3. Create Singleton LLM Client
```python
# utils/llm_client.py
class LLMClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = OpenAI(
                base_url=config.openrouter_base_url,
                api_key=config.openrouter_api_key,
            )
        return cls._instance
```

## Impact Analysis

**Before Refactoring:**
- ~300 lines of duplicate code across files
- Inconsistent error handling patterns
- Multiple LLM client instances
- Scattered rate limiting logic

**After Refactoring:**
- ~150 lines reduction in codebase
- Consistent error handling
- Single LLM client instance
- Centralized rate limiting and validation
- Easier maintenance and testing

## Implementation Priority

1. **High Priority**: Rate limiting decorator and LLM client singleton
2. **Medium Priority**: Message handling utilities and thread creation
3. **Low Priority**: Database logging utilities and config validation

---

*Analysis completed: 2025-05-28*