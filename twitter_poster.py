"""
Twitter/X posting module for the Discord bot.
Handles posting tweets to X/Twitter using the Twitter API v2 via Tweepy.
"""

import asyncio
import logging
from typing import Optional

import config

# Set up logging
logger = logging.getLogger('discord_bot.twitter_poster')

# Twitter API client (lazy initialization)
_twitter_client = None


def _get_twitter_client():
    """Get or create the Twitter API client.
    
    Returns:
        tweepy.Client or None if credentials are not configured
    """
    global _twitter_client
    
    if _twitter_client is not None:
        return _twitter_client
    
    # Check if Twitter credentials are configured
    consumer_key = getattr(config, 'twitter_consumer_key', None)
    consumer_secret = getattr(config, 'twitter_consumer_secret', None)
    access_token = getattr(config, 'twitter_access_token', None)
    access_token_secret = getattr(config, 'twitter_access_token_secret', None)
    
    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        logger.debug("Twitter API credentials not fully configured")
        return None
    
    try:
        import tweepy
        
        _twitter_client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        logger.info("Twitter API client initialized successfully")
        return _twitter_client
    except ImportError:
        logger.error("tweepy package not installed. Install with: pip install tweepy")
        return None
    except Exception as e:
        logger.error(f"Error initializing Twitter client: {str(e)}")
        return None


def is_twitter_posting_enabled() -> bool:
    """Check if Twitter posting is enabled and configured.
    
    Returns:
        bool: True if Twitter posting is enabled and credentials are configured
    """
    # Check if auto-tweet is enabled
    auto_tweet_enabled = getattr(config, 'twitter_auto_tweet_enabled', False)
    if not auto_tweet_enabled:
        return False
    
    # Check if client can be initialized
    return _get_twitter_client() is not None


async def post_tweet(text: str) -> Optional[dict]:
    """Post a tweet to X/Twitter.
    
    Args:
        text: The tweet text (max 280 characters, will be truncated if longer)
        
    Returns:
        dict with tweet data if successful, None if failed
    """
    client = _get_twitter_client()
    if not client:
        logger.warning("Twitter client not available, cannot post tweet")
        return None
    
    # Truncate text if too long (Twitter limit is 280 characters)
    if len(text) > 280:
        # Leave room for ellipsis
        text = text[:277] + "..."
        logger.info(f"Tweet text truncated to 280 characters")
    
    try:
        # Use run_in_executor since tweepy is synchronous
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.create_tweet(text=text)
        )
        
        if response and response.data:
            tweet_id = response.data.get('id')
            logger.info(f"Successfully posted tweet with ID: {tweet_id}")
            return {
                'id': tweet_id,
                'text': response.data.get('text', text)
            }
        else:
            logger.warning("Tweet posted but no response data received")
            return None
            
    except Exception as e:
        logger.error(f"Error posting tweet: {str(e)}", exc_info=True)
        return None


async def post_tweet_thread(tweets: list[str]) -> list[dict]:
    """Post a thread of tweets to X/Twitter.
    
    Args:
        tweets: List of tweet texts to post as a thread
        
    Returns:
        List of dicts with tweet data for successfully posted tweets
    """
    if not tweets:
        return []
    
    client = _get_twitter_client()
    if not client:
        logger.warning("Twitter client not available, cannot post thread")
        return []
    
    posted_tweets = []
    reply_to_id = None
    
    for i, text in enumerate(tweets):
        # Truncate if needed
        if len(text) > 280:
            text = text[:277] + "..."
        
        try:
            loop = asyncio.get_event_loop()
            
            if reply_to_id:
                # Reply to previous tweet in thread
                response = await loop.run_in_executor(
                    None,
                    lambda t=text, r=reply_to_id: client.create_tweet(
                        text=t,
                        in_reply_to_tweet_id=r
                    )
                )
            else:
                # First tweet in thread
                response = await loop.run_in_executor(
                    None,
                    lambda t=text: client.create_tweet(text=t)
                )
            
            if response and response.data:
                tweet_id = response.data.get('id')
                posted_tweets.append({
                    'id': tweet_id,
                    'text': response.data.get('text', text)
                })
                reply_to_id = tweet_id
                logger.info(f"Posted tweet {i+1}/{len(tweets)} with ID: {tweet_id}")
            else:
                logger.warning(f"Tweet {i+1} posted but no response data")
                break
                
        except Exception as e:
            logger.error(f"Error posting tweet {i+1}: {str(e)}", exc_info=True)
            break
    
    return posted_tweets

