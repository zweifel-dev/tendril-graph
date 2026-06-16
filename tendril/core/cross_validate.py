"""CrossValidator — three-way static/runtime reconciliation (M10).

Compares runtime-observed edges from a TelemetryProvider against the
static dependency graph, producing a DivergenceReport with confirmed,
static_only, and runtime_only edge sets.

Coupling note: imports SecretRedactor from tendril.llm.redactor. This is
acceptable because tendril.llm is an installed module from M9. If ever
made optional, redaction logic must be extracted to a shared utility.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from tendril.core.index import IndexEntry, ReverseIndex
from tendril.models.ir import (
    Capabilities,
    Confidence,
    ConfirmedEdge,
    DegradationNotice,
    DivergenceReport,
    Evidence,
    IdentityClass,
    ObservedEdge,
    ResolvedObservedEdge,
    RuntimeOnlyEdge,
    StaticOnlyEdge,
    UnknownService,
)
from tendril.plugins.base import GraphStore, TelemetryProvider

log = logging.getLogger(__name__)

# Capability → data method name mapping
_CAPABILITY_METHODS: dict[str, str] = {
    "apm": "service_dependencies",
    "traces": "edges_from_traces",
    "logs": "edges_from_logs",
    "rum": "edges_from_rum",
}


class CrossValidator:
    """Three-way static/runtime reconciliation engine.

    Constructor args:
        store: GraphStore for reading static edges and writing runtime-only edges.
        provider: TelemetryProvider for fetching observed edges.
        reverse_index: ReverseIndex for resolving service names to repo_ids.
        redactor: Optional SecretRedactor for evidence redaction (FR-013).
    """

    def __init__(
        self,
        store: GraphStore,
        provider: TelemetryProvider,
        reverse_index: ReverseIndex,
        redactor: Any | None = None,
    ) -> None:
        self._store = store
        self._provider = provider
        self._index = reverse_index
        self._redactor = redactor

    # ------------------------------------------------------------------
    # reconcile(env)
    # ------------------------------------------------------------------

    def reconcile(self, env: str) -> DivergenceReport:
        """Run three-way reconciliation for a single environment.

        Steps (per cross-validator contract):
        1. Probe capabilities
        2. Fetch observed edges from active capabilities
        3. Resolve service names to repo_ids
        4. Deduplicate edges, merging evidence
        5. Fetch static edges from store
        6. Compute confirmed/static_only/runtime_only sets
        7. Redact evidence
        8. Write runtime_only edges to store (upsert)
        9. Log reconcile summary
        10. Return DivergenceReport
        """
        start = time.monotonic()
        metadata: list[DegradationNotice] = []
        unknowns: list[UnknownService] = []

        # Step 1: Probe capabilities
        caps: Capabilities
        try:
            caps = self._provider.probe(env)
        except Exception as exc:
            log.warning("probe failed for env %s: %s", env, exc)
            caps = {"apm": False, "logs": False, "traces": False, "rum": False}
            for cap_name in _CAPABILITY_METHODS:
                metadata.append(DegradationNotice(
                    capability=cap_name,
                    reason="error",
                    message=f"probe failed: {exc}",
                ))

        # Step 2: Fetch observed edges from active capabilities
        raw_edges: list[ObservedEdge] = []
        for cap_name, method_name in _CAPABILITY_METHODS.items():
            if not caps.get(cap_name, False):
                log.debug("capability %s inactive for env %s — skipping", cap_name, env)
                metadata.append(DegradationNotice(
                    capability=cap_name,
                    reason="inactive",
                    message=f"capability {cap_name} inactive for env {env}",
                ))
                continue
            try:
                method = getattr(self._provider, method_name)
                edges = method(env)
                raw_edges.extend(edges)
            except Exception as exc:
                log.warning("data fetch failed for %s in env %s: %s", cap_name, env, exc)
                metadata.append(DegradationNotice(
                    capability=cap_name,
                    reason="error",
                    message=f"data fetch failed: {exc}",
                ))

        # Step 3: Resolve service names to repo_ids
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        resolved: list[ResolvedObservedEdge] = []
        for edge in raw_edges:
            from_result = self._resolve_service_name(edge.from_service, env)
            to_result = self._resolve_service_name(edge.to_service, env)

            # Record unknowns
            if isinstance(from_result, UnknownService):
                from_result.capability = edge.capability
                unknowns.append(from_result)
                continue
            if isinstance(to_result, UnknownService):
                to_result.capability = edge.capability
                unknowns.append(to_result)
                continue

            # Build evidence locator (FR-021)
            api_path = _capability_api_path(edge.capability)
            locator = f"datadog:{edge.capability}:{env}:{api_path}@{now_iso}"
            evidence = Evidence(source_type=f"datadog-{edge.capability}", locator=locator)

            # Confidence per FR-004
            if edge.capability == "apm":
                confidence = Confidence.HIGH
            elif edge.capability == "rum":
                confidence = Confidence.HIGH
            elif edge.sample_count > 1:
                confidence = Confidence.HIGH
            else:
                confidence = Confidence.MEDIUM

            # Get deployed_ref from static graph
            deployed_ref = self._get_deployed_ref(from_result, env)

            resolved.append(ResolvedObservedEdge(
                from_id=from_result,
                to_id=to_result,
                env=env,
                evidence=[evidence],
                confidence=confidence,
                deployed_ref=deployed_ref,
            ))

        # Step 4: Deduplicate by (from_id, to_id, env), merge evidence (FR-010)
        merged = _deduplicate_edges(resolved)

        # FR-026: warn on >10,000 resolved edges
        if len(merged) > 10_000:
            log.warning(
                "Reconcile for env %s produced %d resolved edges (>10,000 threshold)",
                env, len(merged),
            )

        # Step 5: Fetch static DEPENDS_ON edges for env
        static_edges = self._fetch_static_edges(env)

        # Step 6: Compute confirmed/static_only/runtime_only
        runtime_keys = {(e.from_id, e.to_id) for e in merged}
        static_keys = {(e["from_id"], e["to_id"]) for e in static_edges}
        static_map = {(e["from_id"], e["to_id"]): e for e in static_edges}
        runtime_map = {(e.from_id, e.to_id): e for e in merged}

        confirmed: list[ConfirmedEdge] = []
        for key in sorted(runtime_keys & static_keys):
            se = static_map[key]
            re_ = runtime_map[key]
            confirmed.append(ConfirmedEdge(
                from_id=key[0],
                to_id=key[1],
                env=env,
                static_provenance=se.get("provenance", ""),
                static_confidence=se.get("confidence", ""),
                runtime_capabilities=[e.source_type.replace("datadog-", "") for e in re_.evidence],
            ))

        static_only: list[StaticOnlyEdge] = []
        for key in sorted(static_keys - runtime_keys):
            se = static_map[key]
            static_only.append(StaticOnlyEdge(
                from_id=key[0],
                to_id=key[1],
                env=env,
                provenance=se.get("provenance", ""),
                confidence=se.get("confidence", ""),
            ))
            log.info(
                "static-only dependency: %s → %s @ %s — no runtime traffic observed",
                key[0], key[1], env,
            )

        runtime_only: list[RuntimeOnlyEdge] = []
        for key in sorted(runtime_keys - static_keys):
            re_ = runtime_map[key]
            runtime_only.append(RuntimeOnlyEdge(
                from_id=key[0],
                to_id=key[1],
                env=env,
                confidence=re_.confidence.value if isinstance(re_.confidence, Confidence) else re_.confidence,
                evidence=re_.evidence,
                deployed_ref=re_.deployed_ref,
            ))

        # Step 7: Redact evidence (FR-013) — applied to runtime_only evidence
        if self._redactor:
            runtime_only = _redact_runtime_edges(runtime_only, self._redactor)

        # Step 8: Write runtime_only edges to store (FR-004, FR-020 upsert)
        for edge in runtime_only:
            try:
                self._write_runtime_edge(edge, env)
            except Exception as exc:
                log.error(
                    "Failed to write runtime edge (%s, %s, %s): %s",
                    edge.from_id, edge.to_id, env, exc,
                )
                metadata.append(DegradationNotice(
                    capability="store",
                    reason="store-write-error",
                    message=f"Failed to write edge {edge.from_id} → {edge.to_id}: {exc}",
                ))

        # Deduplicate unknowns by (service, env, reason)
        seen_unknowns: set[tuple[str, str, str]] = set()
        deduped_unknowns: list[UnknownService] = []
        for u in unknowns:
            key = (u.service, u.env, u.reason)
            if key not in seen_unknowns:
                seen_unknowns.add(key)
                deduped_unknowns.append(u)

        elapsed = time.monotonic() - start

        report = DivergenceReport(
            env=env,
            confirmed=confirmed,
            static_only=static_only,
            runtime_only=runtime_only,
            unknowns=deduped_unknowns,
            capabilities_probed=dict(caps),
            metadata=metadata,
            elapsed_seconds=round(elapsed, 2),
        )

        # Step 9: Log reconcile summary (FR-027)
        degraded = [m.capability for m in metadata if m.reason != "inactive"]
        log.info(
            "Reconcile complete for env %s: confirmed=%d, static_only=%d, "
            "runtime_only=%d, unknowns=%d, degraded_capabilities=%s, elapsed=%.1fs",
            env, len(confirmed), len(static_only), len(runtime_only),
            len(deduped_unknowns), degraded, elapsed,
        )

        return report

    # ------------------------------------------------------------------
    # Service name resolution (FR-023)
    # ------------------------------------------------------------------

    def _resolve_service_name(
        self, service_name: str, env: str,
    ) -> str | UnknownService:
        """Two-step reverse-index lookup per FR-023.

        Step 1: Exact match on SERVICE_TAG identity.
        Step 2: Hostname suffix match on NETWORK identities.
        Returns repo_full_name on unique match, UnknownService otherwise.
        """
        # Step 1: Exact SERVICE_TAG match
        entries = self._index.lookup(service_name, env)
        tag_matches = [
            e for e in entries
            if e.identity_class == IdentityClass.SERVICE_TAG
        ]
        if len(tag_matches) == 1:
            return tag_matches[0].repo_full_name
        if len(tag_matches) > 1:
            return UnknownService(
                service=service_name,
                env=env,
                capability="",
                reason="ambiguous-match",
                candidates=[e.repo_full_name for e in tag_matches],
            )

        # Step 2: Hostname suffix match on NETWORK identities
        # Scan all NETWORK entries for hostname ending with service_name
        suffix_matches: list[IndexEntry] = []
        for key, entry_list in self._index._normalized.items():
            for entry in entry_list:
                if entry.identity_class != IdentityClass.NETWORK:
                    continue
                # Extract hostname from the normalized value
                hostname = key.split("/")[0] if "/" in key else key
                if hostname == service_name or hostname.startswith(service_name + "."):
                    suffix_matches.append(entry)

        if len(suffix_matches) == 1:
            return suffix_matches[0].repo_full_name
        if len(suffix_matches) > 1:
            return UnknownService(
                service=service_name,
                env=env,
                capability="",
                reason="ambiguous-match",
                candidates=list({e.repo_full_name for e in suffix_matches}),
            )

        return UnknownService(
            service=service_name,
            env=env,
            capability="",
            reason="no-index-match",
        )

    # ------------------------------------------------------------------
    # Graph store helpers
    # ------------------------------------------------------------------

    def _fetch_static_edges(self, env: str) -> list[dict[str, Any]]:
        """Fetch all static DEPENDS_ON edges for the given environment."""
        try:
            rows = self._store.query(
                "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
                "WHERE r.env = $env "
                "RETURN a.id AS from_id, b.id AS to_id, "
                "r.provenance AS provenance, r.confidence AS confidence, "
                "r.deployed_ref AS deployed_ref",
                {"env": env},
            )
            if not rows:
                log.warning("No static graph found in store — all runtime edges will appear as runtime_only.")
            return rows
        except Exception as exc:
            log.warning("Failed to fetch static edges for env %s: %s", env, exc)
            return []

    def _get_deployed_ref(self, repo_id: str, env: str) -> str | None:
        """Get the deployed_ref SHA for a repo in a given env from DEPLOYED_AS."""
        try:
            rows = self._store.query(
                "MATCH (a:Deployable)-[r:DEPLOYED_AS]->(d:DeployedRef) "
                "WHERE a.id = $repo_id AND r.env = $env "
                "RETURN d.sha AS sha, d.deploy_timestamp AS ts "
                "ORDER BY d.deploy_timestamp DESC LIMIT 1",
                {"repo_id": repo_id, "env": env},
            )
            if rows:
                return rows[0].get("sha")
        except Exception:
            pass
        return None

    def _write_runtime_edge(self, edge: RuntimeOnlyEdge, env: str) -> None:
        """Write a runtime-only edge to the graph store (FR-004, FR-020 upsert)."""
        # Ensure both endpoint nodes exist
        for node_id in (edge.from_id, edge.to_id):
            node_name = node_id.split("/")[-1] if "/" in node_id else node_id
            self._store.upsert_node({
                "_table": "Deployable",
                "id": node_id,
                "repo_id": node_id,
                "kind": "service",
                "name": node_name,
            })

        # Check for existing observed edge (FR-020 upsert)
        existing = self._store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE a.id = $from_id AND b.id = $to_id AND r.env = $env "
            "AND r.provenance = 'observed' "
            "RETURN count(r) AS cnt",
            {"from_id": edge.from_id, "to_id": edge.to_id, "env": env},
        )
        if existing and existing[0].get("cnt", 0) > 0:
            # Update evidence on existing edge — Kùzu doesn't support
            # relationship property updates easily; skip for v0.
            # The existing edge remains with its original evidence.
            return

        evidence_strs = [str(e) for e in edge.evidence]
        self._store.upsert_edge({
            "_rel_type": "DEPENDS_ON",
            "_from_table": "Deployable",
            "_to_table": "Deployable",
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "env": env,
            "provenance": "observed",
            "confidence": edge.confidence,
            "evidence": evidence_strs,
            "deployed_ref": edge.deployed_ref or "",
            "ambiguous": False,
            "stale": False,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "llm_trace": "",
        })


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _capability_api_path(capability: str) -> str:
    """Map capability name to Datadog API endpoint path (FR-021)."""
    return {
        "apm": "/api/v1/service_dependencies",
        "traces": "/api/v2/spans/events/search",
        "logs": "/api/v2/logs/events/search",
        "rum": "/api/v2/rum/events/search",
    }.get(capability, f"/api/unknown/{capability}")


_EVIDENCE_LOCATOR_PATTERN = re.compile(
    r"^datadog:[a-z]+:[a-zA-Z0-9_-]+:/api/v[12]/[a-z_/]+@\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)


def validate_evidence_locator(locator: str) -> bool:
    """Validate evidence locator matches FR-021 format.

    Expected: datadog:{capability}:{env}:{api_path}@{iso_timestamp}
    """
    return bool(_EVIDENCE_LOCATOR_PATTERN.match(locator))


def _deduplicate_edges(
    edges: list[ResolvedObservedEdge],
) -> list[ResolvedObservedEdge]:
    """Merge edges by (from_id, to_id, env), combining evidence lists.

    FR-010: evidence is sorted by (capability, iso_timestamp, api_path).
    Confidence takes the highest among merged edges.
    """
    by_key: dict[tuple[str, str, str], ResolvedObservedEdge] = {}
    confidence_rank = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}

    for edge in edges:
        key = (edge.from_id, edge.to_id, edge.env)
        if key in by_key:
            existing = by_key[key]
            existing.evidence.extend(edge.evidence)
            # Take highest confidence
            if confidence_rank.get(edge.confidence, 0) > confidence_rank.get(existing.confidence, 0):
                existing.confidence = edge.confidence
            # Preserve deployed_ref from first non-null
            if not existing.deployed_ref and edge.deployed_ref:
                existing.deployed_ref = edge.deployed_ref
        else:
            by_key[key] = ResolvedObservedEdge(
                from_id=edge.from_id,
                to_id=edge.to_id,
                env=edge.env,
                evidence=list(edge.evidence),
                confidence=edge.confidence,
                deployed_ref=edge.deployed_ref,
            )

    # Sort evidence deterministically (FR-010)
    for edge in by_key.values():
        edge.evidence.sort(key=lambda e: (e.source_type, e.locator))

    return list(by_key.values())


def _redact_runtime_edges(
    edges: list[RuntimeOnlyEdge],
    _redactor: Any,
) -> list[RuntimeOnlyEdge]:
    """Apply secret redaction to evidence locators (FR-013).

    Redacts Authorization headers, Bearer tokens, API keys in query params.
    Omits fully-sensitive evidence items.
    """
    from tendril.llm.redactor import REDACTED, _EMAIL_PATTERN, _PHONE_PATTERN

    result: list[RuntimeOnlyEdge] = []

    for edge in edges:
        cleaned_evidence: list[Evidence] = []
        for ev in edge.evidence:
            locator = ev.locator
            # Redact common sensitive patterns in locators
            locator = _redact_sensitive_in_string(locator)

            # Check for PII in locator
            if _EMAIL_PATTERN.search(locator) or _PHONE_PATTERN.search(locator):
                # Omit evidence items with uncleanable PII (FR-013)
                continue

            # If entire locator is redacted, omit it
            if locator == REDACTED:
                continue

            cleaned_evidence.append(Evidence(
                source_type=ev.source_type,
                locator=locator,
            ))

        result.append(RuntimeOnlyEdge(
            from_id=edge.from_id,
            to_id=edge.to_id,
            env=edge.env,
            confidence=edge.confidence,
            evidence=cleaned_evidence,
            deployed_ref=edge.deployed_ref,
        ))

    return result


def _redact_sensitive_in_string(s: str) -> str:
    """Replace sensitive patterns in a string with [REDACTED]."""
    import re
    from tendril.llm.redactor import REDACTED

    # Authorization header values
    s = re.sub(r'Bearer\s+\S+', f'Bearer {REDACTED}', s)
    s = re.sub(r'Basic\s+\S+', f'Basic {REDACTED}', s)

    # API keys in query parameters
    s = re.sub(r'(api_key=)[^&\s]+', rf'\1{REDACTED}', s)
    s = re.sub(r'(token=)[^&\s]+', rf'\1{REDACTED}', s)
    s = re.sub(r'(key=)[^&\s]+', rf'\1{REDACTED}', s)

    return s
