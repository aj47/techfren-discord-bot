import discord
import aiohttp
import base64
import re
from typing import Optional, List, Dict, Any
from logging_config import logger
from PIL import Image
import io

async def download_image(url: str) -> Optional[bytes]:
    """
    Download an image from a URL.
    
    Args:
        url (str): The URL of the image to download
        
    Returns:
        Optional[bytes]: The image bytes if successful, None otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"URL does not point to an image: {url} (Content-Type: {content_type})")
                        return None
                    
                    # Check file size (max 5MB for safety)
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > 5 * 1024 * 1024:
                        logger.warning(f"Image too large: {url} ({content_length} bytes)")
                        return None
                    
                    return await response.read()
                else:
                    logger.warning(f"Failed to download image: {url} (status: {response.status})")
                    return None
    except Exception as e:
        logger.error(f"Error downloading image from {url}: {str(e)}", exc_info=True)
        return None

def compress_image(image_bytes: bytes, max_size: int = 512, quality: int = 85) -> bytes:
    """
    Compress an image to reduce its size while maintaining reasonable quality.
    
    Args:
        image_bytes (bytes): Original image bytes
        max_size (int): Maximum width/height in pixels (default: 512)
        quality (int): JPEG quality 1-100 (default: 85)
        
    Returns:
        bytes: Compressed image bytes
    """
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB if necessary (for JPEG compatibility)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # Calculate new size maintaining aspect ratio
        original_width, original_height = img.size
        if original_width > max_size or original_height > max_size:
            ratio = min(max_size / original_width, max_size / original_height)
            new_size = (int(original_width * ratio), int(original_height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            logger.debug(f"Resized image from {original_width}x{original_height} to {new_size[0]}x{new_size[1]}")
        
        # Save to bytes with compression
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        compressed_bytes = output.getvalue()
        
        compression_ratio = len(compressed_bytes) / len(image_bytes) * 100
        logger.info(f"Compressed image from {len(image_bytes)} to {len(compressed_bytes)} bytes ({compression_ratio:.1f}%)")
        
        return compressed_bytes
    except Exception as e:
        logger.error(f"Error compressing image: {str(e)}", exc_info=True)
        # Return original if compression fails
        return image_bytes

def encode_image_to_base64(image_bytes: bytes) -> str:
    """
    Encode image bytes to base64 string.
    
    Args:
        image_bytes (bytes): The image bytes to encode
        
    Returns:
        str: Base64 encoded string
    """
    return base64.b64encode(image_bytes).decode('utf-8')

def get_image_mime_type(url: str) -> str:
    """
    Get the MIME type of an image from its URL extension.
    
    Args:
        url (str): The image URL
        
    Returns:
        str: The MIME type (defaults to 'image/jpeg')
    """
    from urllib.parse import urlparse
    
    # Parse URL to extract path component (strips querystrings)
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    if path.endswith('.png'):
        return 'image/png'
    elif path.endswith('.gif'):
        return 'image/gif'
    elif path.endswith('.webp'):
        return 'image/webp'
    elif path.endswith('.bmp'):
        return 'image/bmp'
    elif path.endswith('.tiff') or path.endswith('.tif'):
        return 'image/tiff'
    elif path.endswith('.svg'):
        return 'image/svg+xml'
    else:
        return 'image/jpeg'

async def create_image_data_url(url: str, compress: bool = True, max_size: int = 512, quality: int = 85) -> Optional[str]:
    """
    Download an image and convert it to a data URL.
    
    Args:
        url (str): The URL of the image
        compress (bool): Whether to compress the image (default: True)
        max_size (int): Maximum width/height for compression (default: 512)
        quality (int): JPEG quality for compression (default: 85)
        
    Returns:
        Optional[str]: Data URL string in format "data:image/jpeg;base64,..." or None if failed
    """
    try:
        image_bytes = await download_image(url)
        if not image_bytes:
            return None
        
        # Compress image if requested
        was_compressed = False
        if compress:
            try:
                image_bytes = compress_image(image_bytes, max_size=max_size, quality=quality)
                was_compressed = True
            except Exception as e:
                logger.warning(f"Failed to compress image from {url}: {e}")
                # Continue with uncompressed image

        base64_str = encode_image_to_base64(image_bytes)
        # Use image/jpeg only if compressed, otherwise use original MIME type
        mime_type = 'image/jpeg' if was_compressed else get_image_mime_type(url)
        
        data_url = f"data:{mime_type};base64,{base64_str}"
        logger.info(f"Created {'compressed ' if compress else ''}image data URL from {url} (size: {len(image_bytes)} bytes)")
        
        return data_url
    except Exception as e:
        logger.error(f"Error creating image data URL from {url}: {str(e)}", exc_info=True)
        return None

async def extract_images_from_message(message: discord.Message) -> List[str]:
    """
    Extract image URLs from a Discord message's attachments.
    
    Args:
        message (discord.Message): The Discord message to check
        
    Returns:
        List[str]: List of image URLs
    """
    image_urls = []
    
    if message.attachments:
        logger.debug(f"Message has {len(message.attachments)} attachment(s)")
        for attachment in message.attachments:
            logger.debug(f"Attachment: {attachment.filename}, type: {attachment.content_type}")
            # Check if attachment is an image
            if attachment.content_type and attachment.content_type.startswith('image/'):
                image_urls.append(attachment.url)
                logger.info(f"Found image attachment: {attachment.filename} ({attachment.content_type})")
    else:
        logger.debug("Message has no attachments")

    return image_urls

async def get_all_images_from_context(message_context: Optional[Dict[str, Any]]) -> List[str]:
    """
    Get all image data URLs from message context (current, referenced, and linked messages).
    
    Args:
        message_context (Optional[Dict[str, Any]]): Message context containing referenced and linked messages
        
    Returns:
        List[str]: List of image data URLs
    """
    image_data_urls = []
    
    if not message_context:
        return image_data_urls
    
    # Check referenced message (reply)
    if message_context.get('referenced_message'):
        ref_msg = message_context['referenced_message']
        image_urls = await extract_images_from_message(ref_msg)
        for url in image_urls:
            data_url = await create_image_data_url(url)
            if data_url:
                image_data_urls.append(data_url)
                logger.info("Added image from referenced message")

    # Check linked messages
    if message_context.get('linked_messages'):
        for linked_msg in message_context['linked_messages']:
            image_urls = await extract_images_from_message(linked_msg)
            for url in image_urls:
                data_url = await create_image_data_url(url)
                if data_url:
                    image_data_urls.append(data_url)
                    logger.info("Added image from linked message")

    # Check original message
    if message_context.get('original_message'):
        orig_msg = message_context['original_message']
        image_urls = await extract_images_from_message(orig_msg)
        for url in image_urls:
            data_url = await create_image_data_url(url)
            if data_url:
                image_data_urls.append(data_url)
                logger.info("Added image from original message")

    logger.info(f"Total images extracted from context: {len(image_data_urls)}")
    return image_data_urls

async def get_images_from_summary_messages(messages: List[Dict[str, Any]], max_images: int = 5, compress: bool = True) -> List[Dict[str, str]]:
    """
    Extract and process images from a list of message dictionaries (for summaries).
    Returns the last N images to keep token usage reasonable.
    
    Args:
        messages (List[Dict[str, Any]]): List of message dictionaries from database
        max_images (int): Maximum number of images to include (default: 5)
        compress (bool): Whether to compress images (default: True)
        
    Returns:
        List[Dict[str, str]]: List of dicts with 'data_url', 'author', 'timestamp'
    """
    image_data = []

    # Regex pattern to match image URLs in message content
    # Matches common image extensions and Discord CDN URLs
    image_url_pattern = re.compile(
        r'https?://(?:cdn\.discordapp\.com|media\.discordapp\.net|[^\s]+?)(?:/[^\s]*)?\.(?:jpg|jpeg|png|gif|webp|bmp)(?:\?[^\s]*)?',
        re.IGNORECASE
    )

    # Process messages in reverse to get most recent images first
    for msg in reversed(messages):
        if len(image_data) >= max_images:
            break

        # Extract message content
        content = msg.get('content', '')
        if not content:
            continue

        # Find all image URLs in the message content
        image_urls = image_url_pattern.findall(content)

        if not image_urls:
            continue

        # Get metadata from message
        author = msg.get('author_name', 'Unknown')
        timestamp = msg.get('created_at', '')

        # Process each image URL found in this message
        for url in image_urls:
            if len(image_data) >= max_images:
                break

            try:
                # Download the image
                image_bytes = await download_image(url)
                if not image_bytes:
                    logger.warning(f"Failed to download image from {url}")
                    continue

                # Optionally compress the image
                was_compressed = False
                if compress:
                    try:
                        image_bytes = compress_image(image_bytes)
                        was_compressed = True
                    except Exception as e:
                        logger.warning(f"Failed to compress image from {url}: {e}")
                        # Continue with uncompressed image

                # Convert to base64 data URL
                base64_data = base64.b64encode(image_bytes).decode('utf-8')
                # Use image/jpeg only if compressed, otherwise use original MIME type
                mime_type = 'image/jpeg' if was_compressed else get_image_mime_type(url)
                data_url = f"data:{mime_type};base64,{base64_data}"

                # Add to results
                image_data.append({
                    'data_url': data_url,
                    'author': author,
                    'timestamp': str(timestamp)
                })
                logger.info(f"Processed image from {author} at {timestamp}")

            except Exception as e:
                logger.error(f"Error processing image from {url}: {e}", exc_info=True)
                continue

    logger.info(f"Extracted {len(image_data)} images from summary messages (max: {max_images})")
    return image_data
