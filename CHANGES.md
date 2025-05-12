# Changes to the TechFren Discord Bot

## Database Migration

- Migrated from SQLite to libSQL for better performance and scalability
- Adapted database connection logic in `database.py` and `db_utils.py`
- Changed database file from `discord_messages.db` to `discord_messages.turso`

## API Key Management

- Implemented an API key rotation system in `bot.py`
- Extended the `APIKeyRotator` class to support different types of API keys
- Converted existing API keys in `keys.json` from a simple array to a structured collection with types:
  - `openrouter_api_keys` for the OpenRouter API
  - `firecrawl_api_keys` for the Firecrawl API

## Firecrawl Integration

- Added the Firecrawl library (`firecrawl-py`) to `requirements.txt`
- Implemented URL detection and processing in messages
- Implemented Firecrawl API integration for web content scraping
- Integrated Firecrawl API key rotation for rate limit handling
- Added storage and updating of scraped content in the `scraped_links` table

## Database Schema Extensions

- Added a new `scraped_links` table for storing scraped website data with columns:
  - `url` - The scraped URL
  - `content` - The scraped content
  - `metadata` - Additional metadata from Firecrawl
  - `first_scraped_at` - Timestamp of first scraping
  - `last_updated_at` - Timestamp of last update

- Added a new `frontend_entries` table for a future frontend application with columns:
  - `name` - Name of the project/application
  - `description` - Description
  - `status` - Status (proprietary, open source, freemium, unknown)
  - `github_url` - GitHub URL (if available)
  - `website_url` - Website URL (if available)
  - `rating` - Rating (0-10)
  - `rating_source` - Source of the rating
  - `discord_submitter` - Name of the Discord submitter
  - `discord_submitter_id` - Discord ID of the submitter
  - `category` - Category for filtering options
  - `tags` - Tags as a JSON array
  - `logo_url` - URL for the logo
  - `repository_stars` - Number of GitHub stars
  - `pricing_info` - Pricing information
  - `notes` - Additional notes
  - `related_urls` - Related URLs as a JSON array
  - `created_at` - Creation date
  - `last_updated_at` - Date of last update

## Database Operations

- Implemented CRUD operations in `database.py` for:
  - `scraped_links` table (`store_scraped_link`, `get_scraped_link`, `update_scraped_link`)
  - `frontend_entries` table (`store_frontend_entry`, `get_frontend_entry`, `get_frontend_entries_by_name`, `update_frontend_entry`)

## Refactoring and Cleanup

- Removed the no longer needed SQLite imports from `bot.py`
- Updated exception handling for Firecrawl and OpenRouter API calls
- Improved error handling for rate limits

## Documentation

- Created a `setup.sql` file with all SQL statements for database structure setup
- Updated `README.md` with new sections:
  - Database Management
  - API Key Management
  - Firecrawl Integration
- Updated setup instructions for the new configuration structure

## Dependencies

- Added `firecrawl-py` to `requirements.txt` for Firecrawl integration
- Added `libsql-client` to `requirements.txt` for libSQL support
