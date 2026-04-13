import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import summarization_tasks


class TestDailyGeneralSummary(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_client = summarization_tasks.discord_client
        summarization_tasks.set_discord_client(MagicMock())

    async def asyncTearDown(self):
        summarization_tasks.set_discord_client(self.original_client)

    async def test_general_summary_uses_all_active_channels_even_when_per_channel_summaries_are_limited(self):
        now = datetime(2026, 4, 13, 12, 0, tzinfo=timezone.utc)
        active_channels = [
            {
                "channel_id": "general_id",
                "channel_name": "general",
                "guild_id": "guild_id",
                "guild_name": "TechFren",
                "message_count": 1,
            },
            {
                "channel_id": "links_id",
                "channel_name": "links-dump",
                "guild_id": "guild_id",
                "guild_name": "TechFren",
                "message_count": 1,
            },
            {
                "channel_id": "dev_id",
                "channel_name": "dev-chat",
                "guild_id": "guild_id",
                "guild_name": "TechFren",
                "message_count": 1,
            },
        ]
        messages_by_channel = {
            "general_id": {
                "messages": [self._message("g1", "Alice", "General update")]
            },
            "links_id": {
                "messages": [self._message("l1", "Bob", "Useful link")]
            },
            "dev_id": {
                "messages": [self._message("d1", "Casey", "Dev discussion")]
            },
        }

        with (
            patch.object(summarization_tasks.config, "summary_channel_ids", ["general_id", "links_id"]),
            patch.object(summarization_tasks.config, "general_channel_id", "general_id"),
            patch.object(summarization_tasks.database, "get_active_channels", return_value=active_channels),
            patch.object(summarization_tasks.database, "get_messages_for_time_range", return_value=messages_by_channel),
            patch.object(summarization_tasks.database, "get_user_engagement_metrics", return_value={}),
            patch.object(summarization_tasks, "analyze_messages_for_points", new=AsyncMock(return_value=None)),
            patch.object(summarization_tasks, "call_llm_for_summary", new=AsyncMock(return_value="summary")) as mock_summary,
            patch.object(summarization_tasks.database, "store_channel_summary", return_value=True) as mock_store,
            patch.object(summarization_tasks.database, "delete_messages_older_than", return_value=0),
            patch.object(summarization_tasks, "post_summary_to_reports_channel", new=AsyncMock()),
        ):
            await summarization_tasks.run_daily_summarization_once(now=now)

        general_calls = [
            call for call in mock_summary.await_args_list
            if call.args[1] == "all active channels"
        ]
        self.assertEqual(len(general_calls), 1)

        summarized_messages = general_calls[0].args[0]
        self.assertEqual(
            {msg["channel_name"] for msg in summarized_messages},
            {"general", "links-dump", "dev-chat"},
        )

        called_channel_scopes = [call.args[1] for call in mock_summary.await_args_list]
        self.assertIn("links-dump", called_channel_scopes)
        self.assertNotIn("dev-chat", called_channel_scopes)

        general_store_call = next(
            call for call in mock_store.call_args_list
            if call.kwargs["channel_id"] == "general_id"
        )
        metadata = general_store_call.kwargs["metadata"]
        self.assertEqual(metadata["summary_scope"], "all_active_channels")
        self.assertEqual(
            set(metadata["included_channel_names"]),
            {"general", "links-dump", "dev-chat"},
        )

    def _message(self, message_id, author_name, content):
        return {
            "id": message_id,
            "author_id": f"{author_name}_id",
            "author_name": author_name,
            "content": content,
            "created_at": datetime(2026, 4, 13, 11, 0, tzinfo=timezone.utc),
            "is_bot": False,
            "is_command": False,
            "scraped_url": None,
            "scraped_content_summary": None,
            "scraped_content_key_points": None,
            "image_descriptions": None,
        }


if __name__ == "__main__":
    unittest.main()
