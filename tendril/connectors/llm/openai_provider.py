"""OpenAI-compatible LLM provider for Tendril hybrid mode (M9).

Implements the LLMProvider ABC using the openai SDK with base_url override,
allowing any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, Azure,
Bedrock, self-hosted) to be used BYOK.

All requests use temperature=0 for reproducibility (FR-010).
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any

from tendril.config import LLMConfig
from tendril.plugins.base import LLMProvider, LLMRequest, LLMResponse, Capabilities

log = logging.getLogger(__name__)


class LLMErrorKind(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate-limited"
    ENDPOINT_ERROR = "endpoint-error"


class LLMError(Exception):
    """Raised by OpenAICompatibleProvider.complete() on any LLM call failure."""
    def __init__(self, kind: LLMErrorKind, detail: str = "") -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(f"LLMError({kind.value}): {detail}")


class OpenAICompatibleProvider(LLMProvider):
    """LLMProvider backed by any OpenAI Chat Completions compatible endpoint."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    def id(self) -> str:
        return "openai-compatible"

    def capabilities(self) -> Capabilities:
        return {"chat_completions": True, "structured_output": True}

    def complete(self, req: LLMRequest) -> LLMResponse:
        """Call the configured endpoint and return a structured response.

        Raises:
            LLMError(TIMEOUT)       — request exceeded timeout_seconds
            LLMError(RATE_LIMITED)  — HTTP 429
            LLMError(ENDPOINT_ERROR) — any other HTTP or connection error
        """
        import openai

        client = openai.OpenAI(
            base_url=self._config.endpoint,
            api_key=self._config.api_key,
            timeout=float(self._config.timeout_seconds),
        )

        from openai.types.chat import ChatCompletionMessageParam
        messages: list[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    "You are a dependency-graph analysis assistant. "
                    "Respond only with valid JSON matching the requested schema. "
                    "Never fabricate values — only propose what the evidence supports."
                ),
            },
            {
                "role": "user",
                "content": self._build_user_message(req),
            },
        ]

        model = self._config.model or ""
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except openai.APITimeoutError as exc:
            raise LLMError(LLMErrorKind.TIMEOUT, str(exc)) from exc
        except openai.RateLimitError as exc:
            raise LLMError(LLMErrorKind.RATE_LIMITED, str(exc)) from exc
        except (openai.APIConnectionError, openai.APIStatusError, openai.OpenAIError) as exc:
            raise LLMError(LLMErrorKind.ENDPOINT_ERROR, str(exc)) from exc

        trace_id = str(uuid.uuid4())
        raw_content = response.choices[0].message.content or "{}"

        import json
        try:
            structured = json.loads(raw_content)
        except json.JSONDecodeError:
            structured = {}

        return LLMResponse(
            content=raw_content,
            structured=structured,
            trace_id=trace_id,
            usage=dict(response.usage.__dict__) if response.usage else None,
        )

    @staticmethod
    def _build_user_message(req: LLMRequest) -> str:
        import json
        parts: list[str] = [f"Goal: {req.goal}", "", "Evidence:"]
        for item in req.evidence:
            parts.append(json.dumps(item))
        if req.output_schema:
            parts.extend(["", "Required JSON output schema:", json.dumps(req.output_schema)])
        return "\n".join(parts)
