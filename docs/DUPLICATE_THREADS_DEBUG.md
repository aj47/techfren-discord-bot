# Duplicate Threads Debug Guide

## Issue Observed

User sees TWO separate thread responses for ONE mention:
- Thread 1: "Here's your savings data visualize..."
- Thread 2: "Here's a simple bar graph you can cre..."

Both are titled "Bot Response - Dr. vova"

## What This Means

The bot is calling `handle_bot_command()` **twice** for the same message, and both calls are successfully creating threads and generating responses.

## Why Duplicate Detection Might Fail

### Current Detection Logic:
```python
# command_handler.py line 236
command_key = (message.id, message.author.id)
if command_key in _processed_commands:
    logger.warning("⚠️ DUPLICATE COMMAND: Already processing...")
    return

_processed_commands.add(command_key)
```

### Possible Causes:

#### 1. Race Condition (MOST LIKELY)
If Discord sends two `on_message` events rapidly:
```
Time 0ms:  Event 1 arrives → Check cache (not found) → Start processing
Time 5ms:  Event 2 arrives → Check cache (not found yet!) → Start processing
Time 10ms: Event 1 adds to cache
Time 15ms: Event 2 adds to cache (too late!)
```

Both events pass the duplicate check because neither has added to cache yet.

#### 2. Different Message Objects
If Discord sends the message with different attributes:
- Same message.id but different message object instances
- Could happen if message is in channel vs thread

#### 3. Cache Cleared Between Calls
If `_processed_commands` size limit is hit:
```python
if len(_processed_commands) > _PROCESSED_COMMANDS_MAX_SIZE:  # 500
    to_remove = list(_processed_commands)[:_PROCESSED_COMMANDS_MAX_SIZE // 2]
```
Unlikely unless 500+ commands processed rapidly.

## Debug Steps

### 1. Check Logs for These Patterns:

**Pattern A - Race Condition:**
```
✅ Message 123 not in cache, processing
🟢 Executing mention command - Message ID: 123
✅ Message 123 not in cache, processing  <-- SAME ID TWICE!
🟢 Executing mention command - Message ID: 123
```

**Pattern B - Duplicate Detection Working:**
```
✅ Message 123 not in cache, processing
🟢 Executing mention command - Message ID: 123
⚠️ DUPLICATE DETECTED: Skipping duplicate processing of message 123
⚠️ DUPLICATE COMMAND: Already processing/processed message 123
```

**Pattern C - Different Channels:**
```
✅ Message 123 not in cache, processing (channel: 111, cache size: 2)
🟢 Executing mention command - Message ID: 123
✅ Message 123 not in cache, processing (channel: 222, cache size: 3)
🟢 Executing mention command - Message ID: 123
```

### 2. Count LLM Calls

```
grep "🔵 LLM CALL" bot.log | grep "123" | wc -l
```

Should be **1** for normal operation, **2** if duplicate.

### 3. Check Thread Creation

```
grep "Created bot thread" bot.log | grep "Dr. vova"
```

Should show **1** thread creation, not 2.

## Potential Fixes

### Fix 1: Add Async Lock (Race Condition)
```python
import asyncio

_command_lock = asyncio.Lock()
_processed_commands = set()

async def handle_bot_command(...):
    async with _command_lock:
        command_key = (message.id, message.author.id)
        if command_key in _processed_commands:
            logger.warning("⚠️ DUPLICATE COMMAND...")
            return
        _processed_commands.add(command_key)
    
    # Continue processing...
```

### Fix 2: Early Return in on_message
Add duplicate check BEFORE calling `handle_bot_command`:
```python
# In bot.py on_message
if commands["is_mention_command"]:
    # Check if already processed at message level
    if message.id in _processed_messages:
        return
    await handle_bot_command(message, bot.user, bot)
    return
```

### Fix 3: Use Discord's Processing Flag
```python
# Mark message as being processed
if hasattr(message, '_techfren_processing'):
    logger.warning("Message already being processed")
    return
message._techfren_processing = True
```

## Testing

After applying fix:
1. Send `@bot test message` 
2. Check logs - should see only ONE "🟢 Executing mention command"
3. Check Discord - should see only ONE thread created
4. Repeat 10 times to ensure no race conditions

## Log Analysis Needed

Please provide logs showing:
1. The exact time the duplicate occurred
2. All log lines containing the message ID
3. Any warnings or errors around that time
4. Thread creation logs

This will help identify which of the three causes is happening.
