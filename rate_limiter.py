import time
import threading
from collections import defaultdict
from logging_config import logger

# Rate limiting configuration
RATE_LIMIT_SECONDS = 10  # Time between allowed requests per user
MAX_REQUESTS_PER_MINUTE = 6  # Maximum requests per user per minute
CLEANUP_INTERVAL = 3600  # Clean up old rate limit data every hour (in seconds)

# Thread safety for rate limiting
rate_limit_lock = threading.Lock()  # Lock for thread safety

# Rate limiting data structures
user_last_request = {}  # Track last request time per user
user_request_count = defaultdict(list)  # Track request timestamps for per-minute limiting
last_cleanup_time = time.time()  # Track when we last cleaned up old rate limit data

def check_rate_limit(user_id):
    """
    Check if a user has exceeded the rate limit

    Args:
        user_id (str): The Discord user ID

    Returns:
        tuple: (is_rate_limited, seconds_to_wait, reason)
    """
    global last_cleanup_time, RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE
    current_time = time.time()

    # Use lock for thread safety
    with rate_limit_lock:
        # Periodically clean up old rate limit data to prevent memory leaks
        if current_time - last_cleanup_time > CLEANUP_INTERVAL:
            cleanup_rate_limit_data(current_time)
            last_cleanup_time = current_time

        # Check cooldown between requests
        if user_id in user_last_request:
            time_since_last = current_time - user_last_request[user_id]
            if time_since_last < RATE_LIMIT_SECONDS:
                return True, RATE_LIMIT_SECONDS - time_since_last, "cooldown"

        # Check requests per minute
        minute_ago = current_time - 60
        recent_requests = [t for t in user_request_count[user_id] if t > minute_ago]

        if len(recent_requests) >= MAX_REQUESTS_PER_MINUTE:
            oldest = min(recent_requests)
            time_until_reset = oldest + 60 - current_time
            return True, time_until_reset, "max_per_minute"

        # Update tracking
        user_last_request[user_id] = current_time

        # Clean up old timestamps and add the new one (avoid duplicates)
        user_request_count[user_id] = recent_requests + [current_time]

    return False, 0, None

def cleanup_rate_limit_data(current_time):
    """
    Clean up old rate limit data to prevent memory leaks

    Args:
        current_time (float): The current time
    """
    # This function is called from within check_rate_limit which already holds the lock
    # No need to acquire the lock again

    # Remove users who haven't made a request in the last hour
    inactive_threshold = current_time - 3600

    # Clean up user_last_request
    inactive_users = [user_id for user_id, last_time in user_last_request.items()
                     if last_time < inactive_threshold]
    for user_id in inactive_users:
        del user_last_request[user_id]
        if user_id in user_request_count:
            del user_request_count[user_id]

    if inactive_users:
        logger.debug(f"Cleaned up rate limit data for {len(inactive_users)} inactive users")

def update_rate_limit_config(new_rate_limit_seconds, new_max_requests_per_minute):
    """
    Update rate limiting parameters.
    This function should be called if these values are changed in the main config.
    """
    global RATE_LIMIT_SECONDS, MAX_REQUESTS_PER_MINUTE
    with rate_limit_lock:
        RATE_LIMIT_SECONDS = new_rate_limit_seconds
        MAX_REQUESTS_PER_MINUTE = new_max_requests_per_minute
        logger.info(f"Rate limit config updated: {RATE_LIMIT_SECONDS}s cooldown, {MAX_REQUESTS_PER_MINUTE} req/min")
