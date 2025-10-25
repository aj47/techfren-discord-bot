"""
Test image processing functionality for Discord bot.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from llm_handler import ImageContent, download_image_as_base64, _process_images_from_context


class TestImageContent:
    """Test the ImageContent builder pattern."""

    def test_image_content_initialization(self):
        """Test ImageContent initialization."""
        ic = ImageContent()
        assert ic.has_images() is False
        assert ic.build() == []

    def test_add_image_url(self):
        """Test adding image from URL."""
        ic = ImageContent()
        ic.add_image_url("https://example.com/image.jpg", detail="high")
        
        assert ic.has_images() is True
        images = ic.build()
        assert len(images) == 1
        assert images[0]["type"] == "image_url"
        assert images[0]["image_url"]["url"] == "https://example.com/image.jpg"
        assert images[0]["image_url"]["detail"] == "high"

    def test_add_image_base64(self):
        """Test adding image from base64."""
        ic = ImageContent()
        base64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        ic.add_image_base64(base64_data, media_type="image/png")
        
        assert ic.has_images() is True
        images = ic.build()
        assert len(images) == 1
        assert images[0]["type"] == "image_url"
        assert images[0]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_builder_pattern_chaining(self):
        """Test builder pattern allows chaining."""
        ic = ImageContent()
        result = ic.add_image_url("https://example.com/1.jpg").add_image_url("https://example.com/2.jpg")
        
        assert result is ic
        assert len(ic.build()) == 2

    def test_multiple_images(self):
        """Test adding multiple images."""
        ic = ImageContent()
        ic.add_image_url("https://example.com/1.jpg")
        ic.add_image_url("https://example.com/2.jpg")
        ic.add_image_base64("base64data", "image/jpeg")
        
        assert ic.has_images() is True
        assert len(ic.build()) == 3


@pytest.mark.asyncio
class TestDownloadImage:
    """Test image download functionality."""

    @patch('aiohttp.ClientSession')
    async def test_download_image_success(self, mock_session):
        """Test successful image download."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.read = AsyncMock(return_value=b"fake_image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await download_image_as_base64("https://example.com/image.jpg")
        
        assert result is not None
        base64_data, media_type = result
        assert isinstance(base64_data, str)
        assert media_type == "image/jpeg"

    @patch('aiohttp.ClientSession')
    async def test_download_image_not_found(self, mock_session):
        """Test image download with 404 status."""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await download_image_as_base64("https://example.com/notfound.jpg")
        
        assert result is None

    @patch('aiohttp.ClientSession')
    async def test_download_non_image(self, mock_session):
        """Test download with non-image content type."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session_instance = MagicMock()
        mock_session_instance.get = MagicMock(return_value=mock_response)
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await download_image_as_base64("https://example.com/page.html")
        
        assert result is None


@pytest.mark.asyncio
class TestProcessImagesFromContext:
    """Test processing images from message context."""

    async def test_no_context(self):
        """Test with no message context."""
        result = await _process_images_from_context(None)
        assert result is None

    async def test_empty_context(self):
        """Test with empty message context."""
        result = await _process_images_from_context({})
        assert result is None

    @patch('llm_handler.download_image_as_base64')
    async def test_referenced_message_with_image(self, mock_download):
        """Test extracting image from referenced message."""
        mock_download.return_value = ("base64data", "image/jpeg")
        
        mock_attachment = Mock()
        mock_attachment.content_type = "image/jpeg"
        mock_attachment.url = "https://example.com/image.jpg"
        mock_attachment.filename = "test.jpg"
        
        mock_message = Mock()
        mock_message.attachments = [mock_attachment]
        
        context = {
            "referenced_message": mock_message
        }
        
        result = await _process_images_from_context(context)
        
        assert result is not None
        assert result.has_images() is True
        assert len(result.build()) == 1

    @patch('llm_handler.download_image_as_base64')
    async def test_current_message_with_image(self, mock_download):
        """Test extracting image from current message."""
        mock_download.return_value = ("base64data", "image/png")
        
        mock_attachment = Mock()
        mock_attachment.content_type = "image/png"
        mock_attachment.url = "https://example.com/screenshot.png"
        mock_attachment.filename = "screenshot.png"
        
        mock_message = Mock()
        mock_message.attachments = [mock_attachment]
        
        context = {
            "current_message": mock_message
        }
        
        result = await _process_images_from_context(context)
        
        assert result is not None
        assert result.has_images() is True

    @patch('llm_handler.download_image_as_base64')
    async def test_multiple_messages_with_images(self, mock_download):
        """Test extracting images from multiple messages."""
        mock_download.return_value = ("base64data", "image/jpeg")
        
        mock_attachment1 = Mock()
        mock_attachment1.content_type = "image/jpeg"
        mock_attachment1.url = "https://example.com/1.jpg"
        mock_attachment1.filename = "1.jpg"
        
        mock_attachment2 = Mock()
        mock_attachment2.content_type = "image/png"
        mock_attachment2.url = "https://example.com/2.png"
        mock_attachment2.filename = "2.png"
        
        mock_ref_message = Mock()
        mock_ref_message.attachments = [mock_attachment1]
        
        mock_current_message = Mock()
        mock_current_message.attachments = [mock_attachment2]
        
        context = {
            "referenced_message": mock_ref_message,
            "current_message": mock_current_message
        }
        
        result = await _process_images_from_context(context)
        
        assert result is not None
        assert result.has_images() is True
        assert len(result.build()) == 2

    async def test_message_without_attachments(self):
        """Test message without attachments attribute."""
        mock_message = Mock(spec=[])
        
        context = {
            "current_message": mock_message
        }
        
        result = await _process_images_from_context(context)
        
        assert result is None

    @patch('llm_handler.download_image_as_base64')
    async def test_non_image_attachment(self, mock_download):
        """Test attachment that is not an image."""
        mock_attachment = Mock()
        mock_attachment.content_type = "application/pdf"
        mock_attachment.url = "https://example.com/doc.pdf"
        
        mock_message = Mock()
        mock_message.attachments = [mock_attachment]
        
        context = {
            "current_message": mock_message
        }
        
        result = await _process_images_from_context(context)
        
        assert result is None
        mock_download.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
