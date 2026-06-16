"""UNRESOLVED_REF prompt contract v1 (M9 FR-019).

Decision type: propose a concrete value for a reference the structured
pass could not resolve, or confirm it is unresolvable.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from tendril.llm.contracts.base import MalformedResponseError, PromptContract, PromptResponse
from tendril.plugins.base import LLMRequest

PROMPT_VERSION = "unresolved_ref/v1"


class UnresolvedRefResponse(BaseModel, PromptResponse):
    proposed_value: str | None  # null is valid — means unresolvable
    reasoning: str


class UnresolvedRefContract(PromptContract):

    def contract_version(self) -> str:
        return PROMPT_VERSION

    def build_prompt(self, item: Any) -> LLMRequest:
        goal = f"UNRESOLVED_REF:{item.get('consumer_ref_id', '')}"
        evidence = item.get("evidence", [])

        return LLMRequest(
            goal=goal,
            evidence=evidence,
            output_schema={
                "type": "object",
                "properties": {
                    "proposed_value": {"type": ["string", "null"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["proposed_value", "reasoning"],
            },
            max_files=20,
            max_bytes=50_000,
        )

    def validate_response(self, raw: dict[str, Any]) -> UnresolvedRefResponse:
        if "proposed_value" not in raw:
            raise MalformedResponseError(raw_response=raw, reason="'proposed_value' key is absent")

        reasoning = raw.get("reasoning", "")
        if not reasoning or not isinstance(reasoning, str) or not reasoning.strip():
            raise MalformedResponseError(raw_response=raw, reason="'reasoning' field is absent or empty")

        proposed = raw["proposed_value"]
        # null/None is valid; empty string is not
        if proposed is not None and (not isinstance(proposed, str) or proposed.strip() == ""):
            raise MalformedResponseError(
                raw_response=raw,
                reason="'proposed_value' must be null or a non-empty string",
            )

        return UnresolvedRefResponse(
            proposed_value=proposed,
            reasoning=reasoning,
        )
