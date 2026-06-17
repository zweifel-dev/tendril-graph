"""Unit tests for Tier 1 correctness fixes (006-production-readiness).

T005: Multi-environment filtering (FR-001 / SC-001)
T009: Plugin manifest validation (FR-003)
T011: Template marker detection (FR-004)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tendril.plugins.manifest import PluginManifest, load_manifest
from tendril.store.kuzu_store import KuzuStore


# ---------------------------------------------------------------------------
# T005 — US1: Environment filter fix (FR-001 / SC-001)
# ---------------------------------------------------------------------------

class TestEnvironmentFilter:
    """Verify _path_matches_env returns False when no node matches env (FR-001)."""

    def test_no_matching_env_returns_false(self) -> None:
        """Row with only staging env data excluded when filtering for prod."""
        from tendril.store.kuzu_store import _path_matches_env
        row = {"edge": {"env": "staging", "from_id": "a", "to_id": "b"}}
        assert _path_matches_env(row, "prod") is False

    def test_matching_env_returns_true(self) -> None:
        """Row with matching env data included."""
        from tendril.store.kuzu_store import _path_matches_env
        row = {"edge": {"env": "prod", "from_id": "a", "to_id": "b"}}
        assert _path_matches_env(row, "prod") is True

    def test_no_dict_values_returns_false(self) -> None:
        """Row with no dict values is excluded (was the original bug — returned True)."""
        from tendril.store.kuzu_store import _path_matches_env
        row = {"scalar": "some_value", "count": 42}
        assert _path_matches_env(row, "prod") is False

    def test_multi_env_store_query_filters_correctly(self) -> None:
        """Direct Cypher query with env filter excludes cross-env edges (SC-001)."""
        store = KuzuStore(":memory:")
        for nid in ("svc:a", "svc:b", "svc:c"):
            store.upsert_node({
                "_table": "Deployable",
                "id": nid, "repo_id": nid, "kind": "service", "name": nid,
            })
        # Prod edge: a -> b
        store.upsert_edge({
            "_rel_type": "DEPENDS_ON", "_from_table": "Deployable",
            "_to_table": "Deployable", "from_id": "svc:a", "to_id": "svc:b",
            "env": "prod", "provenance": "declared", "confidence": "high",
            "evidence": ["test:prod-edge"], "deployed_ref": "",
            "ambiguous": False, "stale": False, "discovered_at": "", "llm_trace": "",
        })
        # Staging edge: a -> c
        store.upsert_edge({
            "_rel_type": "DEPENDS_ON", "_from_table": "Deployable",
            "_to_table": "Deployable", "from_id": "svc:a", "to_id": "svc:c",
            "env": "staging", "provenance": "declared", "confidence": "high",
            "evidence": ["test:staging-edge"], "deployed_ref": "",
            "ambiguous": False, "stale": False, "discovered_at": "", "llm_trace": "",
        })
        # Query for prod only — must not return staging edges
        prod_rows = store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE r.env = $env RETURN a.id AS from_id, b.id AS to_id",
            {"env": "prod"},
        )
        to_ids = {r["to_id"] for r in prod_rows}
        assert "svc:b" in to_ids, "Prod edge a->b missing"
        assert "svc:c" not in to_ids, "Staging edge a->c leaked into prod query"


# ---------------------------------------------------------------------------
# T009 — US4: Plugin contract version validation (FR-003)
# ---------------------------------------------------------------------------

class TestPluginManifestValidation:
    def test_datadog_manifest_validates(self) -> None:
        """The in-tree Datadog manifest passes validation after version fix."""
        manifest_path = Path("tendril/connectors/telemetry/tendril-plugin.toml")
        manifest = load_manifest(manifest_path)
        errors = manifest.validate()
        assert errors == [], f"Datadog manifest validation failed: {errors}"

    def test_incompatible_major_version_rejected(self) -> None:
        """A manifest with contract_version '2.0.0' must be rejected."""
        manifest = PluginManifest(
            id="test-plugin",
            family="telemetry",
            contract_version="2.0.0",
        )
        errors = manifest.validate()
        assert any("compatible" in e for e in errors), f"Expected version error, got: {errors}"

    def test_matching_major_version_accepted(self) -> None:
        """A manifest with contract_version '1.0.0-alpha' must pass."""
        manifest = PluginManifest(
            id="test-plugin",
            family="telemetry",
            contract_version="1.0.0-alpha",
        )
        errors = manifest.validate()
        assert errors == [], f"Expected no errors, got: {errors}"


# ---------------------------------------------------------------------------
# T011 — US5: Template marker detection (FR-004)
# ---------------------------------------------------------------------------

class TestTemplateMarkerDetection:
    """Verify _extract_static_values rejects template markers anywhere in string."""

    def test_mid_string_template_rejected(self) -> None:
        """'https://{BaseUrl}/api' must be classified as a template, not static."""
        from tendril.models.ir import ConsumerRef, ConsumerRefKind
        from tendril.plugins.base import ExtractionResult
        from tendril.core.traversal import _extract_static_values

        extraction = ExtractionResult(
            consumer_refs=[
                ConsumerRef(
                    kind=ConsumerRefKind.HTTP_CLIENT,
                    token_refs=["BaseUrl"],
                    raw_value="https://{BaseUrl}/api",
                    env_hint="prod",
                ),
            ],
        )
        result = _extract_static_values(extraction, "prod")
        assert "BaseUrl" not in result, (
            f"Template value 'https://{{BaseUrl}}/api' should NOT be treated as static"
        )

    def test_start_template_still_rejected(self) -> None:
        """'{ServiceUrl}' must still be classified as a template (regression)."""
        from tendril.models.ir import ConsumerRef, ConsumerRefKind
        from tendril.plugins.base import ExtractionResult
        from tendril.core.traversal import _extract_static_values

        extraction = ExtractionResult(
            consumer_refs=[
                ConsumerRef(
                    kind=ConsumerRefKind.HTTP_CLIENT,
                    token_refs=["ServiceUrl"],
                    raw_value="{ServiceUrl}",
                    env_hint="prod",
                ),
            ],
        )
        result = _extract_static_values(extraction, "prod")
        assert "ServiceUrl" not in result

    def test_static_url_accepted(self) -> None:
        """'https://api.prod.example.com' must be classified as static."""
        from tendril.models.ir import ConsumerRef, ConsumerRefKind
        from tendril.plugins.base import ExtractionResult
        from tendril.core.traversal import _extract_static_values

        extraction = ExtractionResult(
            consumer_refs=[
                ConsumerRef(
                    kind=ConsumerRefKind.HTTP_CLIENT,
                    token_refs=["ApiEndpoint"],
                    raw_value="https://api.prod.example.com",
                    env_hint="prod",
                ),
            ],
        )
        result = _extract_static_values(extraction, "prod")
        assert "ApiEndpoint" in result
        assert result["ApiEndpoint"] == "https://api.prod.example.com"
