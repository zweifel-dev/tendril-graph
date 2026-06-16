"""PromptContract ABC — versioned prompt/response contract for LLM calls (M9).

Each contract type (AMBIGUOUS_MATCH, UNRESOLVED_REF, IDENTITY_CLASS) implements
this ABC. The version string is part of the cache key, so it must change whenever
the prompt structure or expected response schema changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from tendril.plugins.base import LLMRequest


@dataclass
class MalformedResponseError(Exception):
    """Raised by validate_response() when required fields are absent or invalid."""
    raw_response: dict[str, Any]
    reason: str

    def __str__(self) -> str:
        return f"MalformedResponseError: {self.reason}"


class PromptResponse:
    """Base class for typed prompt responses. Subclasses add contract-specific fields."""
    pass


class PromptContract(ABC):
    """Versioned prompt/response contract.

    Implementations must be stateless — all inputs come through build_prompt().
    """

    @abstractmethod
    def contract_version(self) -> str:
        """Return the contract version string (e.g. 'ambiguous_match/v1').

        Changing this invalidates existing cache entries for this contract.
        """
        ...

    @abstractmethod
    def build_prompt(self, item: Any) -> LLMRequest:
        """Assemble an LLMRequest from a judge item."""
        ...

    @abstractmethod
    def validate_response(self, raw: dict[str, Any]) -> PromptResponse:
        """Validate and parse the raw LLM response dict.

        Raises MalformedResponseError if any required field is absent, empty,
        or semantically invalid.
        """
        ...
