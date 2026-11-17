"""The handler logs a would-delete and does not delete while dry-run is on."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import promo_only
from promo_only import handle_promo_message


def _message(author_id="42", content="join https://discord.gg/abc", bot=False):
    message = MagicMock()
    message.id = 555
    message.content = content
    message.webhook_id = None
    message.author.id = int(author_id)
    message.author.bot = bot
    message.guild.id = 101
    message.channel.id = 7
    message.channel.name = "general"
    message.delete = AsyncMock()
    return message


@pytest.mark.asyncio
async def test_dry_run_logs_and_does_not_delete(monkeypatch):
    message = _message()
    note = MagicMock()
    monkeypatch.setattr(promo_only, "verdict_for", lambda *a, **k: promo_only.Verdict(True, 3, 3, "all stored messages are promotional"))
    monkeypatch.setattr(promo_only, "record_message", MagicMock())
    monkeypatch.setattr(promo_only, "note_decision", note)

    verdict = await handle_promo_message(message, enabled=True, dry_run=True)

    assert verdict.delete is True
    message.delete.assert_not_awaited()
    note.assert_called_once()


@pytest.mark.asyncio
async def test_live_mode_deletes(monkeypatch):
    message = _message()
    monkeypatch.setattr(promo_only, "verdict_for", lambda *a, **k: promo_only.Verdict(True, 3, 3, "all stored messages are promotional"))
    monkeypatch.setattr(promo_only, "record_message", MagicMock())

    await handle_promo_message(message, enabled=False and True or True, dry_run=False)

    message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_does_nothing(monkeypatch):
    message = _message()
    called = MagicMock()
    monkeypatch.setattr(promo_only, "verdict_for", called)

    result = await handle_promo_message(message, enabled=False, dry_run=True)

    assert result is None
    called.assert_not_called()
    message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_author_is_skipped(monkeypatch):
    message = _message(bot=True)
    called = MagicMock()
    monkeypatch.setattr(promo_only, "verdict_for", called)

    result = await handle_promo_message(message, enabled=True, dry_run=False)

    assert result is None
    called.assert_not_called()


@pytest.mark.asyncio
async def test_mixed_history_is_not_deleted(monkeypatch):
    message = _message()
    monkeypatch.setattr(promo_only, "verdict_for", lambda *a, **k: promo_only.Verdict(False, 4, 3, "history is not all promotional"))
    monkeypatch.setattr(promo_only, "record_message", MagicMock())

    verdict = await handle_promo_message(message, enabled=True, dry_run=False)

    assert verdict.delete is False
    message.delete.assert_not_awaited()
