"""M5 acceptance tests: QueryEngine + QueryResult contract (M5-7).

Seeds an in-memory KuzuStore from the golden fixture estate (3 repos),
then verifies all five QueryEngine methods against the contract in
contracts/mcp-endpoints.md.

All 11 tests run against fixtures — no live API calls, no credentials.
"""

from __future__ import annotations

import pytest

from tendril.query.engine import QueryEngine
from tendril.query.response import QueryResult, UnknownsEntry
from tendril.store.kuzu_store import KuzuStore


# ---------------------------------------------------------------------------
# Fixture: in-memory KuzuStore seeded with the 3-repo golden estate
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_store() -> KuzuStore:
    """Return a KuzuStore seeded with the canonical 3-repo estate."""
    store = KuzuStore(":memory:")

    # Nodes
    store.upsert_node({
        "_table": "Deployable",
        "id": "webforms-solution",
        "repo_id": "bitbucket-dc:acme/webforms-solution",
        "kind": "web",
        "name": "webforms-solution",
    })
    store.upsert_node({
        "_table": "Deployable",
        "id": "landing-page-ui",
        "repo_id": "github:acme/landing-page-ui",
        "kind": "web",
        "name": "landing-page-ui",
    })
    store.upsert_node({
        "_table": "Deployable",
        "id": "landing-page-api",
        "repo_id": "github:acme/landing-page-api",
        "kind": "web",
        "name": "landing-page-api",
    })

    # Edges
    store.upsert_edge({
        "_rel_type": "DEPENDS_ON",
        "_from_table": "Deployable",
        "_to_table": "Deployable",
        "from_id": "webforms-solution",
        "to_id": "landing-page-ui",
        "env": "prod",
        "provenance": "injected",
        "confidence": "high",
        "evidence": '["home.aspx:4", "appsettings.prod.json:1", "octopus:var-preview"]',
        "discovered_at": "2024-01-15T10:30:00Z",
        "deployed_ref": "abc123def456",
        "ambiguous": False,
        "stale": False,
    })
    store.upsert_edge({
        "_rel_type": "DEPENDS_ON",
        "_from_table": "Deployable",
        "_to_table": "Deployable",
        "from_id": "webforms-solution",
        "to_id": "landing-page-api",
        "env": "prod",
        "provenance": "injected",
        "confidence": "medium",
        "evidence": '["appsettings.prod.json:2", "octopus:api-var"]',
        "discovered_at": "2024-01-15T10:30:00Z",
        "deployed_ref": "abc123def456",
        "ambiguous": False,
        "stale": False,
    })

    return store


@pytest.fixture
def engine(seeded_store: KuzuStore) -> QueryEngine:
    return QueryEngine(seeded_store)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFindRelevantRepos:
    def test_keyword_match_returns_seeded_repo(self, engine: QueryEngine) -> None:
        result = engine.find_relevant_repos(task="webforms", env="prod")

        assert isinstance(result, QueryResult)
        assert result.operation == "find_relevant_repos"
        assert result.env == "prod"
        assert isinstance(result.results, list)
        assert len(result.results) > 0

        repo_ids = [r["repo_id"] for r in result.results]
        assert "bitbucket-dc:acme/webforms-solution" in repo_ids

        seed = next(r for r in result.results if "webforms-solution" in r["repo_id"])
        assert seed["hop_depth"] == 0
        assert "confidence" in seed
        assert "provenance" in seed
        assert "deployed_ref" in seed

    def test_no_match_returns_unknowns(self, engine: QueryEngine) -> None:
        result = engine.find_relevant_repos(task="xyzzy-nonexistent", env="prod")

        assert result.results == []
        assert len(result.unknowns) == 1
        assert result.unknowns[0].kind == "no-match"


class TestImpactAnalysis:
    def test_finds_dependents(self, engine: QueryEngine) -> None:
        result = engine.impact_analysis(
            repo_id="github:acme/landing-page-ui", env="prod",
        )

        assert isinstance(result, QueryResult)
        assert result.operation == "impact_analysis"
        repo_ids = [r["repo_id"] for r in result.results]
        assert "bitbucket-dc:acme/webforms-solution" in repo_ids

    def test_leaf_repo_returns_unknowns(self, engine: QueryEngine) -> None:
        result = engine.impact_analysis(
            repo_id="github:acme/landing-page-ui",
            env="staging",  # no edges in staging
        )

        assert result.results == []
        assert len(result.unknowns) == 1
        assert result.unknowns[0].kind == "no-match"


class TestDependencyPath:
    def test_found_path(self, engine: QueryEngine) -> None:
        result = engine.dependency_path(
            from_id="bitbucket-dc:acme/webforms-solution",
            to_id="github:acme/landing-page-ui",
            env="prod",
        )

        assert isinstance(result, QueryResult)
        assert result.operation == "dependency_path"
        assert len(result.results) >= 2  # at least from and to

        repo_ids = [h["repo_id"] for h in result.results]
        assert "bitbucket-dc:acme/webforms-solution" in repo_ids
        assert "github:acme/landing-page-ui" in repo_ids

        for i, hop in enumerate(result.results):
            assert hop["hop_index"] == i
            assert "confidence" in hop
            assert "provenance" in hop

    def test_no_path_returns_unknowns(self, engine: QueryEngine) -> None:
        result = engine.dependency_path(
            from_id="github:acme/landing-page-ui",
            to_id="bitbucket-dc:acme/webforms-solution",
            env="prod",
        )

        assert result.results == []
        assert len(result.unknowns) == 1
        assert result.unknowns[0].kind == "no-source"


class TestEnvDiff:
    def test_same_env_empty_diff(self, engine: QueryEngine) -> None:
        result = engine.env_diff(
            repo_id="bitbucket-dc:acme/webforms-solution",
            env_a="prod",
            env_b="prod",
        )

        assert isinstance(result, QueryResult)
        assert result.operation == "env_diff"
        assert result.results == []
        assert result.unknowns == []

    def test_one_empty_env_valid_response(self, engine: QueryEngine) -> None:
        result = engine.env_diff(
            repo_id="bitbucket-dc:acme/webforms-solution",
            env_a="prod",
            env_b="staging",
        )

        assert isinstance(result, QueryResult)
        assert result.unknowns == []
        # prod has 2 edges, staging has 0 → 2 "removed" entries
        removed = [r for r in result.results if r["diff_type"] == "removed"]
        assert len(removed) == 2


class TestExplainEdge:
    def test_full_evidence_chain(self, engine: QueryEngine) -> None:
        result = engine.explain_edge(
            from_id="bitbucket-dc:acme/webforms-solution",
            to_id="github:acme/landing-page-ui",
            env="prod",
        )

        assert isinstance(result, QueryResult)
        assert result.operation == "explain_edge"
        assert len(result.results) == 1

        entry = result.results[0]
        assert entry["repo_id"] == "github:acme/landing-page-ui"
        assert entry["confidence"] == "high"
        assert entry["provenance"] == "injected"
        assert entry["deployed_ref"] == "abc123def456"
        assert isinstance(entry["evidence"], list)
        assert len(entry["evidence"]) >= 3
        assert "ambiguous" in entry
        assert entry["ambiguous"] is False
        assert "stale" in entry
        assert entry["llm_trace"] is None


class TestQueryResultInvariants:
    def test_deployed_refs_never_null(self, engine: QueryEngine) -> None:
        result = engine.find_relevant_repos(task="xyzzy-nonexistent", env="prod")
        assert result.deployed_refs is not None
        assert isinstance(result.deployed_refs, dict)

    def test_unknowns_never_null(self, engine: QueryEngine) -> None:
        result = engine.find_relevant_repos(task="webforms", env="prod")
        assert result.unknowns is not None
        assert isinstance(result.unknowns, list)

    def test_to_dict_has_all_contract_fields(self, engine: QueryEngine) -> None:
        result = engine.find_relevant_repos(task="webforms", env="prod")
        d = result.to_dict()

        required_fields = {
            "operation", "env", "results", "confidence",
            "provenance", "deployed_refs", "unknowns", "metadata",
        }
        assert required_fields.issubset(d.keys())
        assert d["deployed_refs"] is not None
        assert d["unknowns"] is not None
