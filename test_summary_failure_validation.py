"""Regression tests for junk LLM summary responses.

Last night's digest call returned a stray one-liner ("User Safety: safe") from
the router; the bot stored and posted it as a real summary. These tests pin the
validator that rejects such junk.
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '.')

from summarization_tasks import _is_summary_generation_failure


class TestIsSummaryGenerationFailure(unittest.TestCase):
    def test_exact_failure_strings_are_rejected(self):
        self.assertTrue(_is_summary_generation_failure(
            "Sorry, the summary request timed out. Please try again later."))
        self.assertTrue(_is_summary_generation_failure(
            "Sorry, I encountered an error while generating the summary. "
            "Please try again later."))

    def test_non_string_and_empty_are_rejected(self):
        self.assertTrue(_is_summary_generation_failure(None))
        self.assertTrue(_is_summary_generation_failure(123))
        self.assertTrue(_is_summary_generation_failure(""))

    def test_junk_one_liners_are_rejected(self):
        # The 2026-09-15 overnight failure signature.
        self.assertTrue(_is_summary_generation_failure("User Safety: safe"))
        self.assertTrue(_is_summary_generation_failure("User Safety: safe\n"))
        self.assertTrue(_is_summary_generation_failure("ok"))
        self.assertTrue(_is_summary_generation_failure("Hello!"))

    def test_short_circuit_junk_not_saved_by_repeated_calls(self):
        with mock.patch('summarization_tasks.database.store_channel_summary',
                        return_value=True) as m:
            summary = "User Safety: safe"
            if _is_summary_generation_failure(summary):
                m.assert_not_called()

    def test_raw_header_style_is_valid(self):
        self.assertFalse(_is_summary_generation_failure(
            "## 🔥 Highlights\n• **Topic** - context - `user`"))
        self.assertFalse(_is_summary_generation_failure(
            "## 💡 Links Worth Checking\n[Title](https://x.com/foo)"))

    def test_discord_formatted_header_style_is_valid(self):
        self.assertFalse(_is_summary_generation_failure(
            "**🔥 Highlights**\n**Anthropic profitable** - context"))

    def test_message_link_style_is_valid(self):
        self.assertFalse(_is_summary_generation_failure(
            "Some point - `user` [source](<https://discord.com/channels/1/2/3>)"))

    def test_long_digest_without_markers_is_valid(self):
        self.assertFalse(_is_summary_generation_failure("x" * 800))


if __name__ == '__main__':
    unittest.main()
