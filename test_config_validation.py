"""
Test suite for configuration validation functionality.
Tests the config_validator module and configuration handling.
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
import logging

# Import the module to test
import config_validator

# Set up logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('test_config_validation')


class TestConfigValidation:
    """Test configuration validation functionality."""

    def test_validate_config_all_present(self):
        """Test validation when all required config values are present."""
        mock_config = MagicMock()
        mock_config.discord_token = "valid_discord_token"
        mock_config.openai_api_key = "valid_openai_key"
        mock_config.apify_api_token = "valid_apify_token"
        mock_config.firecrawl_api_key = "valid_firecrawl_key"
        
        with patch('config_validator.config', mock_config):
            result = config_validator.validate_config()
            assert result is True

    def test_validate_config_missing_discord_token(self):
        """Test validation when Discord token is missing."""
        mock_config = MagicMock()
        mock_config.discord_token = None
        mock_config.openai_api_key = "valid_openai_key"
        mock_config.apify_api_token = "valid_apify_token"
        mock_config.firecrawl_api_key = "valid_firecrawl_key"
        
        with patch('config_validator.config', mock_config):
            result = config_validator.validate_config()
            assert result is False

    def test_validate_config_empty_values(self):
        """Test validation when config values are empty strings."""
        mock_config = MagicMock()
        mock_config.discord_token = ""
        mock_config.openai_api_key = ""
        mock_config.apify_api_token = ""
        mock_config.firecrawl_api_key = ""
        
        with patch('config_validator.config', mock_config):
            result = config_validator.validate_config()
            assert result is False

    def test_validate_config_partial_configuration(self):
        """Test validation with partial configuration (some services missing)."""
        mock_config = MagicMock()
        mock_config.discord_token = "valid_discord_token"
        mock_config.openai_api_key = "valid_openai_key"
        mock_config.apify_api_token = None  # Missing Apify
        mock_config.firecrawl_api_key = "valid_firecrawl_key"
        
        with patch('config_validator.config', mock_config):
            # Should still be valid if at least one scraping service is configured
            result = config_validator.validate_config()
            # This depends on the actual validation logic

    def test_validate_config_missing_attributes(self):
        """Test validation when config attributes don't exist."""
        mock_config = MagicMock()
        # Remove attributes to simulate missing config
        del mock_config.discord_token
        
        with patch('config_validator.config', mock_config):
            result = config_validator.validate_config()
            assert result is False

    def test_config_file_creation(self):
        """Test configuration file creation and validation."""
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
# Test configuration
discord_token = "test_discord_token"
openai_api_key = "test_openai_key"
apify_api_token = "test_apify_token"
firecrawl_api_key = "test_firecrawl_key"
""")
            temp_config_path = f.name
        
        try:
            # Test that the config file can be loaded and validated
            # This would require modifying the config_validator to accept a file path
            assert os.path.exists(temp_config_path)
        finally:
            os.unlink(temp_config_path)

    def test_environment_variable_fallback(self):
        """Test fallback to environment variables when config is missing."""
        # Set environment variables
        env_vars = {
            'DISCORD_TOKEN': 'env_discord_token',
            'OPENAI_API_KEY': 'env_openai_key',
            'APIFY_API_TOKEN': 'env_apify_token',
            'FIRECRAWL_API_KEY': 'env_firecrawl_key'
        }
        
        with patch.dict(os.environ, env_vars):
            # Test that environment variables are used when config is missing
            # This depends on the actual implementation
            pass

    def test_config_validation_logging(self):
        """Test that configuration validation produces appropriate log messages."""
        mock_config = MagicMock()
        mock_config.discord_token = None
        
        with patch('config_validator.config', mock_config), \
             patch('config_validator.logger') as mock_logger:
            
            config_validator.validate_config()
            
            # Should log validation errors
            mock_logger.error.assert_called()


class TestConfigSecurity:
    """Test configuration security aspects."""

    def test_config_token_masking(self):
        """Test that tokens are properly masked in logs."""
        # This would test that sensitive config values are not logged in plain text
        pass

    def test_config_file_permissions(self):
        """Test that config files have appropriate permissions."""
        # This would test file permission validation
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
