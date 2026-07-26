import respx
import httpx
import pytest
from hotspot.llm.ollama_client import OllamaClient, LLMError


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_returns_dict():
    respx.post("http://localhost:11434/api/chat").respond(
        json={"message": {"content": '{"winner": "A", "reason": "A is fresher"}'}}
    )
    client = OllamaClient(base_url="http://localhost:11434", model="test-model", max_retries=1)
    result = await client.chat_json("prompt")
    assert result == {"winner": "A", "reason": "A is fresher"}


@pytest.mark.asyncio
@respx.mock
async def test_chat_json_raises_on_invalid_json():
    respx.post("http://localhost:11434/api/chat").respond(
        json={"message": {"content": "not json"}}
    )
    client = OllamaClient(base_url="http://localhost:11434", model="test-model", max_retries=1)
    with pytest.raises(LLMError):
        await client.chat_json("prompt")


@pytest.mark.asyncio
@respx.mock
async def test_batch_chat_json_returns_none_on_failure():
    respx.post("http://localhost:11434/api/chat").mock(
        side_effect=[
            httpx.Response(200, json={"message": {"content": '{"x": 1}'}}),
            httpx.Response(500, text="server error"),
            httpx.Response(500, text="server error"),
        ]
    )
    client = OllamaClient(
        base_url="http://localhost:11434", model="test-model",
        max_retries=1, concurrency=2,
    )
    results = await client.batch_chat_json(["p1", "p2"])
    assert results[0] == {"x": 1}
    assert results[1] is None
