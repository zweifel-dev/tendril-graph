"""AMBIGUOUS_MATCH prompt contract v1 (M9 FR-019).

Decision type: choose among two or more candidate identities,
or keep the ambiguous state if the evidence does not discriminate.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, field_validator

from tendril.llm.contracts.base import MalformedResponseError, PromptContract, PromptResponse
from tendril.plugins.base import LLMRequest

PROMPT_VERSION = "ambiguous_match/v1"


class AmbiguousMatchResponse(BaseModel, PromptResponse):
    decision: str  # "keep-ambiguous" | "ground-to-candidate"
    candidate_id: str | None = None
    reasoning: str

    @field_validator("decision")
    @classmethod
    def _valid_decision(cls, v: str) -> str:
        if v not in ("keep-ambiguous", "ground-to-candidate"):
            raise ValueError(f"decision must be 'keep-ambiguous' or 'ground-to-candidate', got {v!r}")
        return v


class AmbiguousMatchContract(PromptContract):

    def contract_version(self) -> str:
        return PROMPT_VERSION

    def build_prompt(self, item: Any) -> LLMRequest:
        goal = f"AMBIGUOUS_MATCH:{item.get('consumer_ref_id', '')}"
        candidates = item.get("candidates", [])
        evidence = item.get("evidence", [])

        prompt_lines = [
            f"Goal: {goal}",
            "",
            "The structured analysis pass found multiple candidate identities for this "
            "consumer reference. Use the evidence to determine which candidate is the "
            "correct match, or indicate that the reference remains ambiguous.",
            "",
            f"Candidates ({len(candidates)}):",
        ]
        for c in candidates:
            prompt_lines.append(f"  - {c}")
        prompt_lines += [
            "",
            "Required JSON response:",
            json.dumps({
                "decision": "<'keep-ambiguous' | 'ground-to-candidate'>",
                "candidate_id": "<candidate_id from list above, or null if keep-ambiguous>",
                "reasoning": "<non-empty explanation>",
            }),
        ]

        return LLMRequest(
            goal=goal,
            evidence=evidence,
            output_schema={
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "candidate_id": {"type": ["string", "null"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["decision", "reasoning"],
            },
            max_files=20,
            max_bytes=50_000,
        )

    def validate_response(self, raw: dict[str, Any]) -> AmbiguousMatchResponse:
        reasoning = raw.get("reasoning", "")
        if not reasoning or not isinstance(reasoning, str) or not reasoning.strip():
            raise MalformedResponseError(raw_response=raw, reason="'reasoning' field is absent or empty")

        decision = raw.get("decision", "")
        if decision not in ("keep-ambiguous", "ground-to-candidate"):
            raise MalformedResponseError(
                raw_response=raw,
                reason=f"'decision' must be 'keep-ambiguous' or 'ground-to-candidate', got {decision!r}",
            )

        candidate_id = raw.get("candidate_id")
        if decision == "ground-to-candidate" and not candidate_id:
            raise MalformedResponseError(
                raw_response=raw,
                reason="'candidate_id' must be present and non-empty when decision is 'ground-to-candidate'",
            )

        return AmbiguousMatchResponse(
            decision=decision,
            candidate_id=candidate_id,
            reasoning=reasoning,
        )
