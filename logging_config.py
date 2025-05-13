import logging
import os
from datetime import datetime

def setup_logging():
    """Sets up logging for the bot."""
    log_directory = "logs"
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)

    # Create a unique log file name with timestamp
    log_filename = f"{log_directory}/bot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger('discord_bot')
    return logger

# Initialize logger when this module is imported
logger = setup_logging()
