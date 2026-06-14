"""Conformance test suite for GraphStore implementations (SPEC.md §4.6)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tendril.plugins.base import GraphStore


class ConformanceGraphStore(ABC):
    """Abstract conformance suite for graph stores."""

    @abstractmethod
    def store(self) -> GraphStore: ...

    def test_id_returns_string(self) -> None:
        sid = self.store().id()
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_upsert_and_query_round_trip(self) -> None:
        s = self.store()
        s.upsert_node({
            "_table": "Repo",
            "id": "test-repo-1",
            "provider": "github",
            "org": "acme",
            "name": "test-repo",
            "url": "https://github.com/acme/test-repo",
            "default_branch": "main",
            "last_indexed_ref": "",
            "last_seen": "",
        })
        rows = s.query(
            "MATCH (r:Repo {id: $id}) RETURN r.name",
            {"id": "test-repo-1"},
        )
        assert len(rows) > 0
