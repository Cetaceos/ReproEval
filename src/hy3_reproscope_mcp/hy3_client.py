"""Async OpenAI-compatible client for Hy3 inference."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .config import Settings
from .errors import Hy3APIError, Hy3TimeoutError, StructuredOutputValidationError

ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)

_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)


class Hy3Client:
    """Small, injectable wrapper around the OpenAI-compatible Hy3 endpoint."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client or AsyncOpenAI(
            base_url=settings.hy3_base_url,
            api_key=settings.require_api_key(),
            timeout=settings.hy3_timeout_seconds,
            max_retries=settings.hy3_max_retries,
        )

    async def complete_text(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Return one non-streaming Hy3 text completion."""

        effort = reasoning_effort or self.settings.hy3_reasoning_effort
        request: dict[str, Any] = {
            "model": self.settings.hy3_model,
            "messages": [dict(message) for message in messages],
            "temperature": self.settings.hy3_temperature if temperature is None else temperature,
            "top_p": self.settings.hy3_top_p,
            "max_tokens": self.settings.hy3_max_tokens,
            "stream": False,
        }
        extra_body = self._reasoning_body(effort)
        if extra_body:
            request["extra_body"] = extra_body
        try:
            response = await self._client.chat.completions.create(**request)
        except APITimeoutError as exc:
            raise Hy3TimeoutError(
                "The Hy3 request timed out.",
                hint="Retry the request or increase HY3_TIMEOUT_SECONDS.",
            ) from exc
        except APIStatusError as exc:
            status_code = exc.status_code
            raise Hy3APIError(
                f"The Hy3 API returned HTTP {status_code}.",
                hint="Check the endpoint, model, credentials, and service availability.",
                retryable=status_code == 429 or status_code >= 500,
            ) from exc
        except APIConnectionError as exc:
            raise Hy3APIError(
                "The Hy3 endpoint could not be reached.",
                hint="Check HY3_BASE_URL and network connectivity.",
            ) from exc

        if not response.choices:
            raise Hy3APIError("The Hy3 API returned no completion choices.", retryable=True)

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise Hy3APIError("The Hy3 API returned an empty completion.", retryable=True)
        return content.strip()

    def _reasoning_body(self, effort: str) -> dict[str, Any]:
        provider = self.settings.resolved_api_provider()
        if provider == "tokenhub":
            return {} if effort == "no_think" else {"reasoning_effort": effort}
        return {"chat_template_kwargs": {"reasoning_effort": effort}}

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[ResponseModelT],
        *,
        reasoning_effort: str | None = None,
        repair_once: bool = True,
    ) -> ResponseModelT:
        """Request JSON, validate it, and optionally make one bounded repair request."""

        raw_response = await self.complete_text(messages, reasoning_effort=reasoning_effort)
        try:
            return self._validate_json(raw_response, response_model)
        except (json.JSONDecodeError, ValidationError) as first_error:
            if not repair_once:
                raise self._structured_error(response_model, first_error) from first_error

        repair_messages = [
            *[dict(message) for message in messages],
            {"role": "assistant", "content": raw_response},
            {
                "role": "user",
                "content": (
                    "Return a corrected JSON value only. It must validate against this JSON Schema: "
                    + json.dumps(response_model.model_json_schema(), ensure_ascii=True)
                ),
            },
        ]
        repaired_response = await self.complete_text(
            repair_messages,
            reasoning_effort="no_think",
            temperature=0.0,
        )
        try:
            return self._validate_json(repaired_response, response_model)
        except (json.JSONDecodeError, ValidationError) as second_error:
            raise self._structured_error(response_model, second_error) from second_error

    @staticmethod
    def _validate_json(raw_response: str, response_model: type[ResponseModelT]) -> ResponseModelT:
        fence_match = _JSON_FENCE.fullmatch(raw_response)
        candidate = fence_match.group(1) if fence_match else raw_response
        try:
            payload = json.loads(candidate)
            return response_model.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as direct_error:
            validated: dict[str, ResponseModelT] = {}
            decoder = json.JSONDecoder()
            for index, character in enumerate(candidate):
                if character not in "[{":
                    continue
                try:
                    embedded_payload, _ = decoder.raw_decode(candidate[index:])
                    model = response_model.model_validate(embedded_payload)
                except (json.JSONDecodeError, ValidationError):
                    continue
                canonical = model.model_dump_json()
                validated[canonical] = model

            if len(validated) == 1:
                return next(iter(validated.values()))
            raise direct_error

    @staticmethod
    def _structured_error(
        response_model: type[BaseModel],
        error: json.JSONDecodeError | ValidationError,
    ) -> StructuredOutputValidationError:
        detail = "invalid JSON" if isinstance(error, json.JSONDecodeError) else "schema validation failed"
        return StructuredOutputValidationError(
            f"Hy3 output for {response_model.__name__} could not be accepted: {detail}.",
            hint="Retry the tool. If the problem persists, inspect the configured model and prompt version.",
            retryable=True,
        )

    async def close(self) -> None:
        """Close the underlying async HTTP client."""

        await self._client.close()
