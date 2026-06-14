"""BFS traversal engine — structured mode (SPEC.md §10).

seed → attribution → extract → for each env: resolve → index.lookup →
DEPENDS_ON → enqueue. Cycle detection via `expanded` set.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from tendril.core.attribution import AttributionEngine
from tendril.core.deployed_ref import DeployedRefResolver
from tendril.core.environment import EnvironmentCanonicalizer
from tendril.core.index import ReverseIndex
from tendril.core.resolver import Resolver
from tendril.models.ir import (
    CICDProfile,
    Confidence,
    ConsumerRef,
    DeployedRef,
    Evidence,
    FileEntry,
    Provenance,
    RepoRef,
    TokenDecl,
)
from tendril.models.graph import DependsOn
from tendril.plugins.base import ExtractorPlugin, ExtractionResult

log = logging.getLogger(__name__)


@dataclass
class TraversalResult:
    edges: list[DependsOn] = field(default_factory=list)
    profiles: dict[str, CICDProfile] = field(default_factory=dict)
    deployed_refs: dict[str, DeployedRef] = field(default_factory=dict)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    expanded: set[str] = field(default_factory=set)


class TraversalEngine:
    def __init__(
        self,
        attribution: AttributionEngine,
        extractors: list[ExtractorPlugin],
        resolver: Resolver,
        index: ReverseIndex,
        ref_resolver: DeployedRefResolver,
        env_canonicalizer: EnvironmentCanonicalizer,
        vcs_read_file: Any = None,
    ) -> None:
        self._attribution = attribution
        self._extractors = extractors
        self._resolver = resolver
        self._index = index
        self._ref_resolver = ref_resolver
        self._env_canon = env_canonicalizer
        self._read_file = vcs_read_file
        # Wire env canonicalizer into the deployed-ref resolver so it can
        # match provider env names ("Production") to canonical forms ("prod").
        if hasattr(ref_resolver, '_env_canon') and ref_resolver._env_canon is None:
            ref_resolver._env_canon = env_canonicalizer

    def traverse(
        self,
        anchor: RepoRef,
        envs: list[str],
        repo_trees: dict[str, list[FileEntry]] | None = None,
        deployments: dict[str, list[dict[str, Any]]] | None = None,
        variable_stores: dict[str, list[Any]] | None = None,
    ) -> TraversalResult:
        result = TraversalResult()
        queue: deque[RepoRef] = deque([anchor])
        trees = repo_trees or {}
        deploys = deployments or {}
        stores = variable_stores or {}

        while queue:
            repo = queue.popleft()
            repo_key = repo.full_name
            if repo_key in result.expanded:
                continue
            result.expanded.add(repo_key)

            tree = trees.get(repo.name, [])
            profile = self._attribution.attribute(
                repo, tree, read_file=self._read_file,
            )
            result.profiles[repo_key] = profile

            for env in envs:
                canon_env, _ = self._env_canon.canonicalize(env)

                deployed_ref = self._ref_resolver.resolve(
                    profile, canon_env, deploys.get(repo.name, []),
                )
                if deployed_ref:
                    result.deployed_refs[f"{repo_key}@{canon_env}"] = deployed_ref

                # FR-24: extract at the deployed ref, not HEAD.
                ref_str = deployed_ref.sha if deployed_ref else "HEAD"

                extraction = self._run_extractors(repo, tree, ref=ref_str)
                static_values = _extract_static_values(extraction, canon_env)
                env_stores = stores.get(repo.name, [])

                for consumer_ref in extraction.consumer_refs:
                    for token_name in consumer_ref.token_refs:
                        token = _find_token(extraction.token_decls, token_name)
                        if not token:
                            continue

                        acquired = self._resolver.acquire(
                            token=token,
                            repo=repo,
                            env=canon_env,
                            profile=profile,
                            ref=ref_str,
                            static_values=static_values,
                            variable_stores=env_stores,
                        )

                        if not acquired.resolved:
                            result.unresolved.append({
                                "repo": repo_key,
                                "env": canon_env,
                                "token": token_name,
                                "rung": acquired.rung,
                                "is_secret": acquired.is_secret,
                            })
                            continue

                        resolved_value = _apply_token_to_ref(
                            consumer_ref.raw_value, token_name, acquired.value or "",
                        )
                        candidates = self._index.lookup(resolved_value, canon_env)

                        if not candidates:
                            host = _extract_host(resolved_value)
                            if host and host != resolved_value:
                                candidates = self._index.lookup(host, canon_env)

                        if not candidates:
                            result.unresolved.append({
                                "repo": repo_key,
                                "env": canon_env,
                                "resolved_value": resolved_value,
                                "reason": "no-index-match",
                            })
                            continue

                        ambiguous = len(candidates) > 1
                        for cand in candidates:
                            # Collect declared_in evidence from ALL TokenDecls
                            # for this token (not just the first match) so that
                            # appsettings.prod.json etc. appear in the edge.
                            all_token_decls = [
                                t for t in extraction.token_decls
                                if t.name == token_name
                            ]
                            consumer_locs = {e.locator for e in consumer_ref.evidence}
                            extra_token_evidence = [
                                t.declared_in for t in all_token_decls
                                if t.declared_in is not None
                                and t.declared_in.locator not in consumer_locs
                            ]
                            all_evidence = (
                                list(consumer_ref.evidence)
                                + extra_token_evidence
                                + list(acquired.evidence)
                                + list(cand.evidence)
                            )

                            edge_confidence = _min_confidence(
                                profile.confidence,
                                cand.confidence,
                            )

                            provenance = (
                                Provenance.INJECTED
                                if acquired.rung != "static"
                                else Provenance.DECLARED
                            )

                            edge = DependsOn(
                                from_id=repo_key,
                                to_id=cand.repo_full_name,
                                env=canon_env,
                                provenance=provenance,
                                confidence=edge_confidence,
                                evidence=all_evidence,
                                deployed_ref=ref_str,
                                ambiguous=ambiguous,
                                candidates=[c.repo_full_name for c in candidates] if ambiguous else [],
                                resolved_via=[cand.raw_value],
                            )
                            result.edges.append(edge)

                            target_repo = _repo_from_full_name(cand.repo_full_name)
                            if target_repo and cand.repo_full_name not in result.expanded:
                                queue.append(target_repo)

                    if not consumer_ref.token_refs and consumer_ref.raw_value:
                        candidates = self._index.lookup(consumer_ref.raw_value, canon_env)
                        for cand in candidates:
                            edge = DependsOn(
                                from_id=repo_key,
                                to_id=cand.repo_full_name,
                                env=canon_env,
                                provenance=Provenance.DECLARED,
                                confidence=cand.confidence,
                                evidence=list(consumer_ref.evidence) + list(cand.evidence),
                                deployed_ref=ref_str,
                                resolved_via=[cand.raw_value],
                            )
                            result.edges.append(edge)

        return result

    def _run_extractors(
        self, repo: RepoRef, tree: list[FileEntry], ref: str = "HEAD",
    ) -> ExtractionResult:
        merged = ExtractionResult()
        for ext in self._extractors:
            try:
                if ext.matches(tree):
                    result = ext.extract(repo, ref, tree, self._read_file)
                    merged.consumer_refs.extend(result.consumer_refs)
                    merged.provider_identities.extend(result.provider_identities)
                    merged.token_decls.extend(result.token_decls)
            except Exception as exc:
                log.warning("Extractor %s failed on %s: %s", ext.id(), repo.full_name, exc)
        return merged


def _find_token(decls: list[TokenDecl], name: str) -> TokenDecl | None:
    for d in decls:
        if d.name == name:
            return d
    return None


def _apply_token_to_ref(raw_value: str, token_name: str, resolved: str) -> str:
    return raw_value.replace(f"{{{token_name}}}", resolved)


def _extract_host(url: str) -> str | None:
    from urllib.parse import urlparse
    if "://" not in url:
        return None
    try:
        parsed = urlparse(url)
        return parsed.hostname
    except Exception:
        return None


def _extract_static_values(extraction: ExtractionResult, env: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for ref in extraction.consumer_refs:
        if ref.env_hint and ref.env_hint.lower() == env.lower():
            for token in ref.token_refs:
                if ref.raw_value and not ref.raw_value.startswith("{"):
                    values[token] = ref.raw_value
    return values


def _min_confidence(a: Confidence, b: Confidence) -> Confidence:
    order = [
        Confidence.VERY_LOW, Confidence.LOW, Confidence.MEDIUM,
        Confidence.HIGH, Confidence.VERY_HIGH,
    ]
    try:
        return order[min(order.index(a), order.index(b))]
    except ValueError:
        return Confidence.MEDIUM


def _repo_from_full_name(full_name: str) -> RepoRef | None:
    parts = full_name.split(":", 1)
    if len(parts) != 2:
        return None
    provider = parts[0]
    org_name = parts[1].split("/", 1)
    if len(org_name) != 2:
        return None
    return RepoRef(provider=provider, org=org_name[0], name=org_name[1])
