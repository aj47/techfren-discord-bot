\
-- SQL Setup for TechFren Discord Bot Database

-- Create messages table
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    guild_id TEXT,
    guild_name TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    is_bot INTEGER NOT NULL,
    is_command INTEGER NOT NULL,
    command_type TEXT
);

-- Create indexes for messages table
CREATE INDEX IF NOT EXISTS idx_author_id ON messages (author_id);
CREATE INDEX IF NOT EXISTS idx_channel_id ON messages (channel_id);
CREATE INDEX IF NOT EXISTS idx_guild_id ON messages (guild_id);
CREATE INDEX IF NOT EXISTS idx_created_at ON messages (created_at);
CREATE INDEX IF NOT EXISTS idx_is_command ON messages (is_command);

-- Create channel_summaries table
CREATE TABLE IF NOT EXISTS channel_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    guild_id TEXT,
    guild_name TEXT,
    date TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    active_users INTEGER NOT NULL,
    active_users_list TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    metadata TEXT
);

-- Create indexes for channel_summaries table
CREATE INDEX IF NOT EXISTS idx_summary_channel_id ON channel_summaries (channel_id);
CREATE INDEX IF NOT EXISTS idx_summary_date ON channel_summaries (date);

-- Create scraped_links table
CREATE TABLE IF NOT EXISTS scraped_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    content TEXT,
    metadata TEXT, -- JSON string for additional metadata from Firecrawl
    first_scraped_at TIMESTAMP NOT NULL,
    last_updated_at TIMESTAMP NOT NULL
);

-- Create index for scraped_links table
CREATE INDEX IF NOT EXISTS idx_scraped_url ON scraped_links (url);

-- Create frontend_entries table for the web frontend
CREATE TABLE IF NOT EXISTS frontend_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('proprietary', 'opensource', 'freemium', 'unknown')),
    github_url TEXT,
    website_url TEXT,
    rating REAL CHECK(rating >= 0 AND rating <= 10),
    rating_source TEXT,
    discord_submitter TEXT,
    discord_submitter_id TEXT,
    category TEXT,
    tags TEXT, -- JSON array of tags
    logo_url TEXT,
    repository_stars INTEGER,
    pricing_info TEXT,
    notes TEXT,
    related_urls TEXT, -- JSON array of related URLs
    created_at TIMESTAMP NOT NULL,
    last_updated_at TIMESTAMP NOT NULL
);

-- Create indexes for frontend_entries table
CREATE INDEX IF NOT EXISTS idx_frontend_entries_name ON frontend_entries (name);
CREATE INDEX IF NOT EXISTS idx_frontend_entries_status ON frontend_entries (status);
CREATE INDEX IF NOT EXISTS idx_frontend_entries_category ON frontend_entries (category);
CREATE INDEX IF NOT EXISTS idx_frontend_entries_submitter_id ON frontend_entries (discord_submitter_id);

-- Note: Ensure your database client (e.g., libSQL) is configured to handle these types appropriately.
-- For example, TIMESTAMP is often stored as TEXT in ISO 8601 format or as INTEGER (Unix timestamp).
