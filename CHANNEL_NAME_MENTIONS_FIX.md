# Channel Name Mentions in LLM Responses

## Issue
LLM responses were not mentioning #channel names when referring to channel-specific content or context, making responses less contextually aware and harder to understand which channel is being discussed.

## Root Cause
The LLM had no information about which channel the conversation was happening in. The `message_context` passed to `call_llm_api()` only contained:
- Thread conversation history
- Referenced messages (replies)
- Linked messages

But **no channel name or ID** was included, so the LLM couldn't reference the channel even when it would be relevant.

## Solution

### 1. ✅ Added Channel Information to Message Context

Updated `_get_bot_command_context()` in **command_handler.py**:
```python
# Initialize message_context if None
if message_context is None:
    message_context = {}

# Add channel information to context
channel = message.channel
if hasattr(channel, "parent") and channel.parent is not None:
    # We're in a thread, use parent channel name
    message_context["channel_name"] = channel.parent.name
    message_context["channel_id"] = str(channel.parent.id)
elif hasattr(channel, "name"):
    # Regular channel
    message_context["channel_name"] = channel.name
    message_context["channel_id"] = str(channel.id)
```

**Handles two cases:**
- **Threads**: Uses the parent channel name (since threads belong to channels)
- **Regular channels**: Uses the channel name directly

Also updated `_get_fallback_message_context()` with the same logic for consistency.

### 2. ✅ Injected Channel Context into LLM Prompt

Updated `_prepare_user_content_with_context()` in **llm_handler.py**:
```python
# Add channel context if available
if message_context.get("channel_name"):
    channel_name = message_context["channel_name"]
    context_parts.append(
        f"**Current Channel:** #{channel_name}"
    )
    logger.debug(f"Added channel context to LLM prompt: #{channel_name}")
```

This adds a clear indicator at the top of the context showing which channel the conversation is in.

### 3. ✅ Updated System Prompts

Modified both system prompts in **llm_handler.py** to instruct the LLM about channel awareness:

**Regular System Prompt:**
```
CHANNEL AWARENESS:
If you see "Current Channel: #channel-name" in the context:
- Reference the channel when discussing its content or activity
- Use the format: #channel-name when mentioning channels
- Be contextually aware of which channel the conversation is in

FORMATTING:
- Use Discord markdown effectively
- Highlight usernames with backticks: `username`
- Reference channels with hashtag: #channel-name  <-- NEW
- Include relevant links and references
```

**Chart Analysis System Prompt:**
```
CHANNEL AWARENESS:
If you see "Current Channel: #channel-name" in the context:
- Reference the channel when presenting data about it
- Use the format: #channel-name when mentioning channels
- Include channel context in your analysis summaries
```

## Example Before & After

### Before (No Channel Context)
```
User in #general: @bot how many messages today?
Bot: There were 42 messages in the past 24 hours with 8 active users.
```

### After (With Channel Context)
```
User in #general: @bot how many messages today?

Context sent to LLM:
**Current Channel:** #general
**User's Question/Request:**
how many messages today?

Bot: There were 42 messages in #general in the past 24 hours with 8 active users.
```

## Implementation Details

### Where Channel Context is Added
1. **Bot mention commands** (`handle_bot_command`) - via `_get_bot_command_context()`
2. **Fallback handlers** (`_handle_bot_command_fallback`) - via `_get_fallback_message_context()`
3. **Thread responses** - inherits parent channel name automatically

### What Gets Logged
```python
logger.debug(f"Added channel context to LLM prompt: #{channel_name}")
```

Check logs to verify channel context is being added to prompts.

### Edge Cases Handled
- **DM channels**: No channel name (handled gracefully with `hasattr` checks)
- **Threads**: Uses parent channel name (threads don't have their own "category")
- **Missing context**: Initializes empty dict if `message_context` is None

## Testing

To verify the fix is working:

1. **Check logs** for the debug message:
   ```bash
   tail -f bot.log | grep "Added channel context"
   ```

2. **Test with bot mention**:
   ```
   @bot what's happening in this channel?
   ```
   Response should mention the channel by name with # formatting.

3. **Test in different channels**:
   Verify the bot references the correct channel name in each case.

## Benefits

1. ✅ **Better context awareness** - LLM knows which channel it's responding in
2. ✅ **Clearer responses** - Users understand which channel is being referenced
3. ✅ **Consistent formatting** - Uses Discord's #channel-name convention
4. ✅ **Thread support** - Works correctly in both channels and threads
5. ✅ **Improved UX** - More natural, contextually aware conversation

## Future Enhancements

- Add server/guild name to context for multi-server bots
- Include channel description or topic in context
- Add category name for better organizational context
- Support channel mentions in slash commands (`/sum-day`, etc.)
