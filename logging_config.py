import logging
import os
import sys
from datetime import datetime

def setup_logging():
    """Sets up logging for the bot with proper Unicode support."""
    log_directory = "logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    # Create a unique log file name with timestamp
    log_filename = f"{log_directory}/bot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    # Create handlers with proper encoding
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    
    # For console handler, handle encoding issues on Windows
    if sys.platform.startswith('win'):
        # On Windows, try to use UTF-8 for console output
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.stream.reconfigure(encoding='utf-8')
        except (AttributeError, OSError):
            # Fallback: create a custom handler that handles encoding errors gracefully
            class SafeStreamHandler(logging.StreamHandler):
                def emit(self, record):
                    try:
                        super().emit(record)
                    except UnicodeEncodeError:
                        # Replace problematic characters and try again
                        msg = self.format(record)
                        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                        print(safe_msg)
            console_handler = SafeStreamHandler(sys.stdout)
    else:
        # On Unix-like systems, UTF-8 is usually the default
        console_handler = logging.StreamHandler()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            file_handler,
            console_handler
        ]
    )
    logger = logging.getLogger('discord_bot')
    return logger

# Initialize logger when this module is imported
logger = setup_logging()
