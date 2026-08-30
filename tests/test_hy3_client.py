from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import StructuredOutputValidationError
from hy3_reproscope_mcp.hy3_client import Hy3Client


class ExampleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence: float


class FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeOpenAI:
    def __init__(self, responses: list[str]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_complete_text_uses_hy3_request_contract() -> None:
    fake = FakeOpenAI(["grounded response"])
    settings = Settings(HY3_API_KEY="test-key", HY3_REASONING_EFFORT="high")
    client = Hy3Client(settings, client=fake)

    result = await client.complete_text([{"role": "user", "content": "Analyze evidence"}])

    assert result == "grounded response"
    call = fake.chat.completions.calls[0]
    assert call["model"] == "hy3"
    assert call["stream"] is False
    assert call["temperature"] == 0.9
    assert call["top_p"] == 1.0
    assert call["max_tokens"] == 16000
    assert call["extra_body"] == {"chat_template_kwargs": {"reasoning_effort": "high"}}


@pytest.mark.asyncio
async def test_complete_text_uses_tokenhub_reasoning_contract() -> None:
    fake = FakeOpenAI(["grounded response"])
    settings = Settings(
        HY3_API_KEY="test-key",
        HY3_BASE_URL="https://tokenhub.tencentmaas.com/v1",
        HY3_REASONING_EFFORT="high",
        HY3_MAX_TOKENS=20000,
    )
    client = Hy3Client(settings, client=fake)

    await client.complete_text([{"role": "user", "content": "Analyze evidence"}])

    call = fake.chat.completions.calls[0]
    assert call["max_tokens"] == 20000
    assert call["extra_body"] == {"reasoning_effort": "high"}


@pytest.mark.asyncio
async def test_tokenhub_no_think_omits_reasoning_parameter() -> None:
    fake = FakeOpenAI(["direct response"])
    settings = Settings(
        HY3_API_KEY="test-key",
        HY3_BASE_URL="https://tokenhub.tencentmaas.com/v1",
        HY3_REASONING_EFFORT="no_think",
    )
    client = Hy3Client(settings, client=fake)

    await client.complete_text([{"role": "user", "content": "Answer directly"}])

    assert "extra_body" not in fake.chat.completions.calls[0]


@pytest.mark.asyncio
async def test_complete_structured_accepts_json_fence() -> None:
    fake = FakeOpenAI(['```json\n{"answer":"supported","confidence":0.9}\n```'])
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    result = await client.complete_structured(
        [{"role": "user", "content": "Return JSON"}],
        ExampleResponse,
    )

    assert result == ExampleResponse(answer="supported", confidence=0.9)
    assert len(fake.chat.completions.calls) == 1


@pytest.mark.asyncio
async def test_complete_structured_allows_deterministic_temperature_override() -> None:
    fake = FakeOpenAI(['{"answer":"supported","confidence":0.9}'])
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    await client.complete_structured(
        [{"role": "user", "content": "Return JSON"}],
        ExampleResponse,
        temperature=0.0,
    )

    assert fake.chat.completions.calls[0]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_complete_structured_repairs_once() -> None:
    fake = FakeOpenAI(["not-json", '{"answer":"repaired","confidence":0.7}'])
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    result = await client.complete_structured(
        [{"role": "user", "content": "Return JSON"}],
        ExampleResponse,
    )

    assert result.answer == "repaired"
    assert len(fake.chat.completions.calls) == 2
    repair_messages = fake.chat.completions.calls[1]["messages"]
    assert "JSON Schema" in repair_messages[-1]["content"]
    assert fake.chat.completions.calls[1]["temperature"] == 0.0
    assert fake.chat.completions.calls[1]["extra_body"] == {"chat_template_kwargs": {"reasoning_effort": "no_think"}}


@pytest.mark.asyncio
async def test_complete_structured_accepts_one_schema_valid_embedded_value() -> None:
    fake = FakeOpenAI(['Result:\n{"answer":"supported","confidence":0.9}\nDone.'])
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    result = await client.complete_structured(
        [{"role": "user", "content": "Return JSON"}],
        ExampleResponse,
    )

    assert result == ExampleResponse(answer="supported", confidence=0.9)
    assert len(fake.chat.completions.calls) == 1


@pytest.mark.asyncio
async def test_complete_structured_repairs_ambiguous_embedded_values() -> None:
    fake = FakeOpenAI(
        [
            '{"answer":"first","confidence":0.9}\n{"answer":"second","confidence":0.8}',
            '{"answer":"repaired","confidence":0.7}',
        ]
    )
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    result = await client.complete_structured(
        [{"role": "user", "content": "Return JSON"}],
        ExampleResponse,
    )

    assert result.answer == "repaired"
    assert len(fake.chat.completions.calls) == 2


@pytest.mark.asyncio
async def test_complete_structured_rejects_second_invalid_response() -> None:
    fake = FakeOpenAI(["not-json", '{"answer":"missing-confidence"}'])
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    with pytest.raises(StructuredOutputValidationError) as exc_info:
        await client.complete_structured(
            [{"role": "user", "content": "Return JSON"}],
            ExampleResponse,
        )

    assert exc_info.value.code == "STRUCTURED_OUTPUT_VALIDATION_ERROR"
    assert exc_info.value.retryable is True
    assert "missing-confidence" not in exc_info.value.message


@pytest.mark.asyncio
async def test_close_closes_injected_client() -> None:
    fake = FakeOpenAI(["unused"])
    client = Hy3Client(Settings(HY3_API_KEY="test-key"), client=fake)

    await client.close()

    assert fake.closed is True
