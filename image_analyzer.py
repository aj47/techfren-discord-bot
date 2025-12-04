"""
Image analysis module.

NOTE: Image analysis has been disabled after migrating from Perplexity to Exa.
Exa does not support multimodal image analysis. To re-enable image analysis,
configure a separate vision-capable LLM API (e.g., OpenAI GPT-4 Vision, Claude, etc.)
and update this module accordingly.

This module previously analyzed images from Discord attachments using Perplexity's
Sonar models to generate descriptive text that can be included in message summaries.
"""

import base64
import logging
from typing import Optional, List, Dict, Any

import aiohttp
import config

# Set up logging
logger = logging.getLogger(__name__)

# Image analysis is currently disabled after migration from Perplexity to Exa
# Exa does not support multimodal image analysis
# TODO: Re-enable with a vision-capable LLM API (OpenAI GPT-4V, Claude Vision, etc.)
image_analysis_client = None
logger.info("Image analysis is disabled - Exa does not support multimodal image analysis")

# Supported image formats
SUPPORTED_IMAGE_TYPES = {
    'image/jpeg': 'jpeg',
    'image/jpg': 'jpeg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/webp': 'webp'
}

# Maximum image size (bytes) to control cost and latency for image analysis
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB in bytes


async def download_image(url: str) -> Optional[bytes]:
    """
    Download an image from a URL.

    Args:
        url: The URL of the image to download

    Returns:
        Image bytes if successful, None if failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"Failed to download image from {url}: HTTP {response.status}")
                    return None

                # Check content length
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > MAX_IMAGE_SIZE:
                    logger.warning(f"Image too large: {content_length} bytes (max {MAX_IMAGE_SIZE})")
                    return None

                image_bytes = await response.read()

                # Double-check actual size
                if len(image_bytes) > MAX_IMAGE_SIZE:
                    logger.warning(f"Image too large: {len(image_bytes)} bytes (max {MAX_IMAGE_SIZE})")
                    return None

                return image_bytes

    except Exception as e:
        logger.exception(f"Error downloading image from {url}: {e}")
        return None


def is_supported_image(content_type: str) -> bool:
    """
    Check if the content type is a supported image format.

    Args:
        content_type: The MIME type of the attachment

    Returns:
        True if supported, False otherwise
    """
    return content_type.lower() in SUPPORTED_IMAGE_TYPES


async def analyze_image(image_bytes: bytes, content_type: str, filename: str = "image") -> Optional[str]:
    """
    Analyze an image using a multimodal LLM.

    NOTE: Image analysis is currently disabled after migrating to Exa.
    Exa does not support multimodal image analysis.

    Args:
        image_bytes: The image data as bytes
        content_type: The MIME type of the image
        filename: Optional filename for context

    Returns:
        Descriptive text about the image, or None if analysis failed/disabled
    """
    # Image analysis is disabled - Exa does not support multimodal
    if not image_analysis_client:
        logger.debug("Image analysis is disabled - skipping image analysis")
        return None

    if not is_supported_image(content_type):
        logger.warning(f"Unsupported image type: {content_type}")
        return None

    # TODO: Implement image analysis with a vision-capable LLM
    # (OpenAI GPT-4 Vision, Claude Vision, etc.)
    logger.debug(f"Image analysis not implemented: {filename}")
    return None


async def analyze_discord_attachment(attachment) -> Optional[Dict[str, Any]]:
    """
    Analyze a Discord attachment if it's an image.

    Args:
        attachment: Discord Attachment object

    Returns:
        Dictionary with analysis results, or None if not an image or analysis failed
        {
            'filename': str,
            'url': str,
            'content_type': str,
            'description': str
        }
    """
    if not attachment:
        return None

    content_type = getattr(attachment, 'content_type', None)
    if not content_type or not is_supported_image(content_type):
        logger.debug(f"Skipping non-image attachment: {attachment.filename}")
        return None

    # Download the image
    image_bytes = await download_image(attachment.url)
    if not image_bytes:
        logger.warning(f"Failed to download image: {attachment.filename}")
        return None

    # Analyze the image
    description = await analyze_image(image_bytes, content_type, attachment.filename)
    if not description:
        logger.warning(f"Failed to analyze image: {attachment.filename}")
        return None

    return {
        'filename': attachment.filename,
        'url': attachment.url,
        'content_type': content_type,
        'description': description
    }


async def analyze_message_images(message) -> List[Dict[str, Any]]:
    """
    Analyze all image attachments in a Discord message.

    Args:
        message: Discord Message object

    Returns:
        List of analysis results for each image attachment
    """
    # Skip processing if image analysis is not configured
    if image_analysis_client is None:
        return []

    if not hasattr(message, 'attachments') or not message.attachments:
        return []

    results = []
    for attachment in message.attachments:
        analysis = await analyze_discord_attachment(attachment)
        if analysis:
            results.append(analysis)

    return results


def format_image_descriptions(analyses: List[Dict[str, Any]]) -> str:
    """
    Format image analysis results into a readable string for inclusion in summaries.

    Args:
        analyses: List of image analysis dictionaries

    Returns:
        Formatted string describing all images
    """
    if not analyses:
        return ""

    if len(analyses) == 1:
        return f"\n[Image: {analyses[0]['description']}]"

    # Multiple images
    descriptions = []
    for i, analysis in enumerate(analyses, 1):
        descriptions.append(f"  {i}. {analysis['description']}")

    return "\n[Images:\n" + "\n".join(descriptions) + "\n]"
