# Links Dump Channel Feature

## Overview

This feature automatically moderates a designated "links dump" channel by deleting text-only messages and allowing only messages that contain URLs.

## Configuration

Add the channel ID to your `.env` file:

```env
LINKS_DUMP_CHANNEL_ID=your_channel_id_here
# Note: Forwarded messages from other channels are always allowed
```

To find your channel ID:
1. Enable Developer Mode in Discord settings
2. Right-click on the channel
3. Select "Copy Channel ID"

## How It Works

### Allowed Messages
- Messages containing URLs (http:// or https://) are allowed to remain
- Bot messages are ignored
- Commands are processed normally
- Forwarded messages from other channels are always allowed

### Deleted Messages
- Text-only messages (no URLs) are automatically deleted after 1 minute
- A warning message is sent explaining the channel rules
- Both the original message and warning are deleted after 1 minute

### Example Behavior

✅ **Allowed**: "Check out this cool article: https://example.com"
✅ **Allowed**: "https://github.com/user/repo - great project!"
✅ **Allowed**: forward of a message
❌ **Deleted**: "What do you think about this?"
❌ **Deleted**: "Thanks for sharing!"

### Warning Message

When a text-only message is posted, the bot responds with:
> @username We only allow sharing of links in this channel. If you want to comment on a link please put it in a thread, otherwise type your message in the appropriate channel. This message will be deleted in 1 minute.

## Features

- **Non-disruptive**: 1-minute delay before deletion allows users to see the warning
- **Thread-friendly**: Encourages discussion in threads rather than blocking it entirely
- **URL detection**: Uses robust regex pattern to detect various URL formats
- **Logging**: All actions are logged for monitoring and debugging
- **Error handling**: Graceful handling of permission issues or deleted messages

## Technical Details

- Uses the existing URL detection regex from the bot's link processing feature
- Integrates seamlessly with existing message handling pipeline
- Minimal performance impact - only processes messages in the configured channel
- No database changes required - works with existing infrastructure

## Disabling

To disable the feature, simply remove or comment out the `LINKS_DUMP_CHANNEL_ID` from your `.env` file.
