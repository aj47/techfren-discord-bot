# Image Processing Feature

## Overview

The bot now supports viewing, analyzing, and understanding images shared in Discord channels. This feature is built into the LLM handler using a minimal builder pattern approach.

## How It Works

The bot can process images from three sources:

1. **Current Message**: Images attached directly to the message mentioning the bot
2. **Referenced Messages**: Images in messages you're replying to
3. **Linked Messages**: Images in Discord message links included in your message

## Usage Examples

### Analyzing an Image Directly

```
@bot what's in this image?
[Attach image]
```

The bot will download the image, encode it, and send it to the vision-capable LLM for analysis.

**Note**: When you attach media to a message, Discord may automatically create a thread. The bot detects this and replies in the existing thread instead of creating a duplicate.

### Asking About a Referenced Image

```
[Reply to a message with an image]
@bot what does this show?
```

The bot will analyze the image from the message you're replying to.

### Multiple Images

```
@bot compare these images
[Attach multiple images or reply to/link messages with images]
```

The bot can process multiple images in a single request.

## Technical Implementation

### Builder Pattern (`ImageContent`)

The `ImageContent` class uses a builder pattern for constructing multimodal LLM requests:

```python
# Example usage
image_content = ImageContent()
image_content.add_image_url("https://example.com/image.jpg")
image_content.add_image_base64(base64_data, "image/jpeg")

if image_content.has_images():
    images = image_content.build()
```

### Image Processing Flow

1. **Detection**: Command handler detects message attachments
2. **Context Creation**: Message context includes the current message
3. **Download & Encode**: Images are downloaded and converted to base64
4. **LLM Request**: Images are sent as part of the multimodal content array
5. **Response**: LLM analyzes and responds about the image content

### Key Components

- `ImageContent`: Builder class for image content
- `download_image_as_base64()`: Downloads and encodes images
- `_process_images_from_context()`: Extracts images from message context
- `_make_llm_request()`: Updated to support multimodal content

## Supported Image Formats

The bot supports all standard image formats:
- JPEG/JPG
- PNG
- GIF
- WebP
- BMP

## Limitations

- Maximum image size depends on Discord's attachment limits (8MB for non-boosted servers)
- LLM token limits apply - very high resolution images may be downscaled by the LLM provider
- Only image attachments are processed (not embeds or external links)

## Requirements

Your LLM provider must support vision/multimodal capabilities:
- ✅ OpenAI GPT-4 Vision
- ✅ Claude 3 (Opus, Sonnet, Haiku)
- ✅ Google Gemini Pro Vision
- ✅ Perplexity Sonar with vision support
- ❌ Text-only models will not work

## Thread Behavior

### Auto-Created Threads
When you attach media (images, videos, etc.) to a message in Discord, Discord may automatically create a thread for that message. The bot intelligently handles this:

- **Detects existing threads**: Checks if message is already in a thread
- **Reuses Discord's thread**: Replies in the auto-created thread instead of making a new one
- **Prevents duplicates**: Won't create a second thread if one already exists

### Log Messages
You'll see different messages depending on the situation:

```
# Message already in thread (Discord auto-created)
INFO - Message is already in thread 'general', using it for response

# Bot checking for existing threads
INFO - Message 123456 already has thread 'general' (from API), reusing it

# Bot creating new thread
INFO - Successfully created thread 'Bot Response - Username' (ID: 789) from message 123456
```

## Logging

When images are processed, you'll see logs like:

```
INFO - Successfully downloaded and encoded image from https://cdn.discordapp.com/...
INFO - Added image from current message: screenshot.png
INFO - Processed 1 image(s) from message context for LLM
INFO - Making LLM request with 1 image(s)
```

## Error Handling

- **Failed downloads**: Logged as warnings, request continues without that image
- **Non-image attachments**: Automatically filtered out
- **Invalid content types**: Skipped with warning log
- **Network errors**: Gracefully handled with timeout (10 seconds)

## Testing

Run the test suite:

```bash
pytest test_image_processing.py -v
```

This covers:
- Builder pattern functionality
- Image download scenarios
- Context processing with various message types
- Error handling
