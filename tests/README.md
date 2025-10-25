# Test Suite

This directory contains all test files for the Discord bot functionality.

## Test Categories

### Chart & Table Tests
- `test_chart_detection.py` - Test chart type detection logic
- `test_chart_fix.py` - Test chart generation fixes
- `test_chart_data_extraction_fix.py` - Test chart data extraction
- `test_enhanced_chart_labels.py` - Test enhanced chart labels
- `test_table_parsing.py` - Test table parsing functionality
- `test_table_extraction.py` - Test table extraction from LLM responses
- `test_table_validation.py` - Test table validation rules
- `test_edge_case_tables.py` - Test edge cases for table validation
- `test_chart_type_logic.py` - Test chart type selection logic

### Bot Functionality Tests
- `test_bot_startup.py` - Test bot startup procedures
- `test_commands.py` - Test command handling
- `test_database.py` - Test database operations
- `test_database_performance.py` - Test database performance
- `test_message_length.py` - Test message length handling

### Discord Integration Tests
- `test_channel_context.py` - Test channel context handling
- `test_thread_error_handling.py` - Test thread error scenarios
- `test_thread_handling_simple.py` - Test basic thread handling
- `test_message_references.py` - Test message reference handling
- `test_message_links_simple.py` - Test simple message linking
- `test_integration_message_references.py` - Test message reference integration

### API & External Services Tests
- `test_apify.py` - Test Apify integration
- `test_perplexity_models.py` - Test Perplexity API models
- `test_perplexity_sources.py` - Test Perplexity source handling
- `test_sonar_web.py` - Test Sonar web integration
- `test_twitter_url_processing.py` - Test Twitter URL processing
- `test_x_scraping.py` - Test X (Twitter) scraping

### Image & Font Tests
- `test_image_processing.py` - Test image processing functionality
- `test_font_registration.py` - Test local font registration

### Source Linking Tests
- `test_source_linking_verification.py` - Test source link verification
- `test_source_linking_integration.py` - Test source link integration
- `test_links_dump.py` - Test links dump functionality

### User Scenario Tests
- `test_user_chart_scenarios.py` - Test user chart generation scenarios
- `test_sum_day_with_links.py` - Test daily summary with links
- `test_methodology_chart_fix.py` - Test chart methodology fixes

## Running Tests

To run all tests:
```bash
python -m pytest tests/ -v
```

To run specific test categories:
```bash
python -m pytest tests/test_chart_*.py -v
python -m pytest tests/test_database*.py -v
```

To run a specific test file:
```bash
python -m pytest tests/test_chart_detection.py -v
```

## Test Configuration

Most tests are standalone and can be run directly:
```bash
python tests/test_chart_detection.py
```

Some tests may require additional setup or environment variables to be configured.