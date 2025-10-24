"""
Test script for image analysis functionality.
This script tests the image handler module independently.
"""

import asyncio
import sys
import os
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
from logging_config import logger
from image_handler import analyze_image_url, analyze_image_with_base64, download_image_as_base64

# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_image_analysis():
    """
    Test image analysis with a sample image URL.
    """
    # Sample image URL (using a public test image)
    test_image_url = "https://picsum.photos/800/600"  # Random image service
    
    logger.info("Testing image analysis functionality...")
    
    # Test 1: Direct URL analysis
    logger.info(f"Test 1: Analyzing image via URL: {test_image_url}")
    result = await analyze_image_url(test_image_url, "Describe this image in detail.")
    
    if result:
        logger.info("✅ Test 1 passed: URL-based image analysis succeeded")
        logger.info(f"Analysis result: {result['analysis'][:100]}...")
    else:
        logger.error("❌ Test 1 failed: URL-based image analysis failed")
    
    # Test 2: Base64 analysis
    logger.info(f"Test 2: Analyzing image via base64: {test_image_url}")
    result_base64 = await analyze_image_with_base64(test_image_url, "What do you see in this image?")
    
    if result_base64:
        logger.info("✅ Test 2 passed: Base64-based image analysis succeeded")
        logger.info(f"Analysis result: {result_base64['analysis'][:100]}...")
    else:
        logger.error("❌ Test 2 failed: Base64-based image analysis failed")
    
    # Test 3: Download and convert to base64
    logger.info(f"Test 3: Converting image to base64: {test_image_url}")
    base64_data = await download_image_as_base64(test_image_url)
    
    if base64_data:
        logger.info("✅ Test 3 passed: Image conversion to base64 succeeded")
        logger.info(f"Base64 data length: {len(base64_data)} characters")
    else:
        logger.error("❌ Test 3 failed: Image conversion to base64 failed")

if __name__ == "__main__":
    try:
        # Import config to check if API key is set
        import config
        if not config.perplexity:
            logger.error("❌ Perplexity API key not found. Please check your configuration.")
            sys.exit(1)
        
        asyncio.run(test_image_analysis())
        logger.info("Image analysis tests completed.")
        
    except ImportError as e:
        logger.error(f"❌ Failed to import required modules: {e}")
        logger.error("Make sure you have configured your config.py file and installed all dependencies.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}", exc_info=True)
        sys.exit(1)
