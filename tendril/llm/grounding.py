"""GroundingStep — validate LLM proposals against the reverse index (M9 FR-006, FR-007).

Every LLM-proposed value must be verified against the reverse index before an edge
is written. Ungrounded proposals are rejected (no edge written, item marked
grounding-failed). This is the core "LLM proposes; grounding validates" invariant.

GroundingStep never raises — all errors are captured in GroundingResult.error.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GroundingResult:
    found: bool
    matched_identity: str | None
    index_locator: str | None
    error: str | None


class GroundingStep:
    """Look up a proposed value in the reverse index.

    ground() returns a GroundingResult and never raises.
    """

    def ground(
        self,
        proposed_value: str,
        reverse_index: object,
        env: str,
    ) -> GroundingResult:
        """Validate proposed_value against the reverse index for the given env.

        Args:
            proposed_value: The value proposed by the LLM (URL, package, etc.)
            reverse_index:  ReverseIndex instance with a lookup() method.
            env:            Canonical environment name.

        Returns:
            GroundingResult with found=True if the index confirms the value,
            found=False if no match, or found=False + error if lookup raised.
        """
        try:
            match = reverse_index.lookup(proposed_value, env)  # type: ignore[union-attr]
            if match:
                # lookup() returns a list[IndexEntry]
                entry = match[0]
                locator = f"index:{env}:{proposed_value}"
                return GroundingResult(
                    found=True,
                    matched_identity=entry.deployable_id,
                    index_locator=locator,
                    error=None,
                )
            return GroundingResult(found=False, matched_identity=None, index_locator=None, error=None)
        except Exception as exc:
            return GroundingResult(found=False, matched_identity=None, index_locator=None, error=str(exc))
