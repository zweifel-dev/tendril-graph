"""IDENTITY_CLASS prompt contract v1 (M9 FR-019).

Decision type: classify an unrecognised reference value into one of the
known identity classes so the resolver can apply the correct matching logic.

Note: the JSON response field is 'class' but the Python model attribute is
'class_' to avoid the reserved keyword collision.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tendril.llm.contracts.base import MalformedResponseError, PromptContract, PromptResponse
from tendril.plugins.base import LLMRequest

PROMPT_VERSION = "identity_class/v1"

_VALID_CLASSES = {"url", "package", "artifact", "unknown"}


class IdentityClassResponse(BaseModel, PromptResponse):
    class_: str = Field(alias="class")
    reasoning: str

    model_config = {"populate_by_name": True}


class IdentityClassContract(PromptContract):

    def contract_version(self) -> str:
        return PROMPT_VERSION

    def build_prompt(self, item: Any) -> LLMRequest:
        goal = f"IDENTITY_CLASS:{item.get('consumer_ref_id', '')}"
        evidence = item.get("evidence", [])

        return LLMRequest(
            goal=goal,
            evidence=evidence,
            output_schema={
                "type": "object",
                "properties": {
                    "class": {"type": "string", "enum": sorted(_VALID_CLASSES)},
                    "reasoning": {"type": "string"},
                },
                "required": ["class", "reasoning"],
            },
            max_files=20,
            max_bytes=50_000,
        )

    def validate_response(self, raw: dict[str, Any]) -> IdentityClassResponse:
        class_val = raw.get("class", "")
        if class_val not in _VALID_CLASSES:
            raise MalformedResponseError(
                raw_response=raw,
                reason=f"'class' must be one of {sorted(_VALID_CLASSES)}, got {class_val!r}",
            )

        reasoning = raw.get("reasoning", "")
        if not reasoning or not isinstance(reasoning, str) or not reasoning.strip():
            raise MalformedResponseError(raw_response=raw, reason="'reasoning' field is absent or empty")

        return IdentityClassResponse(**{"class": class_val, "reasoning": reasoning})
