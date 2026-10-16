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

    def test_drops_rhetoric_recruiting_and_url_question_marks(self):
        """Oct 15 thread: URL ?, quotes, insults, status, and recruiting leaked in."""
        payload = _channel(
            "g",
            "general",
            [
                _msg(
                    "yt",
                    "bird",
                    "https://www.youtube.com/watch?v=zrs_eJ_XGt4\n\nI got to watch this recently and it was very good",
                ),
                _msg(
                    "quote",
                    "bird",
                    '"What is a number that a man may know it, and a man, that he may know a number?"\n\nman droppin bars',
                    created_at=datetime(2026, 9, 30, 12, 1, tzinfo=timezone.utc),
                ),
                _msg(
                    "insult",
                    "bird",
                    "Are they literally retarded?",
                    created_at=datetime(2026, 9, 30, 12, 2, tzinfo=timezone.utc),
                ),
                _msg(
                    "rhetorical",
                    "bird",
                    "They can't generate a contrived character?",
                    created_at=datetime(2026, 9, 30, 12, 3, tzinfo=timezone.utc),
                ),
                _msg(
                    "status",
                    "tazr",
                    "light day? 6% ... well, the setup is done, just adding clipping due to collapse",
                    created_at=datetime(2026, 9, 30, 12, 4, tzinfo=timezone.utc),
                ),
                _msg(
                    "recruit",
                    "nhoj",
                    "We're bringing exceptional engineers together for a paid residency in India at a US-registered technology company working at the frontier of AI and systems. Interested? DM me.",
                    created_at=datetime(2026, 9, 30, 12, 5, tzinfo=timezone.utc),
                ),
                _msg(
                    "statement",
                    "tazr",
                    "could just be this chat, last time i just needed to get rid of the chat",
                    created_at=datetime(2026, 9, 30, 12, 6, tzinfo=timezone.utc),
                ),
                _msg(
                    "rant",
                    "bird",
                    "Who the fuck is naming their models like this, fire that intern.",
                    created_at=datetime(2026, 9, 30, 12, 7, tzinfo=timezone.utc),
                ),
                _msg(
                    "real1",
                    "pierre",
                    "guys I see gpt 6 inside chat gpt web but is it astra or what model is it?",
                    created_at=datetime(2026, 9, 30, 12, 8, tzinfo=timezone.utc),
                ),
                _msg(
                    "real2",
                    "realtime",
                    "anyone got contacts in the database world?",
                    created_at=datetime(2026, 9, 30, 12, 9, tzinfo=timezone.utc),
                ),
                _msg(
                    "real3",
                    "bhavnesh",
                    "Oh, so do this mean the model can do more thinking internally without generating as many reasoning tokens? 🤔",
                    created_at=datetime(2026, 9, 30, 12, 10, tzinfo=timezone.utc),
                ),
                _msg(
                    "real4",
                    "tazr",
                    "i don't know about deepseek engram do you know if they tied it to scratchpad?",
                    created_at=datetime(2026, 9, 30, 12, 11, tzinfo=timezone.utc),
                ),
                _msg(
                    "real5",
                    "bird",
                    "I am curious, could Claude read the RYS sagas and then use nnsight to set up probe studies to find the most important layers in 3.8 27B to loop?",
                    created_at=datetime(2026, 9, 30, 12, 12, tzinfo=timezone.utc),
                ),
            ],
        )
        qs = oq.scout_questions(payload, guild_id=GUILD, limit=12)
        ids = [q["id"] for q in qs]
        self.assertEqual(ids, ["real1", "real2", "real3", "real4", "real5"])

    def test_parent_has_no_pings(self):
        text = oq.parent_content(3, "September 30, 2026")
        self.assertIn("Open questions — September 30, 2026", text)
        self.assertNotIn("<@", text)
        self.assertNotIn("<#", text)

    def test_resolves_general_like_digest_when_env_unset(self):
        class _Ch:
            def __init__(self, cid, name):
                self.id = cid
                self.name = name

        class _Guild:
            def __init__(self):
                self.text_channels = [
                    _Ch(111, "bots"),
                    _Ch(1053882445017124977, "general"),
                    _Ch(222, "off-topic"),
                ]

        class _Client:
            guilds = [_Guild()]

        self.assertEqual(
            oq.resolve_general_channel_id("999", _Client()),
            "999",
        )
        self.assertEqual(
            oq.resolve_general_channel_id(None, _Client()),
            "1053882445017124977",
        )
        self.assertEqual(
            oq.resolve_general_channel_id("", _Client()),
            "1053882445017124977",
        )
        self.assertIsNone(oq.resolve_general_channel_id(None, None))
        empty = type("C", (), {"guilds": []})()
        self.assertIsNone(oq.resolve_general_channel_id(None, empty))


if __name__ == "__main__":
    unittest.main()
