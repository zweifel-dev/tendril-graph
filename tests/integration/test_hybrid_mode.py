"""Integration tests for M9 LLM hybrid mode (T023–T034).

All tests use MockLLMProvider — zero live LLM calls.
MockLLMProvider returns canned responses from complete_responses.json keyed
by contract version (the item's decision_type maps to the fixture key).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tendril.config import LLMConfig
from tendril.connectors.llm.openai_provider import LLMError, LLMErrorKind
from tendril.core.index import ReverseIndex
from tendril.llm.cache import DiskResponseCache
from tendril.llm.judge import LLMJudge
from tendril.llm.redactor import ResidencyGate, SecretRedactor
from tendril.models.graph import DependsOn
from tendril.models.ir import Confidence, Evidence, IdentityClass, Provenance, ProviderIdentity
from tendril.plugins.base import LLMProvider, LLMRequest, LLMResponse, Capabilities
from tendril.core.traversal import TraversalResult

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "conformance" / "llm" / "complete_responses.json"
M9_FIXTURE = Path(__file__).parent.parent / "fixtures" / "golden" / "m9-hybrid"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_canned() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_bytes())


DECISION_TYPE_TO_CONTRACT_KEY = {
    "AMBIGUOUS_MATCH": "ambiguous_match/v1",
    "UNRESOLVED_REF": "unresolved_ref/v1",
    "IDENTITY_CLASS": "identity_class/v1",
}


class MockLLMProvider(LLMProvider):
    """Returns canned fixture responses keyed by contract version."""

    def __init__(self, canned: dict[str, Any]) -> None:
        self._canned = canned
        self.call_count = 0
        self.captured_requests: list[LLMRequest] = []

    def id(self) -> str:
        return "mock-llm"

    def capabilities(self) -> Capabilities:
        return {}

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.captured_requests.append(req)
        # Derive contract version from goal prefix
        goal_prefix = req.goal.split(":")[0]
        contract_key = DECISION_TYPE_TO_CONTRACT_KEY.get(goal_prefix, "unresolved_ref/v1")
        raw = self._canned.get(contract_key, {})
        import uuid
        return LLMResponse(
            content=json.dumps(raw),
            structured=dict(raw),
            trace_id=str(uuid.uuid4()),
        )


def _make_index_with_sidecar() -> ReverseIndex:
    """Return a ReverseIndex with sidecar-service registered at https://sidecar.internal."""
    index = ReverseIndex()
    index.add(
        deployable_id="sidecar-service",
        repo_full_name="github:myorg/sidecar-service",
        identities=[
            ProviderIdentity(
                identity_class=IdentityClass.NETWORK,
                value="https://sidecar.internal",
                env="prod",
                evidence=[Evidence(source_type="vcs", locator="github:myorg/sidecar-service:homepage")],
            )
        ],
    )
    return index


def _make_unresolved_item(
    consumer_ref_id: str = "SIDECAR_URL",
    decision_type: str = "UNRESOLVED_REF",
    from_id: str = "github:myorg/anchor-repo",
    env: str = "prod",
    is_secret: bool = False,
) -> dict[str, Any]:
    return {
        "consumer_ref_id": consumer_ref_id,
        "decision_type": decision_type,
        "from_id": from_id,
        "env": env,
        "reason": "not-found",
        "evidence": [
            {
                "source_type": "cicd",
                "locator": f"github_actions:anchor-repo:{consumer_ref_id}",
                "key": consumer_ref_id,
                "value": "https://sidecar.internal",
                "is_secret": is_secret,
            }
        ],
        "candidates": ["github:myorg/sidecar-service"],
        "raw_value": "https://sidecar.internal",
    }


def _make_config(cache_path: str) -> LLMConfig:
    return LLMConfig(
        endpoint="http://localhost:11434/v1",
        model="test-model",
        api_key="test-key",
        timeout_seconds=60,
        max_evidence_files=20,
        max_evidence_bytes=50_000,
        cache_path=cache_path,
    )


# ---------------------------------------------------------------------------
# T023 — SC-001: unknowns reduced after hybrid pass
# ---------------------------------------------------------------------------

class TestSC001UnknownsReduced:
    def test_sc001_unknowns_reduced(self, tmp_path: Path) -> None:
        """Hybrid pass reduces unknowns list and writes at least one llm-judged edge."""
        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        # Structured result: one unresolved item
        result = TraversalResult()
        result.unresolved = [_make_unresolved_item()]
        structured_unknowns_count = len(result.unresolved)

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, mock_provider, config)

        # Unknowns count must decrease
        assert len(result.unresolved) < structured_unknowns_count

        # At least one llm-judged edge
        llm_edges = [e for e in result.edges if e.provenance == Provenance.LLM_JUDGED]
        assert len(llm_edges) >= 1

        edge = llm_edges[0]
        assert edge.confidence == Confidence.LOW
        assert edge.llm_trace is not None
        assert len(edge.evidence) > 0

    def test_sc001_edge_has_correct_fields(self, tmp_path: Path) -> None:
        """Written edge has provenance=llm-judged, confidence=low, llm_trace, evidence."""
        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        result = TraversalResult()
        result.unresolved = [_make_unresolved_item()]

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, mock_provider, config)

        llm_edges = [e for e in result.edges if e.provenance == Provenance.LLM_JUDGED]
        assert llm_edges, "Expected at least one llm-judged edge"
        edge = llm_edges[0]
        assert edge.provenance.value == "llm-judged"
        assert edge.confidence.value == "low"
        assert edge.llm_trace is not None
        assert edge.evidence  # non-empty


# ---------------------------------------------------------------------------
# T007 — US2: LLM-grounded edge to_id uses repo_full_name format
# ---------------------------------------------------------------------------

class TestLLMGroundingToIdFormat:
    def test_llm_edge_to_id_is_repo_full_name(self, tmp_path: Path) -> None:
        """LLM-grounded edge to_id must match provider:org/name, not a bare slug."""
        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        result = TraversalResult()
        result.unresolved = [_make_unresolved_item()]

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, mock_provider, config)

        llm_edges = [e for e in result.edges if e.provenance == Provenance.LLM_JUDGED]
        assert llm_edges, "Expected at least one llm-judged edge"
        for edge in llm_edges:
            # to_id must be in provider:org/name format (e.g. github:myorg/sidecar-service)
            assert ":" in edge.to_id, f"to_id '{edge.to_id}' missing provider prefix"
            assert "/" in edge.to_id, f"to_id '{edge.to_id}' missing org/name separator"


# ---------------------------------------------------------------------------
# T025 / T026 — US3: endpoint error and no-config graceful degradation
# ---------------------------------------------------------------------------

class TestSC005GracefulDegradation:
    def test_sc005_endpoint_error_marks_llm_error(self, tmp_path: Path) -> None:
        """When provider raises LLMError, item is marked llm-error and no edge is written."""
        class FailingProvider(LLMProvider):
            def id(self) -> str:
                return "failing"
            def capabilities(self) -> Capabilities:
                return {}
            def complete(self, req: LLMRequest) -> LLMResponse:
                raise LLMError(LLMErrorKind.ENDPOINT_ERROR, "connection refused")

        index = _make_index_with_sidecar()
        result = TraversalResult()
        result.unresolved = [_make_unresolved_item()]

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, FailingProvider(), config)

        assert not any(e.provenance == Provenance.LLM_JUDGED for e in result.edges)
        assert len(result.unresolved) == 1
        assert result.unresolved[0]["reason"] == "llm-error"

    def test_sc005_rate_limit_marks_rate_limited(self, tmp_path: Path) -> None:
        """HTTP 429 response marks item as rate-limited."""
        class RateLimitedProvider(LLMProvider):
            def id(self) -> str:
                return "rate-limited"
            def capabilities(self) -> Capabilities:
                return {}
            def complete(self, req: LLMRequest) -> LLMResponse:
                raise LLMError(LLMErrorKind.RATE_LIMITED, "429 Too Many Requests")

        index = _make_index_with_sidecar()
        result = TraversalResult()
        result.unresolved = [_make_unresolved_item()]

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, RateLimitedProvider(), config)

        assert result.unresolved[0]["reason"] == "rate-limited"


# ---------------------------------------------------------------------------
# T027 — US4: SC-003 provenance labels
# ---------------------------------------------------------------------------

class TestSC003ProvenanceLabels:
    def test_sc003_provenance_labels(self, tmp_path: Path) -> None:
        """Every llm-judged edge has confidence=low and llm_trace; structured edges unchanged."""
        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        # Add a pre-existing structured edge
        structured_edge = DependsOn(
            from_id="github:myorg/anchor-repo",
            to_id="github:myorg/other-service",
            env="prod",
            provenance=Provenance.DECLARED,
            confidence=Confidence.HIGH,
            evidence=[Evidence(source_type="vcs", locator="anchor-repo:src/config.py:12")],
        )

        result = TraversalResult()
        result.edges = [structured_edge]
        result.unresolved = [_make_unresolved_item()]

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, mock_provider, config)

        # Structured edge must be unchanged
        declared_edges = [e for e in result.edges if e.provenance == Provenance.DECLARED]
        assert len(declared_edges) == 1
        assert declared_edges[0].confidence == Confidence.HIGH
        assert declared_edges[0].llm_trace is None

        # LLM-judged edges must have correct labels
        llm_edges = [e for e in result.edges if e.provenance == Provenance.LLM_JUDGED]
        for edge in llm_edges:
            assert edge.confidence == Confidence.LOW
            assert edge.llm_trace is not None


# ---------------------------------------------------------------------------
# T029 — US5: SC-004 cache hit — second build issues zero new LLM requests
# ---------------------------------------------------------------------------

class TestSC004CacheHit:
    def test_sc004_cache_hit(self, tmp_path: Path) -> None:
        """Second build against same fixture produces zero new LLM calls."""
        canned = _load_canned()
        index = _make_index_with_sidecar()

        def _run(provider: MockLLMProvider) -> TraversalResult:
            result = TraversalResult()
            result.unresolved = [_make_unresolved_item()]
            config = _make_config(str(tmp_path))
            cache = DiskResponseCache(str(tmp_path))
            judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
            return judge.run(result, index, provider, config)

        provider1 = MockLLMProvider(canned)
        result1 = _run(provider1)
        call_count_1 = provider1.call_count

        provider2 = MockLLMProvider(canned)
        result2 = _run(provider2)
        call_count_2 = provider2.call_count

        assert call_count_1 >= 1, "First build must make at least one LLM call"
        assert call_count_2 == 0, "Second build must make zero LLM calls (cache hit)"

        # Edge sets must be identical (same from_id, to_id, env, provenance)
        def edge_key(e: DependsOn) -> tuple:
            return (e.from_id, e.to_id, e.env, e.provenance.value)

        keys1 = sorted(edge_key(e) for e in result1.edges)
        keys2 = sorted(edge_key(e) for e in result2.edges)
        assert keys1 == keys2


# ---------------------------------------------------------------------------
# T030 — US5: deterministic output ordering
# ---------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_deterministic_ordering(self, tmp_path: Path) -> None:
        """Two runs with same inputs produce identical sorted edge lists."""
        canned = _load_canned()
        index = _make_index_with_sidecar()

        def _run() -> list[tuple]:
            provider = MockLLMProvider(canned)
            result = TraversalResult()
            result.unresolved = [_make_unresolved_item()]
            config = _make_config(str(tmp_path))
            cache = DiskResponseCache(str(tmp_path))
            judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
            r = judge.run(result, index, provider, config)
            return sorted(
                (e.from_id, e.to_id, e.env, e.provenance.value, e.confidence.value)
                for e in r.edges
            )

        run1 = _run()
        run2 = _run()
        assert run1 == run2


# ---------------------------------------------------------------------------
# T033 — SC-002: secret redaction — secret value absent from LLM request
# ---------------------------------------------------------------------------

class TestSC002SecretRedaction:
    def test_sc002_secret_redaction(self, tmp_path: Path) -> None:
        """Secret value from fixture must not appear in any captured LLM request payload."""
        SECRET_RAW_VALUE = "tok_live_abc123"

        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        # Item with a secret in evidence
        item = _make_unresolved_item()
        item["evidence"].append({
            "source_type": "cicd",
            "locator": "github_actions:anchor-repo:SECRET_TOKEN",
            "key": "SECRET_TOKEN",
            "value": SECRET_RAW_VALUE,
            "is_secret": True,
        })

        result = TraversalResult()
        result.unresolved = [item]

        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        judge.run(result, index, mock_provider, config)

        # Inspect captured request payloads
        for req in mock_provider.captured_requests:
            payload_str = json.dumps([e for e in req.evidence])
            assert SECRET_RAW_VALUE not in payload_str, (
                f"Secret value appeared in LLM request payload: {payload_str[:200]}"
            )
            assert "[REDACTED]" in payload_str


# ---------------------------------------------------------------------------
# T033-b — Budget exceeded
# ---------------------------------------------------------------------------

class TestBudgetExceeded:
    def test_budget_exceeded_skips_item(self, tmp_path: Path) -> None:
        """Items exceeding evidence budget are skipped with reason=budget-exceeded."""
        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        item = _make_unresolved_item()
        # Add enough evidence to exceed max_evidence_files=1
        item["evidence"] = [
            {"source_type": "cicd", "locator": f"file:{i}", "key": f"VAR_{i}", "value": "x"}
            for i in range(50)
        ]

        result = TraversalResult()
        result.unresolved = [item]

        config = _make_config(str(tmp_path))
        config.max_evidence_files = 1  # very low budget
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, mock_provider, config)

        assert result.unresolved[0]["reason"] == "budget-exceeded"
        assert mock_provider.call_count == 0


# ---------------------------------------------------------------------------
# T032 — SC-006: explain_edge returns llm_trace for LLM-judged edges
# ---------------------------------------------------------------------------

class TestSC006ExplainEdge:
    def test_sc006_explain_edge_trace(self, tmp_path: Path) -> None:
        """explain_edge for an llm-judged edge returns the reasoning trace."""
        from tendril.query.engine import QueryEngine
        from tendril.store.kuzu_store import KuzuStore

        canned = _load_canned()
        mock_provider = MockLLMProvider(canned)
        index = _make_index_with_sidecar()

        # Run hybrid pass to produce an llm-judged edge
        result = TraversalResult()
        result.unresolved = [_make_unresolved_item()]
        config = _make_config(str(tmp_path))
        cache = DiskResponseCache(str(tmp_path))
        judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
        result = judge.run(result, index, mock_provider, config)

        llm_edges = [e for e in result.edges if e.provenance == Provenance.LLM_JUDGED]
        assert llm_edges, "Expected at least one llm-judged edge"
        edge = llm_edges[0]
        assert edge.llm_trace is not None

        # Persist edge to KuzuStore
        db_path = str(tmp_path / "test.db")
        store = KuzuStore(db_path)
        for node_id in (edge.from_id, edge.to_id):
            store.upsert_node({
                "_table": "Deployable",
                "id": node_id,
                "repo_id": node_id,
                "kind": "service",
                "name": node_id.split("/")[-1],
            })
        store.upsert_edge({
            "_rel_type": "DEPENDS_ON",
            "_from_table": "Deployable",
            "_to_table": "Deployable",
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "env": edge.env,
            "provenance": edge.provenance.value,
            "confidence": edge.confidence.value,
            "evidence": [str(e) for e in edge.evidence],
            "deployed_ref": edge.deployed_ref or "",
            "ambiguous": edge.ambiguous,
            "stale": edge.stale,
            "discovered_at": "",
            "llm_trace": edge.llm_trace or "",
        })

        # Query explain_edge with cache_path to load trace
        qe = QueryEngine(store)
        qr = qe.explain_edge(
            from_id=edge.from_id,
            to_id=edge.to_id,
            env=edge.env,
            cache_path=str(tmp_path),
        )

        assert qr.results, "explain_edge must return at least one result"
        result_row = qr.results[0]

        # llm_trace field must be present and populated
        assert "llm_trace" in result_row
        trace = result_row["llm_trace"]
        assert trace is not None, "llm_trace must not be None for an llm-judged edge"
        assert isinstance(trace, dict)

        # Trace must contain required fields
        assert "trace_id" in trace
        assert "decision_type" in trace
        assert "redacted_request" in trace
        assert "grounding_result" in trace
        assert "disposition" in trace
        assert trace["disposition"] == "accepted"

        # Redacted request must not contain known secret values
        redacted_req_str = json.dumps(trace.get("redacted_request", {}))
        assert "tok_live_abc123" not in redacted_req_str

# ---------------------------------------------------------------------------
# T034 — SC-007: M0–M8 test suite passes unchanged; no LLM imports required
# ---------------------------------------------------------------------------

class TestSC007M0M8Unaffected:
    def test_sc007_llm_module_not_imported_in_structured_path(self) -> None:
        """Importing the core structured-mode modules must not pull in tendril.llm."""
        import sys

        # These are the structured-mode imports — they must work without LLM deps
        llm_modules_before = {k for k in sys.modules if k.startswith("tendril.llm")}

        # Import core structured modules fresh (may already be imported, that's fine)
        import tendril.core.traversal  # noqa: F401
        import tendril.core.index  # noqa: F401
        import tendril.core.resolver  # noqa: F401
        import tendril.models.ir  # noqa: F401
        import tendril.models.graph  # noqa: F401

        # tendril.llm must NOT appear in sys.modules solely from structured imports
        # (It may already be there from other tests — we test that core modules
        #  don't *add* new llm sub-modules)
        llm_modules_after_core = {k for k in sys.modules if k.startswith("tendril.llm")}
        new_llm_from_core = llm_modules_after_core - llm_modules_before
        assert not new_llm_from_core, (
            f"Structured core import pulled in LLM modules: {new_llm_from_core}"
        )


    def test_explain_edge_structured_edge_has_no_llm_trace(self, tmp_path: Path) -> None:
        """explain_edge for a structured edge returns llm_trace=None."""
        from tendril.query.engine import QueryEngine
        from tendril.store.kuzu_store import KuzuStore

        db_path = str(tmp_path / "structured.db")
        store = KuzuStore(db_path)
        for node_id in ("github:myorg/a", "github:myorg/b"):
            store.upsert_node({
                "_table": "Deployable",
                "id": node_id,
                "repo_id": node_id,
                "kind": "service",
                "name": node_id.split("/")[-1],
            })
        store.upsert_edge({
            "_rel_type": "DEPENDS_ON",
            "_from_table": "Deployable",
            "_to_table": "Deployable",
            "from_id": "github:myorg/a",
            "to_id": "github:myorg/b",
            "env": "prod",
            "provenance": "declared",
            "confidence": "high",
            "evidence": [],
            "deployed_ref": "",
            "ambiguous": False,
            "stale": False,
            "discovered_at": "",
            "llm_trace": "",
        })

        qe = QueryEngine(store)
        qr = qe.explain_edge("github:myorg/a", "github:myorg/b", "prod")
        assert qr.results
        assert qr.results[0]["llm_trace"] is None
