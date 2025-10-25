# Duplicate Issue Investigation

## Current System Prompt Flow

The bot uses **ONE** system prompt per LLM call, selected based on conditions:

```
User sends message → Bot detects command
    ↓
call_llm_api(query, context, force_charts)
    ↓
_select_system_prompt(force_charts, query, user_content)
    ↓
    IF force_charts == True:
        return _get_chart_analysis_system_prompt()
    ELSE IF _should_use_chart_system(query, user_content):
        return _get_chart_analysis_system_prompt()
    ELSE:
        return _get_regular_system_prompt()
    ↓
One LLM call with selected prompt → One response
```

**KEY POINT**: Only ONE prompt is used per message. There's no scenario where both prompts are applied to the same message.

## Duplicate Detection Already in Place

### Level 1: Message-level (bot.py)
```python
_processed_messages = set()  # Track by message.id

if message_key in _processed_messages:
    logger.warning("⚠️ DUPLICATE DETECTED: Skipping...")
    return
```

### Level 2: Command-level (command_handler.py)
```python
_processed_commands = set()  # Track by (message.id, author.id)

if command_key in _processed_commands:
    logger.warning("⚠️ DUPLICATE COMMAND: Already processing...")
    return
```

## Possible Duplicate Scenarios

### 1. Discord Auto-Thread Duplication
**Problem**: Discord sends the same message in both channel and auto-created thread
**Solution**: Already handled - only message.id is used as key (not channel info)

### 2. User Sees Two Responses
**If you're seeing**:
- Response 1: Bot explanation of how to make graphs
- Response 2: Actual chart

**Possible cause**:
- First response used regular system prompt (shouldn't happen with our detection)
- Second response used chart system prompt

**To verify**, check logs for:
```
🔵 LLM CALL: query='...' 
```
If you see TWO of these for the same message ID, we have a real duplicate.

### 3. Chart Appears Twice in Same Response
**If you're seeing**:
- One response with the same chart shown twice

**Possible cause**:
- Chart rendering happening twice in the same message
- Table duplication in LLM response

## What "Duplicates" Are You Seeing?

Please clarify which scenario you're experiencing:

**A. Two separate bot messages** in response to one user message?
```
User: @bot create a graph
Bot: [Message 1] To create a graph...
Bot: [Message 2] Here's your chart: [image]
```

**B. Same chart twice in one response**?
```
User: @bot create a graph  
Bot: [Message 1]
     | Data | Value |
     [Chart 1: Bar]
     | Data | Value |
     [Chart 2: Bar]  <-- same chart again
```

**C. Same table/data twice in response text**?
```
User: @bot create a graph
Bot: Here's the data:
     | Data | Value |
     | foo  | 10    |
     
     Here's the same data again:
     | Data | Value |
     | foo  | 10    |
```

**D. Processing logs show duplicate**?
```
Log: ✅ Message 12345 not in cache, processing
Log: ✅ Message 12345 not in cache, processing  <-- same ID twice
```

## Investigation Steps

1. **Check your logs** for the message that showed duplicates
2. **Count "🔵 LLM CALL"** entries for that message ID
3. **Look for "⚠️ DUPLICATE"** warnings
4. **Share the full log sequence** for one duplicate occurrence

## Why System Prompts Don't Need to Merge

The current design is **correct**:
- **Chart mode**: Optimized for data analysis, MUST create tables
- **Regular mode**: Optimized for conversation, AVOID tables

These are **mutually exclusive** behaviors for different use cases:
- `/chart-day` → Chart mode (force_charts=True)
- `@bot analyze data` → Chart mode (detected by keywords)
- `@bot how do webhooks work?` → Regular mode

**Merging them would**:
- Make prompts longer and more complex
- Create conflicting instructions
- Confuse the LLM about when to create tables

## Actual Problem Hypothesis

Based on your original issue, I think the "duplicate" might be:
1. You send: `@bot create a graph` with table data
2. Bot first responds with regular mode (explaining)
3. Then someone manually triggers chart mode
4. You see two different responses

**OR**:
1. Bot detects "create a graph" keyword
2. Uses chart system prompt correctly
3. LLM generates table
4. But the table appears twice in the response text itself (LLM duplication, not system issue)

## Next Steps

1. **Share exact duplicate behavior** you're seeing
2. **Share full log sequence** for one occurrence
3. **Describe**: Is it two messages or one message with duplicate content?

Then we can pinpoint the exact issue and fix it!
