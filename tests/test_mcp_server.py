"""MCP server endpoint tests (T030, FR-010).

Tests all 5 MCP endpoints plus discovery manifest, 404 handling,
validation errors, and 503 (store unavailable) using FastAPI TestClient.

The store is seeded once per module via the golden fixture graph build.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tendril.cli.main import main
from tendril.mcp.server import app, get_engine
from tendril.query.engine import QueryEngine
from tendril.store.kuzu_store import KuzuStore


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_GOLDEN_DIR = str(Path(__file__).parent / "fixtures" / "golden")

# Module-scoped store: build once, reuse across all tests.
_store: KuzuStore | None = None
_engine: QueryEngine | None = None


@pytest.fixture(scope="module", autouse=True)
def _seed_store(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Build the golden fixture graph once and keep the store alive for the module."""
    global _store, _engine
    db_path = str(tmp_path_factory.mktemp("mcp") / "graph.db")
    exit_code = main([
        "graph", "build",
        "--anchor", "bitbucket-dc:acme/webforms-solution",
        "--env", "prod",
        "--fixture-dir", _GOLDEN_DIR,
        "--db", db_path,
    ])
    assert exit_code == 0, "Golden fixture graph build failed"
    _store = KuzuStore(db_path)
    _engine = QueryEngine(_store)


def _override_engine() -> QueryEngine:
    assert _engine is not None
    return _engine


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """TestClient with the real seeded engine injected."""
    app.dependency_overrides[get_engine] = _override_engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_store() -> Iterator[TestClient]:
    """TestClient with NO engine — simulates store unavailable (503)."""
    def _raise():
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail={"error": {"code": 503, "message": "Graph store unavailable"}})

    app.dependency_overrides[get_engine] = _raise
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. GET /mcp — discovery manifest
# ---------------------------------------------------------------------------

class TestMCPManifest:
    def test_manifest_returns_tools(self, client: TestClient) -> None:
        resp = client.get("/mcp")
        assert resp.status_code == 200
        body = resp.json()
        assert "tools" in body
        tool_names = [t["name"] for t in body["tools"]]
        assert "find_relevant_repos" in tool_names
        assert "impact_analysis" in tool_names
        assert "dependency_path" in tool_names
        assert "env_diff" in tool_names
        assert "explain_edge" in tool_names
        assert len(body["tools"]) == 5

    def test_manifest_tools_have_schema(self, client: TestClient) -> None:
        resp = client.get("/mcp")
        for tool in resp.json()["tools"]:
            assert "schema" in tool
            assert "properties" in tool["schema"]


# ---------------------------------------------------------------------------
# 2. POST /mcp/find_relevant_repos — valid + invalid
# ---------------------------------------------------------------------------

class TestFindRelevantRepos:
    def test_valid_request(self, client: TestClient) -> None:
        resp = client.post("/mcp/find_relevant_repos", json={
            "task": "webforms",
            "env": "prod",
        })
        assert resp.status_code == 200
        body = resp.json()
        # QueryResult shape
        assert "operation" in body
        assert "results" in body
        assert body["operation"] == "find_relevant_repos"
        assert isinstance(body["results"], list)
        assert len(body["results"]) >= 1

    def test_invalid_min_confidence(self, client: TestClient) -> None:
        resp = client.post("/mcp/find_relevant_repos", json={
            "task": "webforms",
            "env": "prod",
            "min_confidence": "ultra",
        })
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == 400


# ---------------------------------------------------------------------------
# 3. POST /mcp/impact_analysis — valid + missing field
# ---------------------------------------------------------------------------

class TestImpactAnalysis:
    def test_valid_request(self, client: TestClient) -> None:
        resp = client.post("/mcp/impact_analysis", json={
            "repo_id": "bitbucket-dc:acme/webforms-solution",
            "env": "prod",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)

    def test_missing_required_field(self, client: TestClient) -> None:
        """Missing 'env' → 400 validation error."""
        resp = client.post("/mcp/impact_analysis", json={
            "repo_id": "bitbucket-dc:acme/webforms-solution",
        })
        assert resp.status_code == 422 or resp.status_code == 400
        body = resp.json()
        assert "error" in body


# ---------------------------------------------------------------------------
# 4. POST /mcp/dependency_path — valid request
# ---------------------------------------------------------------------------

class TestDependencyPath:
    def test_valid_request(self, client: TestClient) -> None:
        resp = client.post("/mcp/dependency_path", json={
            "from_id": "bitbucket-dc:acme/webforms-solution",
            "to_id": "github:acme/landing-page-ui",
            "env": "prod",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 5. POST /mcp/env_diff — valid request
# ---------------------------------------------------------------------------

class TestEnvDiff:
    def test_valid_request(self, client: TestClient) -> None:
        resp = client.post("/mcp/env_diff", json={
            "repo_id": "bitbucket-dc:acme/webforms-solution",
            "env_a": "prod",
            "env_b": "staging",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 6. POST /mcp/explain_edge — valid request
# ---------------------------------------------------------------------------

class TestExplainEdge:
    def test_valid_request(self, client: TestClient) -> None:
        resp = client.post("/mcp/explain_edge", json={
            "from_id": "bitbucket-dc:acme/webforms-solution",
            "to_id": "github:acme/landing-page-ui",
            "env": "prod",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


# ---------------------------------------------------------------------------
# 7. 404 handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_nonexistent_route_returns_404(self, client: TestClient) -> None:
        resp = client.get("/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body == {"error": {"code": 404, "message": "Not Found"}}

    def test_503_store_unavailable(self, client_no_store: TestClient) -> None:
        resp = client_no_store.post("/mcp/find_relevant_repos", json={
            "task": "anything",
            "env": "prod",
        })
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == 503
