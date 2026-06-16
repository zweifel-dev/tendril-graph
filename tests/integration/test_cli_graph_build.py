"""CLI graph build integration test (FR-012, Gap 3).

Verifies that `tendril graph build --anchor ... --env prod --fixture-dir tests/fixtures/golden/`
produces a queryable DEPENDS_ON@prod edge in KuzuStore.

Zero credentials — all fixture data.
"""

from __future__ import annotations

from pathlib import Path

from tendril.cli.main import main
from tendril.store.kuzu_store import KuzuStore

_GOLDEN_DIR = str(Path(__file__).parent.parent / "fixtures" / "golden")


class TestCLIGraphBuild:
    def test_graph_build_produces_depends_on_edge(self, tmp_path: Path) -> None:
        """graph build with golden fixture → DEPENDS_ON@prod persisted to KuzuStore."""
        db_path = str(tmp_path / "graph.db")

        exit_code = main([
            "graph", "build",
            "--anchor", "bitbucket-dc:acme/webforms-solution",
            "--env", "prod",
            "--fixture-dir", _GOLDEN_DIR,
            "--db", db_path,
        ])
        assert exit_code == 0, "CLI graph build returned non-zero exit code"

        store = KuzuStore(db_path)
        edges = store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE r.env = $env RETURN a.id AS from_id, b.id AS to_id, "
            "r.env AS env, r.provenance AS provenance, r.confidence AS confidence, "
            "r.deployed_ref AS deployed_ref",
            {"env": "prod"},
        )

        assert len(edges) >= 1, (
            f"Expected at least one DEPENDS_ON@prod edge, got: {edges}"
        )

        target = next(
            (e for e in edges
             if e.get("from_id") == "bitbucket-dc:acme/webforms-solution"
             and e.get("to_id") == "github:acme/landing-page-ui"),
            None,
        )
        assert target is not None, (
            f"Expected edge webforms-solution -> landing-page-ui @prod. "
            f"Got edges: {[(e.get('from_id'), e.get('to_id')) for e in edges]}"
        )
        assert target["env"] == "prod"
        assert target["deployed_ref"] == "abc123def456", (
            f"Expected deployed_ref=abc123def456, got {target['deployed_ref']!r}"
        )
        assert target["provenance"] == "injected", (
            f"Expected provenance=injected, got {target['provenance']!r}"
        )
        store.close()

    def test_graph_build_exit_zero_on_valid_fixture(self, tmp_path: Path) -> None:
        """graph build exits 0 when fixture-dir is valid."""
        exit_code = main([
            "graph", "build",
            "--anchor", "bitbucket-dc:acme/webforms-solution",
            "--env", "prod",
            "--fixture-dir", _GOLDEN_DIR,
            "--db", str(tmp_path / "g.db"),
        ])
        assert exit_code == 0

    def test_graph_build_exits_1_on_missing_fixture_dir(self, tmp_path: Path) -> None:
        """graph build exits 1 when fixture-dir does not exist."""
        exit_code = main([
            "graph", "build",
            "--anchor", "bitbucket-dc:acme/webforms-solution",
            "--env", "prod",
            "--fixture-dir", str(tmp_path / "nonexistent"),
            "--db", ":memory:",
        ])
        assert exit_code == 1

    def test_graph_build_exits_1_on_bad_anchor(self, tmp_path: Path) -> None:
        """graph build exits 1 when --anchor lacks provider:org/name format."""
        exit_code = main([
            "graph", "build",
            "--anchor", "invalid-anchor",
            "--env", "prod",
            "--fixture-dir", _GOLDEN_DIR,
            "--db", ":memory:",
        ])
        assert exit_code == 1
