"""
YouTube handler module for the Discord bot.
Handles extracting transcripts and summarizing YouTube videos.
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi

# Set up logging
logger = logging.getLogger("discord_bot.youtube_handler")


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract the video ID from a YouTube URL.

    Args:
        url (str): The YouTube URL

    Returns:
        Optional[str]: The video ID or None if extraction failed
    """
    try:
        # Pattern to match YouTube video IDs in various URL formats
        patterns = [
            r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([A-Za-z0-9_-]{11})",  # noqa: E501
            r"youtube\.com/watch\?.*v=([A-Za-z0-9_-]{11})",
            r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        logger.debug(f"No video ID found in URL: {url}")
        return None

    except Exception as e:
        logger.error(
            f"Error extracting video ID from URL {url}: {str(e)}", exc_info=True
        )
        return None


async def get_video_transcript(video_id: str) -> Optional[str]:
    """
    Get the transcript for a YouTube video.

    Args:
        video_id (str): The YouTube video ID

    Returns:
        Optional[str]: The transcript text or None if unavailable
    """
    try:
        logger.info(f"Getting transcript for video ID: {video_id}")

        # Use asyncio.to_thread to run the blocking call in a thread
        transcript_list = await asyncio.to_thread(
            YouTubeTranscriptApi.get_transcript,
            video_id,
            languages=["en", "en-US", "en-GB"],
        )

        # Format the transcript as plain text
        # Each entry in transcript_list is a dict with 'text', 'start', 'duration' keys
        transcript_text = " ".join([entry["text"] for entry in transcript_list])

        logger.info(f"Successfully retrieved transcript for video ID: {video_id}")
        return transcript_text

    except Exception as e:
        logger.warning(f"Could not get transcript for video ID {video_id}: {str(e)}")
        return None


async def get_video_metadata(video_id: str) -> Dict[str, Any]:
    """
    Get basic metadata for a YouTube video.
    Note: This is a placeholder for potential YouTube Data API integration.

    Args:
        video_id (str): The YouTube video ID

    Returns:
        Dict[str, Any]: Basic metadata (currently just video_id and constructed URL)
    """
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": None,  # Would require YouTube Data API
        "channel": None,  # Would require YouTube Data API
        "duration": None,  # Would require YouTube Data API
    }


async def scrape_youtube_content(url: str) -> Optional[Dict[str, Any]]:
    """
    Scrape content from a YouTube URL by extracting the transcript.

    Args:
        url (str): The YouTube URL to scrape

    Returns:
        Optional[Dict[str, Any]]: A dictionary containing the scraped content or None if scraping failed  # noqa: E501
    """
    try:
        logger.info(f"Scraping YouTube URL: {url}")

        # Extract video ID from URL
        video_id = extract_video_id(url)
        if not video_id:
            logger.error(f"Could not extract video ID from URL: {url}")
            return None

        # Get video transcript
        transcript = await get_video_transcript(video_id)
        if not transcript:
            logger.warning(f"Could not get transcript for video: {url}")
            # Return a structured error response instead of None
            metadata = await get_video_metadata(video_id)
            error_markdown = format_transcript_unavailable_message(metadata)
            return {
                "markdown": error_markdown,
                "raw_data": {
                    "transcript": None,
                    "metadata": metadata,
                    "error": "transcript_unavailable",
                },
            }

        # Get basic metadata
        metadata = await get_video_metadata(video_id)

        # Limit transcript length to prevent token overload (approximately 7000
        # characters)
        if len(transcript) > 7000:
            transcript = transcript[:7000] + "... [transcript truncated]"

        # Format as markdown
        markdown_content = format_as_markdown(transcript, metadata)

        scraped_content = {"transcript": transcript, "metadata": metadata}

        return {"markdown": markdown_content, "raw_data": scraped_content}

    except Exception as e:
        logger.error(f"Error scraping YouTube URL {url}: {str(e)}", exc_info=True)
        return None


def format_as_markdown(transcript: str, metadata: Dict[str, Any]) -> str:
    """
    Format the YouTube transcript as markdown.

    Args:
        transcript (str): The video transcript
        metadata (Dict[str, Any]): Video metadata

    Returns:
        str: The formatted markdown content
    """
    try:
        markdown = "# YouTube Video Transcript\n\n"
        markdown += f"**Video URL:** {metadata['url']}\n"
        markdown += f"**Video ID:** {metadata['video_id']}\n\n"

        if metadata.get("title"):
            markdown += f"**Title:** {metadata['title']}\n"
        if metadata.get("channel"):
            markdown += f"**Channel:** {metadata['channel']}\n"
        if metadata.get("duration"):
            markdown += f"**Duration:** {metadata['duration']}\n"

        markdown += "\n## Transcript\n\n"
        markdown += transcript

        return markdown

    except Exception as e:
        logger.error(
            f"Error formatting YouTube content as markdown: {str(e)}", exc_info=True
        )
        return "Error formatting YouTube content."


def format_transcript_unavailable_message(metadata: Dict[str, Any]) -> str:
    """
    Format a message when transcript is unavailable.

    Args:
        metadata (Dict[str, Any]): Video metadata

    Returns:
        str: Formatted message about transcript unavailability
    """
    try:
        markdown = "# YouTube Video - Transcript Unavailable\n\n"
        markdown += f"**Video URL:** {metadata['url']}\n"
        markdown += f"**Video ID:** {metadata['video_id']}\n\n"

        if metadata.get("title"):
            markdown += f"**Title:** {metadata['title']}\n"
        if metadata.get("channel"):
            markdown += f"**Channel:** {metadata['channel']}\n"
        if metadata.get("duration"):
            markdown += f"**Duration:** {metadata['duration']}\n"

        markdown += "\n## Transcript Status\n\n"
        markdown += "❌ **Transcript not available**\n\n"
        markdown += "This video does not have auto-generated captions or manual transcripts available. "  # noqa: E501
        markdown += "The video may be:\n"
        markdown += "- Too new (transcripts are still being generated)\n"
        markdown += "- In a language not supported by auto-captioning\n"
        markdown += "- Restricted by the channel owner\n"
        markdown += "- A live stream or premiere\n\n"
        markdown += "Please check the video directly for more information."

        return markdown

    except Exception as e:
        logger.error(
            f"Error formatting transcript unavailable message: {str(e)}", exc_info=True
        )
        return "YouTube video transcript is not available."


async def is_youtube_url(url: str) -> bool:
    """
    Check if a URL is from YouTube.

    Args:
        url (str): The URL to check

    Returns:
        bool: True if the URL is from YouTube, False otherwise
    """
    # Pattern to match YouTube domains and URL formats
    youtube_patterns = [
        r"(?:^https?://(?:www\.)?youtube\.com)",
        r"(?:^https?://(?:www\.)?youtu\.be)",
        r"(?:^https?://(?:www\.)?m\.youtube\.com)",
        r"(?://(?:www\.)?youtube\.com)",
        r"(?://(?:www\.)?youtu\.be)",
        r"(?://(?:www\.)?m\.youtube\.com)",
    ]

    for pattern in youtube_patterns:
        if re.search(pattern, url):
            return True

    return False
