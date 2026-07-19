import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import llm_handler


def _completion(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


def _valid_response():
    return json.dumps({
        "awards": [{
            "author_id": "123",
            "author_name": "helper",
            "points": 10,
            "reason": "Provided a detailed technical answer.",
        }],
        "total_awarded": 10,
        "summary": "One meaningful contribution earned points.",
    })


@pytest.mark.asyncio
async def test_point_analysis_requests_strict_structured_output():
    create = AsyncMock(return_value=_completion(_valid_response()))
    messages = [{"author_id": "123", "author_name": "helper", "content": "answer"}]

    with patch.object(llm_handler.llm_client.chat.completions, "create", create):
        result = await llm_handler.analyze_messages_for_points(messages)

    assert result["awards"][0]["author_id"] == "123"
    assert result["total_awarded"] == 10
    request = create.await_args.kwargs
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["max_tokens"] == 4000
    assert request["extra_body"]["reasoning"]["effort"] == "low"


@pytest.mark.asyncio
async def test_point_analysis_retries_a_truncated_response():
    create = AsyncMock(side_effect=[
        _completion('{"awards":[{"author_id":"123",', finish_reason="length"),
        _completion(_valid_response()),
    ])
    messages = [{"author_id": "123", "author_name": "helper", "content": "answer"}]

    with patch.object(llm_handler.llm_client.chat.completions, "create", create):
        result = await llm_handler.analyze_messages_for_points(messages)

    assert create.await_count == 2
    assert create.await_args_list[0].kwargs["max_tokens"] == 4000
    assert create.await_args_list[1].kwargs["max_tokens"] == 8000
    assert result["total_awarded"] == 10


@pytest.mark.asyncio
async def test_point_analysis_falls_back_after_two_invalid_responses():
    create = AsyncMock(return_value=_completion("{", finish_reason="length"))
    messages = [{"author_id": "123", "author_name": "helper", "content": "answer"}]

    with patch.object(llm_handler.llm_client.chat.completions, "create", create):
        result = await llm_handler.analyze_messages_for_points(messages)

    assert create.await_count == 2
    assert result == {
        "awards": [],
        "summary": "Failed to analyze messages for points due to parsing error.",
    }
