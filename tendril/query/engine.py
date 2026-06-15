"""QueryEngine — five structured query operations over the graph (M5-2).

All methods return a QueryResult with deployed_refs always ``{}`` (not None)
and unknowns always ``[]`` (not None).  Multi-hop BFS uses iterative
``store.neighbors()`` calls because Kùzu variable-length patterns have
known compatibility caveats in v0.8.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tendril.plugins.base import GraphStore
from tendril.query.response import (
    QueryResult,
    UnknownsEntry,
    aggregate_confidence,
    aggregate_provenance,
)

log = logging.getLogger(__name__)

# Confidence level ordering for min-confidence filtering.
_CONFIDENCE_RANK: dict[str, int] = {"high": 2, "medium": 1, "low": 0}

# Provenance order used for per-edge display (not aggregation).
_MAX_IMPACT_HOPS = 5


def _passes_min_confidence(edge_confidence: str, min_confidence: str) -> bool:
    return (
        _CONFIDENCE_RANK.get(edge_confidence, 0)
        >= _CONFIDENCE_RANK.get(min_confidence, 0)
    )


def _parse_evidence(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(e) for e in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(e) for e in parsed]
        except (json.JSONDecodeError, ValueError):
            pass
        return [raw] if raw else []
    return []


class QueryEngine:
    """Five query operations over an existing KuzuStore graph."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # find_relevant_repos (keyword BFS)
    # ------------------------------------------------------------------

    def find_relevant_repos(
        self,
        task: str,
        env: str,
        max_hops: int = 3,
        min_confidence: str = "low",
    ) -> QueryResult:
        keyword = task.lower()

        # Seed: deployables whose name or id contains the keyword.
        all_nodes = self._store.query(
            "MATCH (d:Deployable) RETURN d.id AS did, d.name AS dname, d.repo_id AS repo_id"
        )
        seeds = [
            n for n in all_nodes
            if keyword in str(n.get("dname", "")).lower()
            or keyword in str(n.get("did", "")).lower()
        ]

        if not seeds:
            return QueryResult(
                operation="find_relevant_repos",
                env=env,
                results=[],
                confidence="high",
                provenance="declared",
                deployed_refs={},
                unknowns=[UnknownsEntry(
                    kind="no-match",
                    description=f"No repositories match keyword '{task}' in {env}",
                )],
            )

        # BFS to collect connected repos.
        results: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: list[tuple[str, str, int]] = []  # (deployable_id, repo_id, hop_depth)

        for seed in seeds:
            did = seed["did"]
            if did not in visited:
                visited.add(did)
                queue.append((did, seed.get("repo_id") or did, 0))

        confidences: list[str] = []
        provenances: list[str] = []
        deployed_refs: dict[str, str] = {}

        while queue:
            current_did, current_repo_id, hop = queue.pop(0)

            # Get the deployed_ref for this seed from outbound edges.
            dep_ref = self._get_deployed_ref_for_node(current_did, env)
            if dep_ref:
                deployed_refs[current_repo_id] = dep_ref

            results.append({
                "repo_id": current_repo_id,
                "confidence": "high",
                "provenance": "declared",
                "deployed_ref": dep_ref,
                "hop_depth": hop,
            })
            confidences.append("high")
            provenances.append("declared")

            if hop >= max_hops:
                continue

            # Outbound DEPENDS_ON neighbors in this env.
            edges = self._store.query(
                "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
                "WHERE a.id = $node_id AND r.env = $env "
                "RETURN b.id AS bid, b.repo_id AS brepo_id, "
                "r.confidence AS conf, r.provenance AS prov, r.deployed_ref AS dref",
                {"node_id": current_did, "env": env},
            )
            for edge in edges:
                conf = edge.get("conf") or "low"
                if not _passes_min_confidence(conf, min_confidence):
                    continue
                bid = edge["bid"]
                if bid in visited:
                    continue
                visited.add(bid)
                brepo_id = edge.get("brepo_id") or bid
                queue.append((bid, brepo_id, hop + 1))
                confidences.append(conf)
                provenances.append(edge.get("prov") or "declared")
                if edge.get("dref"):
                    deployed_refs[brepo_id] = edge["dref"]

        return QueryResult(
            operation="find_relevant_repos",
            env=env,
            results=results,
            confidence=aggregate_confidence(confidences),
            provenance=aggregate_provenance(provenances),
            deployed_refs=deployed_refs,
            unknowns=[],
        )

    # ------------------------------------------------------------------
    # impact_analysis (reverse BFS)
    # ------------------------------------------------------------------

    def impact_analysis(
        self,
        repo_id: str,
        env: str,
        min_confidence: str = "low",
    ) -> QueryResult:
        # Resolve repo_id to deployable id.
        target_did = self._repo_id_to_did(repo_id)
        if not target_did:
            # Try treating repo_id as a deployable id directly.
            target_did = repo_id

        results: list[dict[str, Any]] = []
        visited: set[str] = set()
        queue: list[tuple[str, str, int, list[str]]] = [(target_did, repo_id, 0, [])]
        visited.add(target_did)

        confidences: list[str] = []
        provenances: list[str] = []
        deployed_refs: dict[str, str] = {}

        while queue:
            current_did, current_repo_id, hop, path_so_far = queue.pop(0)
            if hop >= _MAX_IMPACT_HOPS:
                continue

            # Inbound DEPENDS_ON edges (who depends on current node?)
            inbound = self._store.query(
                "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
                "WHERE b.id = $node_id AND r.env = $env "
                "RETURN a.id AS aid, a.repo_id AS arepo_id, "
                "r.confidence AS conf, r.provenance AS prov, r.deployed_ref AS dref",
                {"node_id": current_did, "env": env},
            )
            for edge in inbound:
                conf = edge.get("conf") or "low"
                if not _passes_min_confidence(conf, min_confidence):
                    continue
                aid = edge["aid"]
                if aid in visited:
                    continue
                visited.add(aid)
                arepo_id = edge.get("arepo_id") or aid
                dref = edge.get("dref")
                if dref:
                    deployed_refs[arepo_id] = dref
                path_to_target = path_so_far + [arepo_id]
                results.append({
                    "repo_id": arepo_id,
                    "confidence": conf,
                    "provenance": edge.get("prov") or "declared",
                    "deployed_ref": dref,
                    "path_to_target": path_to_target,
                })
                confidences.append(conf)
                provenances.append(edge.get("prov") or "declared")
                queue.append((aid, arepo_id, hop + 1, path_to_target))

        if not results:
            return QueryResult(
                operation="impact_analysis",
                env=env,
                results=[],
                confidence="high",
                provenance="declared",
                deployed_refs={},
                unknowns=[UnknownsEntry(
                    kind="no-match",
                    description=f"No repositories depend on {repo_id} in {env}",
                    repo_id=repo_id,
                )],
            )

        return QueryResult(
            operation="impact_analysis",
            env=env,
            results=results,
            confidence=aggregate_confidence(confidences),
            provenance=aggregate_provenance(provenances),
            deployed_refs=deployed_refs,
            unknowns=[],
        )

    # ------------------------------------------------------------------
    # dependency_path (BFS path finding)
    # ------------------------------------------------------------------

    def dependency_path(
        self,
        from_id: str,
        to_id: str,
        env: str,
    ) -> QueryResult:
        from_did = self._repo_id_to_did(from_id) or from_id
        to_did = self._repo_id_to_did(to_id) or to_id

        # BFS to find shortest path.
        visited: set[str] = {from_did}
        # Queue entries: (current_did, path_of_repo_ids_so_far)
        from_repo_id = self._did_to_repo_id(from_did) or from_id
        queue: list[tuple[str, list[dict[str, Any]]]] = [
            (from_did, [{
                "repo_id": from_repo_id,
                "confidence": "high",
                "provenance": "declared",
                "deployed_ref": None,
                "hop_index": 0,
            }])
        ]

        while queue:
            current_did, path = queue.pop(0)

            edges = self._store.query(
                "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
                "WHERE a.id = $node_id AND r.env = $env "
                "RETURN b.id AS bid, b.repo_id AS brepo_id, "
                "r.confidence AS conf, r.provenance AS prov, r.deployed_ref AS dref",
                {"node_id": current_did, "env": env},
            )
            for edge in edges:
                bid = edge["bid"]
                if bid in visited:
                    continue
                visited.add(bid)
                conf = edge.get("conf") or "low"
                prov = edge.get("prov") or "declared"
                brepo_id = edge.get("brepo_id") or bid
                dref = edge.get("dref")
                new_path = path + [{
                    "repo_id": brepo_id,
                    "confidence": conf,
                    "provenance": prov,
                    "deployed_ref": dref,
                    "hop_index": len(path),
                }]
                if bid == to_did:
                    all_confs = [h["confidence"] for h in new_path]
                    all_provs = [h["provenance"] for h in new_path]
                    deployed_refs = {
                        h["repo_id"]: h["deployed_ref"]
                        for h in new_path
                        if h.get("deployed_ref")
                    }
                    return QueryResult(
                        operation="dependency_path",
                        env=env,
                        results=new_path,
                        confidence=aggregate_confidence(all_confs),
                        provenance=aggregate_provenance(all_provs),
                        deployed_refs=deployed_refs,
                        unknowns=[],
                    )
                queue.append((bid, new_path))

        return QueryResult(
            operation="dependency_path",
            env=env,
            results=[],
            confidence="high",
            provenance="declared",
            deployed_refs={},
            unknowns=[UnknownsEntry(
                kind="no-source",
                description=f"No path found from {from_id} to {to_id} in {env}",
            )],
        )

    # ------------------------------------------------------------------
    # env_diff (set diff of outbound edges across two envs)
    # ------------------------------------------------------------------

    def env_diff(
        self,
        repo_id: str,
        env_a: str,
        env_b: str,
    ) -> QueryResult:
        did = self._repo_id_to_did(repo_id) or repo_id
        edges_a = self._get_outbound_edges(did, env_a)
        edges_b = self._get_outbound_edges(did, env_b)

        ids_a = {e["to_repo_id"] for e in edges_a}
        ids_b = {e["to_repo_id"] for e in edges_b}
        map_a = {e["to_repo_id"]: e for e in edges_a}
        map_b = {e["to_repo_id"]: e for e in edges_b}

        results: list[dict[str, Any]] = []
        confidences: list[str] = []
        provenances: list[str] = []

        for rid in sorted(ids_a - ids_b):
            e = map_a[rid]
            results.append({
                "repo_id": rid,
                "confidence": e["confidence"],
                "provenance": e["provenance"],
                "deployed_ref": e["deployed_ref"],
                "diff_type": "removed",
                "env_a_value": e["confidence"],
                "env_b_value": None,
            })
            confidences.append(e["confidence"])
            provenances.append(e["provenance"])

        for rid in sorted(ids_b - ids_a):
            e = map_b[rid]
            results.append({
                "repo_id": rid,
                "confidence": e["confidence"],
                "provenance": e["provenance"],
                "deployed_ref": e["deployed_ref"],
                "diff_type": "added",
                "env_a_value": None,
                "env_b_value": e["confidence"],
            })
            confidences.append(e["confidence"])
            provenances.append(e["provenance"])

        for rid in sorted(ids_a & ids_b):
            ea = map_a[rid]
            eb = map_b[rid]
            if ea["confidence"] != eb["confidence"]:
                results.append({
                    "repo_id": rid,
                    "confidence": aggregate_confidence([ea["confidence"], eb["confidence"]]),
                    "provenance": aggregate_provenance([ea["provenance"], eb["provenance"]]),
                    "deployed_ref": ea["deployed_ref"] or eb["deployed_ref"],
                    "diff_type": "changed",
                    "env_a_value": ea["confidence"],
                    "env_b_value": eb["confidence"],
                })
                confidences.append(ea["confidence"])
                provenances.append(ea["provenance"])

        deployed_refs: dict[str, str] = {}
        for e in edges_a + edges_b:
            if e.get("deployed_ref"):
                deployed_refs[e["to_repo_id"]] = e["deployed_ref"]

        return QueryResult(
            operation="env_diff",
            env=f"{env_a}:{env_b}",
            results=results,
            confidence=aggregate_confidence(confidences) if confidences else "high",
            provenance=aggregate_provenance(provenances) if provenances else "declared",
            deployed_refs=deployed_refs,
            unknowns=[],
        )

    # ------------------------------------------------------------------
    # explain_edge (full evidence chain)
    # ------------------------------------------------------------------

    def explain_edge(
        self,
        from_id: str,
        to_id: str,
        env: str,
    ) -> QueryResult:
        from_did = self._repo_id_to_did(from_id) or from_id
        to_did = self._repo_id_to_did(to_id) or to_id

        rows = self._store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE a.id = $from_id AND b.id = $to_id AND r.env = $env "
            "RETURN b.repo_id AS to_repo_id, r.confidence AS conf, "
            "r.provenance AS prov, r.deployed_ref AS dref, "
            "r.evidence AS ev, r.ambiguous AS amb, r.stale AS stale",
            {"from_id": from_did, "to_id": to_did, "env": env},
        )

        if not rows:
            return QueryResult(
                operation="explain_edge",
                env=env,
                results=[],
                confidence="high",
                provenance="declared",
                deployed_refs={},
                unknowns=[UnknownsEntry(
                    kind="no-source",
                    description=f"No edge found from {from_id} to {to_id} in {env}",
                )],
            )

        row = rows[0]
        conf = row.get("conf") or "low"
        prov = row.get("prov") or "declared"
        dref = row.get("dref")
        evidence = _parse_evidence(row.get("ev"))
        ambiguous = bool(row.get("amb", False))
        stale = bool(row.get("stale", False))
        to_repo_id = row.get("to_repo_id") or to_id

        deployed_refs: dict[str, str] = {}
        if dref:
            deployed_refs[to_repo_id] = dref

        return QueryResult(
            operation="explain_edge",
            env=env,
            results=[{
                "repo_id": to_repo_id,
                "confidence": conf,
                "provenance": prov,
                "deployed_ref": dref,
                "evidence": evidence,
                "ambiguous": ambiguous,
                "stale": stale,
                "llm_trace": None,
            }],
            confidence=conf,
            provenance=prov,
            deployed_refs=deployed_refs,
            unknowns=[],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _repo_id_to_did(self, repo_id: str) -> str | None:
        """Resolve a full repo_id like 'github:acme/foo' to a Deployable.id."""
        rows = self._store.query(
            "MATCH (d:Deployable) WHERE d.repo_id = $repo_id RETURN d.id AS did",
            {"repo_id": repo_id},
        )
        if rows:
            return rows[0].get("did")
        # Try direct id match (short name fallback).
        rows2 = self._store.query(
            "MATCH (d:Deployable) WHERE d.id = $did RETURN d.id AS did",
            {"did": repo_id},
        )
        return rows2[0].get("did") if rows2 else None

    def _did_to_repo_id(self, did: str) -> str | None:
        rows = self._store.query(
            "MATCH (d:Deployable) WHERE d.id = $did RETURN d.repo_id AS repo_id",
            {"did": did},
        )
        return rows[0].get("repo_id") if rows else None

    def _get_deployed_ref_for_node(self, did: str, env: str) -> str | None:
        """Get the deployed_ref SHA for a deployable in a given env from its edges."""
        rows = self._store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE a.id = $did AND r.env = $env AND r.deployed_ref IS NOT NULL "
            "RETURN r.deployed_ref AS dref LIMIT 1",
            {"did": did, "env": env},
        )
        return rows[0].get("dref") if rows else None

    def _get_outbound_edges(self, did: str, env: str) -> list[dict[str, Any]]:
        rows = self._store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE a.id = $node_id AND r.env = $env "
            "RETURN b.repo_id AS to_repo_id, r.confidence AS confidence, "
            "r.provenance AS provenance, r.deployed_ref AS deployed_ref",
            {"node_id": did, "env": env},
        )
        return [
            {
                "to_repo_id": r.get("to_repo_id") or r.get("b.id", ""),
                "confidence": r.get("confidence") or "low",
                "provenance": r.get("provenance") or "declared",
                "deployed_ref": r.get("deployed_ref"),
            }
            for r in rows
        ]
