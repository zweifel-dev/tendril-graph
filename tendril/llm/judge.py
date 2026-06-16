"""LLMJudge — post-processor that runs after the structured pass (M9 FR-002–009).

Consumes a TraversalResult, processes each unresolved/ambiguous item through
the LLM pipeline (redact → residency gate → contract → cache → complete →
validate → ground → write edge), and returns an augmented TraversalResult.

Structured-mode edges are NEVER modified (FR-016).
All LLM calls use temperature=0 (enforced in OpenAICompatibleProvider).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tendril.config import LLMConfig
from tendril.llm.cache import DiskResponseCache
from tendril.llm.contracts.ambiguous_match import AmbiguousMatchContract
from tendril.llm.contracts.base import MalformedResponseError
from tendril.llm.contracts.identity_class import IdentityClassContract
from tendril.llm.contracts.unresolved_ref import UnresolvedRefContract
from tendril.llm.grounding import GroundingStep
from tendril.llm.redactor import ResidencyGate, SecretRedactor
from tendril.models.graph import DependsOn
from tendril.models.ir import Confidence, Evidence, Provenance
from tendril.plugins.base import LLMProvider

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision type constants (match values expected in TraversalResult.unresolved)
# ---------------------------------------------------------------------------

DT_AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
DT_UNRESOLVED_REF = "UNRESOLVED_REF"
DT_IDENTITY_CLASS = "IDENTITY_CLASS"


@dataclass
class ReasoningTrace:
    trace_id: str
    decision_type: str
    contract_version: str
    redacted_request: dict[str, Any]
    raw_response: dict[str, Any] | None
    grounding_result: dict[str, Any] | None
    disposition: str  # "accepted"|"rejected"|"ambiguous-kept"|"malformed"|"grounding-failed"
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "decision_type": self.decision_type,
            "contract_version": self.contract_version,
            "redacted_request": self.redacted_request,
            "raw_response": self.raw_response,
            "grounding_result": self.grounding_result,
            "disposition": self.disposition,
            "created_at": self.created_at,
        }


class LLMJudge:
    """Post-processor: run the LLM hybrid pass on a completed TraversalResult."""

    def __init__(
        self,
        cache: DiskResponseCache,
        redactor: SecretRedactor,
        residency_gate: ResidencyGate,
        grounding_step: GroundingStep | None = None,
    ) -> None:
        self._cache = cache
        self._redactor = redactor
        self._gate = residency_gate
        self._grounding = grounding_step or GroundingStep()
        self._contracts = {
            DT_AMBIGUOUS_MATCH: AmbiguousMatchContract(),
            DT_UNRESOLVED_REF: UnresolvedRefContract(),
            DT_IDENTITY_CLASS: IdentityClassContract(),
        }

    def run(
        self,
        result: Any,  # TraversalResult — avoid circular import
        reverse_index: Any,
        provider: LLMProvider,
        config: LLMConfig,
    ) -> Any:
        """Process unresolved items and return augmented TraversalResult.

        Structured edges in result.edges are never modified.
        """
        remaining_unresolved: list[dict[str, Any]] = []
        new_edges: list[DependsOn] = []

        for item in result.unresolved:
            processed = self._process_item(
                item, reverse_index, provider, config,
                new_edges, remaining_unresolved,
            )
            if not processed:
                remaining_unresolved.append(item)

        result.edges = result.edges + new_edges
        result.unresolved = remaining_unresolved
        return result

    def _process_item(
        self,
        item: dict[str, Any],
        reverse_index: Any,
        provider: LLMProvider,
        config: LLMConfig,
        new_edges: list[DependsOn],
        remaining_unresolved: list[dict[str, Any]],
    ) -> bool:
        """Process one unresolved item. Returns True if item was consumed (edge written or definitively skipped)."""
        from tendril.connectors.llm.openai_provider import LLMError, LLMErrorKind

        decision_type = item.get("decision_type", DT_UNRESOLVED_REF)
        consumer_ref_id = item.get("consumer_ref_id") or item.get("ref") or ""
        env = item.get("env", "")

        # Skip already-secret items
        if item.get("reason") == "is-secret":
            item_copy = dict(item)
            item_copy["reason"] = "unresolvable-redacted"
            remaining_unresolved.append(item_copy)
            return True

        # --- Budget check ---
        evidence_raw: list[dict[str, Any]] = item.get("evidence", [])
        if not self._check_budget(evidence_raw, config):
            item_copy = dict(item)
            item_copy["reason"] = "budget-exceeded"
            remaining_unresolved.append(item_copy)
            log.warning("LLM budget exceeded for item %s — skipping", consumer_ref_id)
            return True

        # --- Collect known secrets from evidence ---
        known_secrets: set[str] = {
            e["value"]
            for e in evidence_raw
            if isinstance(e, dict) and e.get("is_secret") and e.get("value")
        }

        # --- Redaction pass ---
        redacted_evidence = self._redactor.redact(evidence_raw, known_secrets)

        # --- Residency gate ---
        goal = f"{decision_type}:{consumer_ref_id}"
        gate_result = self._gate.evaluate(redacted_evidence, goal)
        if not gate_result.allowed:
            item_copy = dict(item)
            item_copy["reason"] = "unresolvable-redacted"
            remaining_unresolved.append(item_copy)
            log.warning(
                "LLM call blocked by residency gate for %s: %s",
                consumer_ref_id, gate_result.trigger,
            )
            return True

        # --- Select contract ---
        contract = self._contracts.get(decision_type)
        if contract is None:
            log.warning("No contract for decision_type %r — skipping", decision_type)
            return False

        # --- Cache lookup ---
        locators = [e.get("locator", str(e)) for e in redacted_evidence if isinstance(e, dict)]
        cached_response = self._cache.get(goal, locators)

        if cached_response is not None:
            raw_response = cached_response
            log.debug("LLM cache hit for %s", goal)
        else:
            # --- Build and execute LLM call ---
            llm_req = contract.build_prompt({
                **item,
                "evidence": redacted_evidence,
                "consumer_ref_id": consumer_ref_id,
            })

            try:
                llm_resp = provider.complete(llm_req)
                raw_response = llm_resp.structured or {}
                self._cache.put(goal, locators, raw_response, contract.contract_version())
            except LLMError as exc:
                item_copy = dict(item)
                if exc.kind == LLMErrorKind.RATE_LIMITED:
                    item_copy["reason"] = "rate-limited"
                    log.warning("LLM rate-limited for %s", consumer_ref_id)
                else:
                    item_copy["reason"] = "llm-error"
                    log.warning("LLM error for %s: %s", consumer_ref_id, exc)
                remaining_unresolved.append(item_copy)
                return True

        # --- Validate response ---
        try:
            parsed = contract.validate_response(raw_response)
        except MalformedResponseError as exc:
            item_copy = dict(item)
            item_copy["reason"] = "llm-error"
            remaining_unresolved.append(item_copy)
            log.warning("Malformed LLM response for %s: %s | raw=%s", consumer_ref_id, exc, raw_response)
            return True

        # --- Extract proposed value ---
        proposed_value = self._extract_proposed_value(parsed, decision_type, item)

        if proposed_value is None:
            # LLM confirmed unresolvable (e.g. proposed_value=null or keep-ambiguous)
            item_copy = dict(item)
            if decision_type == DT_AMBIGUOUS_MATCH:
                item_copy["ambiguous"] = True
                # Keep existing ambiguous candidate edges, record trace
                trace = self._write_trace(
                    decision_type=decision_type,
                    contract=contract,
                    redacted_evidence=redacted_evidence,
                    raw_response=raw_response,
                    grounding=None,
                    disposition="ambiguous-kept",
                    config=config,
                )
                item_copy["llm_trace"] = trace.trace_id
                log.debug("Ambiguous item kept for %s (trace=%s)", consumer_ref_id, trace.trace_id)
            remaining_unresolved.append(item_copy)
            return True

        # --- Grounding ---
        grounding = self._grounding.ground(proposed_value, reverse_index, env)

        if not grounding.found:
            item_copy = dict(item)
            item_copy["reason"] = "grounding-failed"
            remaining_unresolved.append(item_copy)
            log.warning(
                "LLM proposal '%s' for %s failed grounding (error=%s)",
                proposed_value, consumer_ref_id, grounding.error,
            )
            return True

        # --- Write edge ---
        trace = self._write_trace(
            decision_type=decision_type,
            contract=contract,
            redacted_evidence=redacted_evidence,
            raw_response=raw_response,
            grounding=grounding,
            disposition="accepted",
            config=config,
        )

        edge_evidence = list(item.get("evidence", []))
        if grounding.index_locator:
            edge_evidence.append({"source_type": "index", "locator": grounding.index_locator})

        edge = DependsOn(
            from_id=item.get("from_id", ""),
            to_id=grounding.matched_identity or proposed_value,
            env=env,
            provenance=Provenance.LLM_JUDGED,
            confidence=Confidence.LOW,
            evidence=[
                Evidence(source_type=e.get("source_type", "evidence"), locator=e.get("locator", str(e)))
                for e in edge_evidence
                if isinstance(e, dict)
            ],
            deployed_ref=item.get("deployed_ref", ""),
            llm_trace=trace.trace_id,
        )
        new_edges.append(edge)
        log.info(
            "LLM edge written: %s -> %s @%s [trace=%s]",
            edge.from_id, edge.to_id, edge.env, trace.trace_id,
        )
        return True

    def _extract_proposed_value(
        self,
        parsed: Any,
        decision_type: str,
        item: dict[str, Any],
    ) -> str | None:
        """Return the proposed value from a parsed contract response, or None."""
        if decision_type == DT_AMBIGUOUS_MATCH:
            if parsed.decision == "keep-ambiguous":
                return None
            return parsed.candidate_id

        if decision_type == DT_UNRESOLVED_REF:
            return parsed.proposed_value  # may be None

        if decision_type == DT_IDENTITY_CLASS:
            # IdentityClass tells us how to resolve, not what to resolve to
            # Apply the classified type to the original raw_value
            return item.get("raw_value") or item.get("ref")

        return None

    def _check_budget(self, evidence: list[dict[str, Any]], config: LLMConfig) -> bool:
        """Return True if evidence is within budget limits."""
        if len(evidence) > config.max_evidence_files:
            return False
        total_bytes = sum(
            len(json.dumps(e).encode("utf-8"))
            for e in evidence
            if isinstance(e, dict)
        )
        if total_bytes > config.max_evidence_bytes:
            return False
        return True

    def _write_trace(
        self,
        decision_type: str,
        contract: Any,
        redacted_evidence: list[dict[str, Any]],
        raw_response: dict[str, Any] | None,
        grounding: Any,
        disposition: str,
        config: LLMConfig,
    ) -> ReasoningTrace:
        """Write a ReasoningTrace JSON file and return the trace object."""
        trace_id = str(uuid.uuid4())
        trace = ReasoningTrace(
            trace_id=trace_id,
            decision_type=decision_type,
            contract_version=contract.contract_version(),
            redacted_request={"evidence": redacted_evidence},
            raw_response=raw_response,
            grounding_result=grounding.__dict__ if grounding else None,
            disposition=disposition,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        traces_dir = Path(config.cache_path).expanduser() / "traces"
        try:
            traces_dir.mkdir(parents=True, exist_ok=True)
            (traces_dir / f"{trace_id}.json").write_text(
                json.dumps(trace.as_dict(), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("Could not write reasoning trace %s: %s", trace_id, exc)

        return trace
