# Research: M10 — Telemetry Cross-Validation (Datadog)

**Date**: 2026-06-15 | **Status**: Complete

## R-001: Datadog REST API Endpoints

### Decision

Use the following Datadog API endpoints for each capability:

| Capability | Data Endpoint | Probe Endpoint |
|-----------|---------------|----------------|
| APM | `GET /api/v1/service_dependencies?env={env}` | `GET /api/v1/services?env={env}` (1-result check) |
| Traces | `POST /api/v2/spans/events/search` | Same endpoint with `limit=1` |
| Logs | `POST /api/v2/logs/events/search` | Same endpoint with `from=now-1m`, `limit=1` |
| RUM | `POST /api/v2/rum/events/search` | Same endpoint with `limit=1` |

### Rationale

- APM service dependencies is a precomputed, non-paginated aggregate — the highest-value
  single endpoint because it gives the full service-to-service call graph in one call.
- Trace, log, and RUM search endpoints use cursor-based pagination (`meta.page.after`),
  max 1,000 events per page.
- Probe endpoints are the lowest-cost calls that confirm capability is active (per FR-003).

### Alternatives Considered

- v2 Service Catalog API (`GET /api/v2/services/definitions`): Richer metadata but
  heavier response and not needed for probing. The v1 services list is lighter.
- v2 spans search vs v1 trace search: v2 is the current standard; v1 is deprecated.

### Authentication

All calls use HTTP headers (never query parameters, to avoid key leakage in logs):
- `DD-API-KEY: {api_key}` — organization API key
- `DD-APPLICATION-KEY: {app_key}` — application key

### Base URL from DD_SITE

Pattern: `https://api.{DD_SITE}` for all sites.

| DD_SITE | Base URL |
|---------|----------|
| `datadoghq.com` (US1, default) | `https://api.datadoghq.com` |
| `us3.datadoghq.com` | `https://api.us3.datadoghq.com` |
| `us5.datadoghq.com` | `https://api.us5.datadoghq.com` |
| `datadoghq.eu` (EU1) | `https://api.datadoghq.eu` |
| `ap1.datadoghq.com` | `https://api.ap1.datadoghq.com` |
| `ddog-gov.com` (US1-FED) | `https://api.ddog-gov.com` |

### Pagination Model

- **APM service_dependencies**: Not paginated (aggregated view).
- **Traces/Logs/RUM search**: Cursor-based. Response includes `meta.page.after`;
  pass as `page.cursor` in next request. Max `limit=1000` per page.

### Rate Limiting

Response headers: `X-RateLimit-Limit`, `X-RateLimit-Period`,
`X-RateLimit-Remaining`, `X-RateLimit-Reset`. HTTP 429 on limit hit.
Per FR-019, v0 does not retry or honor reset — marks capability as degraded.

### Verification Note

Endpoint paths and response schemas should be verified against
`https://docs.datadoghq.com/api/latest/` before implementation, particularly:
- Whether `GET /api/v1/service_dependencies` is still active or superseded by v2
- Exact query syntax for `span_kind` filtering (`@span.kind` vs `span_kind`)
- Whether `/api/v1/services` remains the lightest APM probe

---

## R-002: Fixture Format and Loading Convention

### Decision

Follow the established fixture convention:
- Location: `tests/fixtures/conformance/telemetry/datadog/`
- File naming: `{method}_{env}.json` (e.g., `service_dependencies_prod.json`)
- Loading: `DatadogTelemetryProvider(fixture_dir=Path(...))` constructor parameter
- Parsing: `json.loads(path.read_bytes())` returning typed IR objects

### Rationale

This matches the existing pattern used by `GitHubActionsProvider` (accepts `fixture_dir`,
globs for files, loads JSON) and the broader convention at
`tests/fixtures/conformance/{type}/{name}/`.

### Alternatives Considered

- YAML fixtures: Rejected — all existing fixtures are JSON; YAML adds a dependency
  and breaks convention.
- Embedded fixtures in test files: Rejected — external files are easier to update and
  share across test methods.

### Fixture Files Required

```text
tests/fixtures/conformance/telemetry/datadog/
├── capabilities_prod.json              # Probe result: {apm: true, logs: true, traces: true, rum: true}
├── capabilities_logs_only.json         # Partial: {apm: false, logs: true, traces: false, rum: false}
├── capabilities_none.json              # All inactive
├── service_dependencies_prod.json      # APM service pairs (3 edges: 2 matching static, 1 unknown)
├── edges_from_traces_prod.json         # Span-derived edges
├── edges_from_logs_prod.json           # Log-parsed edges
├── edges_from_rum_prod.json            # RUM browser-to-API edges
├── service_dependencies_staging.json   # Env variant for multi-env tests
└── edges_from_logs_prod_with_pii.json  # Log lines containing PII for redaction tests
```

---

## R-003: service-tag Identity Type for Reverse Index

### Decision

Add `SERVICE_TAG = "service-tag"` to the existing `IdentityClass` enum in
`tendril/models/ir.py`. This is the minimal change that integrates with the existing
`ReverseIndex` normalization pipeline.

### Rationale

The `IdentityClass` enum is a finite, hardcoded set: `NETWORK`, `LOGICAL`, `DEPLOY`,
`ARTIFACT`, `ASYNC`, `DATA`. Adding `SERVICE_TAG` follows the same pattern. The
`ReverseIndex._normalize()` method dispatches on class: `NETWORK` gets URL normalization,
all others get `lower().strip()`.

**Important**: FR-023 specifies case-sensitive exact match for service names. The default
normalization (`lower().strip()`) would break this. Two approaches:

1. **Add a `SERVICE_TAG` case to `_normalize()`** that returns the value unchanged
   (preserves case). Lookup then tries exact match first (which succeeds for case-sensitive
   service names), and the normalized fallback would also be exact.
2. **Skip normalization entirely for SERVICE_TAG** by checking in `add()` and only
   inserting into `_exact`, not `_normalized`.

**Chosen**: Option 1 — add `SERVICE_TAG` normalization that returns `value.strip()` (strip
whitespace but preserve case). This keeps the two-tier lookup (exact then normalized)
working correctly while honoring the case-sensitive requirement.

### Alternatives Considered

- Open-ended `identity_class: str` instead of enum: Rejected — would require redesigning
  the ReverseIndex dispatch logic and break type safety across the codebase.
- Reusing `LOGICAL` class for service tags: Rejected — `LOGICAL` normalizes to lowercase,
  violating FR-023's case-sensitive requirement. Conflating purposes also reduces clarity.

### Confidence Assignment

`SERVICE_TAG` identities should be assigned `Confidence.HIGH` in `_class_confidence()`
because they represent an explicit, human-authored mapping from Datadog service name to
repository.

### FR-023 Two-Step Lookup Implementation

The two-step lookup (1: exact SERVICE_TAG match, 2: hostname suffix match on NETWORK
identities) is implemented in `CrossValidator`, not in `ReverseIndex`:

```text
def resolve_service_name(service_name, reverse_index, env):
    # Step 1: Exact match on SERVICE_TAG
    entries = reverse_index.lookup(service_name, env)
    service_tag_matches = [e for e in entries if e.identity_class == IdentityClass.SERVICE_TAG]
    if len(service_tag_matches) == 1:
        return service_tag_matches[0].repo_full_name
    if len(service_tag_matches) > 1:
        return Unknown(reason="ambiguous-match", candidates=[...])

    # Step 2: Hostname suffix match on NETWORK identities
    # Scan all NETWORK entries for hostname ending with service_name
    ...
```

---

## R-004: CrossValidator Design

### Decision

`CrossValidator` lives at `tendril/core/cross_validate.py`. Constructor takes
`store: GraphStore` and `provider: TelemetryProvider`. The `reconcile(env)` method:

1. Calls `provider.probe(env)` → `Capabilities`
2. For each active capability, calls the corresponding data method → `list[ObservedEdge]`
3. Resolves Datadog service names to graph `repo_id`s via `ReverseIndex` (FR-023)
4. Deduplicates edges by `(from_id, to_id, env)`, merging evidence (FR-010)
5. Fetches existing static `DEPENDS_ON` edges for the env from the graph store
6. Computes set operations: `confirmed`, `static_only`, `runtime_only`
7. Applies secret redaction via `SecretRedactor` + `ResidencyGate` PII check (FR-013)
8. Writes `runtime_only` edges to graph store as `DEPENDS_ON` with upsert (FR-020)
9. Returns `DivergenceReport`

### Rationale

- Separating `CrossValidator` from `DatadogTelemetryProvider` keeps the provider pure
  (data fetching only) and the validator reusable across future telemetry providers.
- Constructor injection (no globals) aligns with Constitution Principle I.
- SecretRedactor import from `tendril.llm` is acceptable coupling (documented per spec
  Assumptions section).

### Alternatives Considered

- Merging CrossValidator into TraversalEngine: Rejected — telemetry reconciliation is
  logically distinct from static traversal and can run standalone.
- Making CrossValidator a plugin: Rejected — there's only one reconciliation algorithm
  and it orchestrates across the provider/store boundary; it's core logic, not a plugin.

---

## R-005: Secret Redaction in Telemetry Evidence

### Decision

Reuse the existing `SecretRedactor` from `tendril/llm/redactor.py` plus `ResidencyGate`
PII patterns. Apply redaction to:
- `ObservedEdge.evidence` locators before they're stored
- `DivergenceReport` before serialization (FR-013)

### Rationale

M9 already defines the redaction pipeline. The same patterns (Authorization headers,
Bearer tokens, API keys in query params, password fields, PII field set) apply to
telemetry evidence. No new patterns needed for M10.

### Key Rules from FR-013

- Redacted evidence retains locator structure with `[REDACTED]` replacing sensitive portion
- Evidence where entire value is sensitive → omitted from evidence list entirely
- Log lines where PII can't be separated from caller/callee fields → skipped entirely
- DD_API_KEY and DD_APP_KEY never appear in evidence, logs, or graph edges
- Unlike M9 (blocks entire LLM call on PII), M10 omits only the affected evidence item

---

## R-006: CLI Integration Design

### Decision

Two CLI integration points:

1. **Standalone command**: `tendril telemetry reconcile --env <env>` — runs reconcile
   against an existing static graph, writes DivergenceReport JSON to stdout, persists
   runtime-only edges to graph store. `--env` is required (exit code 1 if omitted).

2. **Automatic integration**: At the end of `tendril graph build`, when Datadog
   credentials are present and complete (per FR-007), run reconcile for each built
   environment. This is additive — appended after the existing LLM hybrid pass.

### Rationale

FR-012 requires both modes. FR-018 specifies the standalone command syntax. The automatic
integration follows the existing pattern where `graph build` conditionally runs the LLM
hybrid pass.

### Alternatives Considered

- Separate `tendril datadog` command group: Rejected — telemetry is a cross-cutting
  concern, not a Datadog-specific command. `tendril telemetry reconcile` is provider-
  agnostic in naming (the provider is selected by configuration).

---

## R-007: httpx as HTTP Client

### Decision

Use `httpx` (synchronous client) for live Datadog API calls. It is used only in live mode;
fixture mode bypasses HTTP entirely.

### Rationale

- `httpx` supports configurable timeouts, connection pooling, and custom headers natively
- Already a common Python HTTP client; lighter than `requests` with async capability
  available for future v1 parallelism
- Synchronous mode is sufficient for v0's sequential per-environment reconciliation

### Alternatives Considered

- `requests`: Viable but `httpx` is more modern and has better timeout semantics
- `aiohttp`: Async-only; v0 doesn't need async; adds complexity
- `urllib3` directly: Too low-level for the convenience needed

### Dependency Note

`httpx` is added to `pyproject.toml` as an optional dependency (e.g., `pip install -e ".[telemetry]"`
or included in `.[dev]`). Fixture mode has zero HTTP dependency.
