"""QueryResult and UnknownsEntry types for the M5 query layer (SPEC.md §4.6, data-model.md).

All five query operations return a QueryResult.  ``deployed_refs`` is always
``{}`` (never None); ``unknowns`` is always ``[]`` (never None).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Weakest-link ordering for confidence aggregation.
_CONFIDENCE_RANK: dict[str, int] = {"high": 2, "medium": 1, "low": 0}

# Least-trustworthy ordering for provenance aggregation.
# Lower rank = less trustworthy = wins the aggregate.
_PROVENANCE_RANK: dict[str, int] = {
    "declared": 3,
    "injected": 2,
    "observed": 1,
    "llm-judged": 0,
}


@dataclass
class UnknownsEntry:
    """One item in the unknowns list of a QueryResult."""
    kind: str
    description: str
    repo_id: str | None = None
    token: str | None = None
    candidates: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind, "description": self.description}
        if self.repo_id is not None:
            d["repo_id"] = self.repo_id
        if self.token is not None:
            d["token"] = self.token
        if self.candidates is not None:
            d["candidates"] = self.candidates
        return d


@dataclass
class QueryResult:
    """Top-level response object for all five query operations."""
    operation: str
    env: str
    results: list[dict[str, Any]] = field(default_factory=list)
    confidence: str = "high"
    provenance: str = "declared"
    deployed_refs: dict[str, str] = field(default_factory=dict)
    unknowns: list[UnknownsEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "env": self.env,
            "results": self.results,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "deployed_refs": self.deployed_refs,
            "unknowns": [u.to_dict() for u in self.unknowns],
            "metadata": self.metadata,
        }


def aggregate_confidence(items: list[str]) -> str:
    """Return the weakest confidence across all items (high > medium > low).

    Empty input → ``"high"`` (vacuously all edges are high-confidence).
    """
    if not items:
        return "high"
    min_rank = min(_CONFIDENCE_RANK.get(c, 0) for c in items)
    for conf, rank in sorted(_CONFIDENCE_RANK.items(), key=lambda kv: kv[1]):
        if rank == min_rank:
            return conf
    return "low"


def aggregate_provenance(items: list[str]) -> str:
    """Return the least trustworthy provenance across all items.

    Order (most → least trustworthy): declared > injected > observed > llm-judged.
    Empty input → ``"declared"``.
    """
    if not items:
        return "declared"
    min_rank = min(_PROVENANCE_RANK.get(p, 0) for p in items)
    for prov, rank in sorted(_PROVENANCE_RANK.items(), key=lambda kv: kv[1]):
        if rank == min_rank:
            return prov
    return "llm-judged"
