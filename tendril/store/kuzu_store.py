"""Kùzu GraphStore adapter (SPEC.md §4.6, §13).

Embedded property graph — no external service needed. The GraphStore ABC
is the only code that knows it's Kùzu; swapping to Neo4j is one plugin change.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import kuzu

from tendril.plugins.base import GraphStore
from tendril.store.schema import SCHEMA_DDL

log = logging.getLogger(__name__)


class KuzuStore(GraphStore):
    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        if db_path == ":memory:":
            self._db = kuzu.Database()
        else:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = kuzu.Database(str(db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()

    def _init_schema(self) -> None:
        for ddl in SCHEMA_DDL:
            try:
                self._conn.execute(ddl)
            except Exception as exc:
                log.debug("Schema DDL skipped (may already exist): %s", exc)

    def id(self) -> str:
        return "kuzu"

    def upsert_node(self, node: dict[str, Any]) -> None:
        # Copy to avoid mutating the caller's dict (BUG 4 fix)
        node = dict(node)
        table = node.pop("_table", None)
        if not table:
            raise ValueError("node must have '_table' key")
        node_id = node.get("id")
        if not node_id:
            raise ValueError("node must have 'id' key")

        # MERGE on primary key only, then SET all other fields.
        # Merging on all columns would require an exact match of every value,
        # turning upsert into insert-only-on-exact-duplicate.
        other = {k: v for k, v in node.items() if k != "id"}
        if other:
            set_clause = ", ".join(f"n.{k} = ${k}" for k in other)
            query = (
                f"MERGE (n:{table} {{id: $id}}) "
                f"ON CREATE SET {set_clause} "
                f"ON MATCH SET {set_clause}"
            )
        else:
            query = f"MERGE (n:{table} {{id: $id}})"

        self._conn.execute(query, node)

    def upsert_edge(self, edge: dict[str, Any]) -> None:
        # Copy to avoid mutating the caller's dict
        edge = dict(edge)
        rel_type = edge.pop("_rel_type", None)
        from_table = edge.pop("_from_table", None)
        to_table = edge.pop("_to_table", None)
        from_id = edge.pop("from_id", None)
        to_id = edge.pop("to_id", None)

        if not all([rel_type, from_table, to_table, from_id, to_id]):
            raise ValueError("edge must have _rel_type, _from_table, _to_table, from_id, to_id")

        if "evidence" in edge and isinstance(edge["evidence"], list):
            edge["evidence"] = json.dumps([str(e) for e in edge["evidence"]])

        # Kùzu does not support MERGE on relationship tables; guard with an
        # existence check to prevent duplicates on re-runs (BUG 5 fix).
        check_q = (
            f"MATCH (a:{from_table} {{id: $from_id}})"
            f"-[r:{rel_type}]->"
            f"(b:{to_table} {{id: $to_id}}) "
            f"RETURN count(r) AS cnt"
        )
        check_result = self.query(check_q, {"from_id": from_id, "to_id": to_id})
        if check_result and check_result[0].get("cnt", 0) > 0:
            return

        params = {**edge, "from_id": from_id, "to_id": to_id}
        if edge:
            props = ", ".join(f"r.{k} = ${k}" for k in edge)
            query = (
                f"MATCH (a:{from_table} {{id: $from_id}}), (b:{to_table} {{id: $to_id}}) "
                f"CREATE (a)-[r:{rel_type}]->(b) "
                f"SET {props}"
            )
        else:
            query = (
                f"MATCH (a:{from_table} {{id: $from_id}}), (b:{to_table} {{id: $to_id}}) "
                f"CREATE (a)-[r:{rel_type}]->(b)"
            )
        self._conn.execute(query, params)

    def query(self, spec: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # execute() is typed as returning QueryResult | list[QueryResult].
        # The list form occurs when kuzu splits a multi-statement string; our
        # queries are always single statements so we take [0] if needed.
        raw = self._conn.execute(spec, params or {})
        result = raw[0] if isinstance(raw, list) else raw
        rows: list[dict[str, Any]] = []
        while result.has_next():
            row = result.get_next()
            col_names = result.get_column_names()
            if col_names:
                rows.append(dict(zip(col_names, row)))
            else:
                rows.append({"_row": row})
        return rows

    def neighbors(
        self,
        node_id: str,
        rel: str | None = None,
        env: str | None = None,
        min_confidence: str | None = None,
    ) -> list[dict[str, Any]]:
        rel_pattern = f":{rel}" if rel else ""
        where_clauses = ["a.id = $node_id"]
        if env:
            where_clauses.append("r.env = $env")
        where = " AND ".join(where_clauses)
        q = (
            f"MATCH (a)-[r{rel_pattern}]->(b) "
            f"WHERE {where} "
            f"RETURN b, r"
        )
        params: dict[str, Any] = {"node_id": node_id}
        if env:
            params["env"] = env
        return self.query(q, params)

    def path(
        self, from_id: str, to_id: str, env: str | None = None,
    ) -> list[dict[str, Any]]:
        # Kùzu's shortestPath does not support inline relationship-property
        # filters the way Neo4j does. Run unfiltered and filter by env in Python
        # if needed (BUG 6 fix — removes invalid `rels(p, r, ...)` syntax).
        q = (
            "MATCH p = shortestPath((a)-[*]->(b)) "
            "WHERE a.id = $from_id AND b.id = $to_id "
            "RETURN p"
        )
        rows = self.query(q, {"from_id": from_id, "to_id": to_id})
        if env:
            rows = [r for r in rows if _path_matches_env(r, env)]
        return rows

    def close(self) -> None:
        pass


def _path_matches_env(path_row: dict[str, Any], env: str) -> bool:
    """Best-effort env filter on a path result row."""
    for value in path_row.values():
        if isinstance(value, dict):
            if value.get("env") == env:
                return True
    return False  # no node matched the requested env — exclude
