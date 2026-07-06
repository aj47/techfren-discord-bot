from discord_formatter import DiscordFormatter


def test_enhance_summary_sections_rewrites_arrow_message_links_to_source():
    content = (
        "• **New model release** - tested on a Shopify app - "
        "`realtimeuk` <t:1783376820:t> [→](https://discord.com/channels/1/2/3)"
    )

    formatted = DiscordFormatter._enhance_summary_sections(content)

    assert "[source](<https://discord.com/channels/1/2/3>)" in formatted
    assert "[→]" not in formatted


def test_enhance_summary_sections_rewrites_wrapped_arrow_message_links_to_source():
    content = "• **Topic** - `user` <t:1783376820:t> [→](<https://discord.com/channels/1/2/3>)"

    formatted = DiscordFormatter._enhance_summary_sections(content)

    assert "[source](<https://discord.com/channels/1/2/3>)" in formatted
    assert "<<https://discord.com/channels/1/2/3>>" not in formatted


def test_enhance_summary_sections_keeps_non_discord_links_unchanged():
    content = "• [3090 prices in 2026](https://old.reddit.com/r/LocalLLaMA/example)"

    formatted = DiscordFormatter._enhance_summary_sections(content)

    assert "[3090 prices in 2026](<https://old.reddit.com/r/LocalLLaMA/example>)" in formatted
