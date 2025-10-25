"""
Image analysis handler using Perplexity Sonar vision API.
Handles image processing and analysis for Discord message attachments.
"""

import io
import json
import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List

from logging_config import logger
import config

from openai import AsyncOpenAI

async def analyze_image_url(image_url: str, user_query: str = "Analyze this image") -> Optional[Dict[str, Any]]:
    """
    Analyze an image from its URL using Perplexity Sonar vision API.
    
    Args:
        image_url (str): URL of the image to analyze
        user_query (str): Query for what to analyze about the image
        
    Returns:
        Optional[Dict[str, Any]]: Analysis result or None if failed
    """
    try:
        logger.info(f"Analyzing image from URL: {image_url}")
        
        # Initialize OpenAI client with Perplexity configuration
        client = AsyncOpenAI(
            api_key=config.perplexity,
            base_url=config.perplexity_base_url
        )
        
        # Create the message with the image
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_query
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ]
        
        # Call Perplexity API with vision capabilities
        response = await client.chat.completions.create(
            model="sonar-pro",  # Use the vision-capable model
            messages=messages,
            max_tokens=1000,
            temperature=0.1
        )
        
        analysis_text = response.choices[0].message.content
        
        result = {
            'analysis': analysis_text,
            'image_url': image_url,
            'query': user_query,
            'model': 'sonar-pro'
        }
        
        logger.info(f"Successfully analyzed image: {image_url}")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing image from URL {image_url}: {str(e)}", exc_info=True)
        return None

async def download_image_as_base64(image_url: str) -> Optional[str]:
    """
    Download an image and convert it to base64 format.
    
    Args:
        image_url (str): URL of the image to download
        
    Returns:
        Optional[str]: Base64 encoded image or None if failed
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    
                    # Detect content type
                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"URL does not contain an image: {image_url} (content-type: {content_type})")
                        return None
                    
                    import base64
                    base64_image = base64.b64encode(image_data).decode('utf-8')
                    
                    # Create data URI
                    data_uri = f"data:{content_type};base64,{base64_image}"
                    return data_uri
                else:
                    logger.error(f"Failed to download image from {image_url}: HTTP {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error downloading image from {image_url}: {str(e)}", exc_info=True)
        return None

async def analyze_image_with_base64(image_url: str, user_query: str = "Analyze this image") -> Optional[Dict[str, Any]]:
    """
    Download image, convert to base64, and analyze using Perplexity Sonar vision API.
    
    Args:
        image_url (str): URL of the image to analyze
        user_query (str): Query for what to analyze about the image
        
    Returns:
        Optional[Dict[str, Any]]: Analysis result or None if failed
    """
    try:
        # Download and convert image to base64
        data_uri = await download_image_as_base64(image_url)
        if not data_uri:
            return None
        
        logger.info(f"Analyzing image with base64 from URL: {image_url}")
        
        # Initialize OpenAI client with Perplexity configuration
        client = AsyncOpenAI(
            api_key=config.perplexity,
            base_url=config.perplexity_base_url
        )
        
        # Create the message with the base64 image
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_query
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_uri
                        }
                    }
                ]
            }
        ]
        
        # Call Perplexity API with vision capabilities
        response = await client.chat.completions.create(
            model="sonar-pro",  # Use the vision-capable model
            messages=messages,
            max_tokens=1000,
            temperature=0.1
        )
        
        analysis_text = response.choices[0].message.content
        
        result = {
            'analysis': analysis_text,
            'image_url': image_url,
            'query': user_query,
            'model': 'sonar-pro'
        }
        
        logger.info(f"Successfully analyzed image with base64: {image_url}")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing image with base64 from {image_url}: {str(e)}", exc_info=True)
        return None

async def analyze_message_attachments(message) -> Optional[str]:
    """
    Analyze image attachments in a Discord message.
    
    Args:
        message: Discord message object
        
    Returns:
        Optional[str]: JSON string of analysis results or None if no images found
    """
    try:
        if not message.attachments:
            return None
        
        image_analyses = []
        
        for attachment in message.attachments:
            # Check if the attachment is an image
            if attachment.content_type and attachment.content_type.startswith('image/'):
                logger.info(f"Analyzing image attachment: {attachment.filename}")
                
                # Try URL analysis first
                result = await analyze_image_url(
                    attachment.url, 
                    "Analyze this image and provide a detailed description including main objects, text, colors, and overall scene."
                )
                
                # If URL analysis fails, try base64 analysis
                if not result:
                    result = await analyze_image_with_base64(
                        attachment.url,
                        "Analyze this image and provide a detailed description including main objects, text, colors, and overall scene."
                    )
                
                if result:
                    image_analyses.append({
                        'filename': attachment.filename,
                        'url': attachment.url,
                        'analysis': result['analysis']
                    })
        
        if image_analyses:
            return json.dumps(image_analyses)
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error analyzing message attachments: {str(e)}", exc_info=True)
        return None

async def process_and_update_message_with_image_analysis(message_id: str, message) -> bool:
    """
    Process image attachments in a message and update the database with analysis results.
    
    Args:
        message_id (str): Discord message ID
        message: Discord message object
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Analyze image attachments
        image_analysis = await analyze_message_attachments(message)
        
        if image_analysis:
            # Update the database with the analysis results
            from database import update_message_with_image_analysis
            success = await update_message_with_image_analysis(message_id, image_analysis)
            
            if success:
                logger.info(f"Successfully updated message {message_id} with image analysis")
            else:
                logger.warning(f"Failed to update message {message_id} with image analysis")
                
            return success
        else:
            logger.debug(f"No image attachments found in message {message_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error processing image analysis for message {message_id}: {str(e)}", exc_info=True)
        return False
