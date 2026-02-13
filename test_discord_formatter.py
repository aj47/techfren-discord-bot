#!/usr/bin/env python3
"""
Unit tests for DiscordFormatter citation normalization.
"""

import pytest
from discord_formatter import DiscordFormatter


class TestNormalizeCitations:
    """Test cases for _normalize_citations method."""

    def test_none_input(self):
        """Test handling of None input."""
        result = DiscordFormatter._normalize_citations(None)
        assert result == []

    def test_empty_list(self):
        """Test handling of empty list."""
        result = DiscordFormatter._normalize_citations([])
        assert result == []

    def test_empty_dict(self):
        """Test handling of empty dict."""
        result = DiscordFormatter._normalize_citations({})
        assert result == []

    def test_perplexity_simple_urls(self):
        """Test Perplexity format with simple URL strings."""
        citations = [
            "https://example.com/article1",
            "https://example.com/article2"
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 2
        assert result[0] == {'url': 'https://example.com/article1'}
        assert result[1] == {'url': 'https://example.com/article2'}

    def test_perplexity_nested_dict_format(self):
        """Test Perplexity nested dict format: {"citations": [...]}"""
        citations = {
            "citations": [
                {"url": "https://example.com/article1"},
                {"url": "https://example.com/article2"}
            ]
        }
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 2
        assert result[0] == {'url': 'https://example.com/article1'}
        assert result[1] == {'url': 'https://example.com/article2'}

    def test_perplexity_double_nested(self):
        """Test Perplexity double-nested format with inner citations."""
        citations = {
            "citations": [
                {
                    "url": "https://example.com/article1",
                    "citations": [
                        {"url": "https://example.com/sub1"},
                        {"url": "https://example.com/sub2"}
                    ]
                }
            ]
        }
        result = DiscordFormatter._normalize_citations(citations)
        # Should extract BOTH parent and nested citations
        assert len(result) == 3
        # Verify nested citations are extracted
        urls = [c['url'] for c in result]
        assert "https://example.com/article1" in urls
        assert "https://example.com/sub1" in urls
        assert "https://example.com/sub2" in urls

    def test_deeply_nested_citations(self):
        """Test deeply nested citation structures (3+ levels)."""
        citations = {
            "citations": [
                {
                    "url": "https://example.com/level1",
                    "citations": [
                        {
                            "url": "https://example.com/level2",
                            "citations": [
                                {"url": "https://example.com/level3"}
                            ]
                        }
                    ]
                }
            ]
        }
        result = DiscordFormatter._normalize_citations(citations)
        # Should extract all 3 levels
        assert len(result) == 3
        urls = [c['url'] for c in result]
        assert "https://example.com/level1" in urls
        assert "https://example.com/level2" in urls
        assert "https://example.com/level3" in urls

    def test_alternate_wrapper_keys(self):
        """Test dict wrappers with alternate keys."""
        # Test 'items' wrapper
        citations = {
            "items": [
                {"url": "https://example.com/item1"},
                {"url": "https://example.com/item2"}
            ]
        }
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 2

        # Test 'sources' wrapper
        citations = {
            "sources": [
                {"url": "https://example.com/src1"}
            ]
        }
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 1

        # Test 'results' wrapper
        citations = {
            "results": [
                {"url": "https://example.com/res1"}
            ]
        }
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 1

    def test_exa_format_with_metadata(self):
        """Test Exa format with full metadata."""
        citations = [
            {
                "url": "https://example.com/article1",
                "title": "Article Title",
                "author": "John Doe",
                "publishedDate": "2024-01-15T10:30:00Z"
            },
            {
                "url": "https://example.com/article2",
                "title": "Another Article"
            }
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 2
        assert result[0]['url'] == 'https://example.com/article1'
        assert result[0]['title'] == 'Article Title'
        assert result[0]['author'] == 'John Doe'
        assert result[1]['url'] == 'https://example.com/article2'
        assert result[1]['title'] == 'Another Article'

    def test_alternate_url_field_names(self):
        """Test citations with alternate URL field names."""
        # Test 'link' field
        citations = [
            {"link": "https://example.com/link1"}
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 1
        assert result[0]['url'] == 'https://example.com/link1'

        # Test 'source_url' field
        citations = [
            {"source_url": "https://example.com/src1"}
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 1
        assert result[0]['url'] == 'https://example.com/src1'

    def test_mixed_citation_formats(self):
        """Test mixed citation formats in single response."""
        citations = [
            "https://example.com/simple",
            {"url": "https://example.com/dict"},
            {"link": "https://example.com/link"}
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 3
        assert result[0]['url'] == 'https://example.com/simple'
        assert result[1]['url'] == 'https://example.com/dict'
        assert result[2]['url'] == 'https://example.com/link'

    def test_dict_without_url_returns_empty(self):
        """Test dict citation without any URL field."""
        citations = [
            {"title": "No URL here"},
            {"author": "Someone"}
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 0

    def test_list_of_lists_flattening(self):
        """Test flattening of nested list structures."""
        citations = [
            [
                {"url": "https://example.com/nested1"},
                {"url": "https://example.com/nested2"}
            ]
        ]
        result = DiscordFormatter._normalize_citations(citations)
        assert len(result) == 2

    def test_dict_wrapper_with_non_list_value(self):
        """Test dict wrapper where key exists but value is not a list."""
        citations = {
            "citations": "not a list"
        }
        result = DiscordFormatter._normalize_citations(citations)
        # Should handle gracefully - tries to process as string
        assert result == []


class TestFormatCitationLink:
    """Test cases for _format_citation_link method."""

    def test_simple_url(self):
        """Test formatting citation with simple URL."""
        citation = {'url': 'https://example.com/article'}
        result = DiscordFormatter._format_citation_link(1, citation)
        assert result == "[`[1]`](https://example.com/article)"

    def test_empty_url(self):
        """Test formatting citation with empty URL."""
        citation = {'url': ''}
        result = DiscordFormatter._format_citation_link(1, citation)
        assert result == "[`[1]`]()"

    def test_missing_url_field(self):
        """Test formatting citation without URL field."""
        citation = {'title': 'No URL'}
        result = DiscordFormatter._format_citation_link(1, citation)
        assert result == "[`[1]`]()"


class TestFormatLlMResponse:
    """Test cases for format_llm_response method."""

    def test_no_citations(self):
        """Test formatting response without citations."""
        content = "This is a test response"
        result = DiscordFormatter.format_llm_response(content)
        assert result == content

    def test_citations_replace_number_references(self):
        """Test that citation numbers are replaced with links."""
        content = "According to [1] and [2], AI is advancing."
        citations = [
            "https://example.com/1",
            "https://example.com/2"
        ]
        result = DiscordFormatter.format_llm_response(content, citations)
        # Check that the formatted citations are present
        assert "[`[1]`]" in result
        assert "[`[2]`]" in result
        # Check that standalone [1] and [2] patterns are replaced
        # The replacement is "[`[1]`]" so standalone [1] should not appear outside backticks
        import re
        standalone_pattern = r'(?<!`)\[1\](?!`)'
        standalone_pattern2 = r'(?<!`)\[2\](?!`)'
        assert not re.search(standalone_pattern, result)
        assert not re.search(standalone_pattern2, result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
