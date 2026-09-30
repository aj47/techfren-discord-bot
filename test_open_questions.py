import unittest
from datetime import datetime, timezone

import open_questions as oq


GUILD = "1010083670599671838"


def _msg(
    mid,
    author,
    content,
    *,
    author_id="1",
    is_bot=False,
    reply_to=None,
    created_at=None,
):
    return {
        "id": mid,
        "author_id": author_id,
        "author_name": author,
        "content": content,
        "created_at": created_at or datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
        "is_bot": is_bot,
        "is_command": False,
        "reply_to_message_id": reply_to,
    }


def _channel(channel_id, name, messages):
    return {
        channel_id: {
            "channel_id": channel_id,
            "channel_name": name,
            "guild_id": GUILD,
            "messages": messages,
        }
    }


class TestOpenQuestionsScout(unittest.TestCase):
    def test_skips_replied_and_bots_and_thread_titles(self):
        payload = {}
        payload.update(
            _channel(
                "g",
                "general",
                [
                    _msg("q1", "alice", "Whats everyones genuine thoughts on Chatgpt GPTs?"),
                    _msg("r1", "bob", "I like them", reply_to="q1"),
                    _msg("q2", "bot", "anyone know the answer to this question please?", is_bot=True),
                    _msg("q3", "carol", "What's up with Pi? New main version coming?"),
                ],
            )
        )
        payload.update(
            _channel(
                "t",
                "Open questions - September 30, 2026",
                [_msg("t1", "dave", "How do I install hermes on linux please?")],
            )
        )
        qs = oq.scout_questions(payload, guild_id=GUILD, limit=12)
        ids = [q["id"] for q in qs]
        self.assertEqual(ids, ["q3"])
        self.assertNotIn("<@", oq.thread_body(qs))
        self.assertNotIn("<#", oq.thread_body(qs))
        self.assertNotIn(" in general", oq.thread_body(qs))

    def test_adds_context_only_for_deictic_asks(self):
        payload = _channel(
            "g",
            "general",
            [
                _msg("p1", "pierre", "I fixed codecompanion", author_id="p"),
                _msg(
                    "q1",
                    "cayc",
                    "Is that one open source? I only used it once.",
                    author_id="c",
                    created_at=datetime(2026, 9, 30, 12, 1, tzinfo=timezone.utc),
                ),
                _msg(
                    "q2",
                    "cold",
                    "Whats everyones genuine thoughts on Chatgpt GPTs?",
                    author_id="k",
                    created_at=datetime(2026, 9, 30, 12, 2, tzinfo=timezone.utc),
                ),
            ],
        )
        qs = oq.scout_questions(payload, guild_id=GUILD, limit=12)
        by_id = {q["id"]: q for q in qs}
        self.assertEqual(by_id["q1"]["context"], "I fixed codecompanion")
        self.assertNotIn("context", by_id["q2"])
        body = oq.thread_body(qs)
        self.assertIn("_re: I fixed codecompanion_", body)
        self.assertIn("**cayc** — Is that one open source?", body)
        self.assertNotIn("<t:", body)

    def test_parent_has_no_pings(self):
        text = oq.parent_content(3, "September 30, 2026")
        self.assertIn("Open questions — September 30, 2026", text)
        self.assertNotIn("<@", text)
        self.assertNotIn("<#", text)


if __name__ == "__main__":
    unittest.main()
