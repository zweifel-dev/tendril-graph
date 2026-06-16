# Feature Specification: M10 — Telemetry Cross-Validation (Datadog)

**Feature Branch**: `005-m10-telemetry-datadog`

**Created**: 2026-06-15

**Status**: Draft

**Input**: M10 Telemetry (Datadog) — three-way static/runtime reconciliation, DatadogTelemetryProvider, CrossValidator, capability probing, divergence report with runtime-only edges persisted to the dependency graph.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Surface Undeclared Runtime Dependencies (Priority: P1)

An operator runs a graph build and wants to know whether any service-to-service calls are
happening in production that the static analysis did not capture. Tendril queries the
telemetry provider (Datadog APM service map) and returns a **divergence report** that
identifies edges present in runtime traces but absent from the static graph. Those
runtime-discovered edges are written into the dependency graph with `provenance=observed`
and `confidence=high`, making them available to every downstream query and agent tool.

**Why this priority**: The highest-value output of telemetry cross-validation is the
`runtime_only` set — undeclared dependencies that are live in production. These are the
most actionable alerts and the core reason M10 exists.

**Independent Test**: Given a Datadog fixture with 3 APM service edges (2 matching static
graph, 1 unknown to static analysis), running reconcile for that environment produces a
divergence report with `confirmed` count = 2 and `runtime_only` count = 1; the
runtime-only edge is written to the graph store with `provenance=observed`,
`confidence=high`, and non-empty `evidence`.

**Acceptance Scenarios**:

1. **Given** a completed static graph for `env=prod` and a Datadog APM fixture with one
   service edge not present in the static graph, **When** `reconcile(env="prod")` is
   called, **Then** the divergence report contains that edge in `runtime_only` and
   the graph store contains a new `DEPENDS_ON@prod` edge with `provenance=observed`,
   `confidence=high`, and an `evidence` list referencing the APM source.

2. **Given** the same reconcile run, **When** the two edges that exist in both static and
   runtime are examined, **Then** both appear in `confirmed` with their original
   `provenance` and `confidence` unchanged.

3. **Given** a static graph edge with no corresponding runtime traffic, **When** the
   reconcile report is produced, **Then** that edge appears in `static_only` — flagged
   for human review but not deleted from the graph.

---

### User Story 2 — Capability-Aware Degradation (Priority: P1)

An operator configures Tendril with Datadog credentials for an estate where only the Logs
product is enabled (APM is not instrumented). Tendril probes the available capabilities per
environment before attempting to pull any data, falls back to the available signal (logs),
and produces whatever reconciliation is possible — without failing the build or pretending
APM data exists.

**Why this priority**: Capability detection and graceful degradation is a non-negotiable
design invariant (CLAUDE.md Invariant 5). A missing telemetry capability must never fail
the run or produce a misleading result.

**Independent Test**: Given a fixture that declares only `logs` capability (APM absent),
running `reconcile()` produces a partial divergence report sourced from log analysis only;
the report metadata records which capabilities were probed, which were active, and which
were skipped; exit code is 0.

**Acceptance Scenarios**:

1. **Given** a Datadog fixture with `apm=false, logs=true, rum=false`, **When**
   `probe(env)` is called, **Then** a `Capabilities` object is returned reflecting those
   values; subsequent data-fetch calls use only the active capabilities.

2. **Given** all Datadog capabilities returning empty results, **When** reconcile runs,
   **Then** the divergence report has empty sets for all three categories, report metadata
   indicates "no runtime signal", and the process exits cleanly with no errors.

3. **Given** Datadog credentials are missing entirely (env vars unset, no config section),
   **When** a graph build is triggered, **Then** no telemetry step runs, a single INFO log
   message is emitted stating telemetry is unconfigured (per FR-007), and all M0–M9
   outputs are unaffected.

---

### User Story 3 — Multi-Signal Edge Discovery (Priority: P2)

Beyond the APM service map, Tendril can pull runtime signal from distributed traces, log
parsing, and browser RUM. Each signal source independently contributes observed edges.
Together they give a more complete runtime picture than any single source alone. The operator
can see which signal source contributed each runtime-discovered edge in the evidence chain.

**Why this priority**: The APM service map is the most reliable single signal but may not
be enabled in all estates. Trace-level and log-level extraction extend coverage; RUM
captures browser-to-API edges that pure backend tracing misses. Supporting all four gives
maximum recall.

**Independent Test**: Given fixtures for APM service dependencies, span search results,
structured log lines, and RUM events each contributing a distinct edge, `reconcile()`
produces observed edges with evidence referencing the correct signal source for each. The
fixture includes all four sources: `service_dependencies_prod.json` (APM),
`edges_from_traces_prod.json` (traces), `edges_from_logs_prod.json` (logs),
`edges_from_rum_prod.json` (RUM), each contributing at least one distinct edge. The
conformance fixture at `tests/fixtures/conformance/telemetry/datadog/` must cover all
four methods.

**Acceptance Scenarios**:

1. **Given** APM service map data, **When** `service_dependencies(env)` is called, **Then**
   a list of `ObservedEdge` records is returned, each with `capability="apm"` and a
   locator referencing the Datadog API source.

2. **Given** distributed trace span data showing a caller→callee relationship not visible
   in the APM service map, **When** `edges_from_traces(env)` is called, **Then** that
   edge appears as an additional `ObservedEdge` with `capability="traces"`.

3. **Given** structured log lines containing outbound HTTP call records, **When**
   `edges_from_logs(env)` is called, **Then** extracted caller→callee pairs appear as
   `ObservedEdge` records with `capability="logs"`.

4. **Given** RUM resources showing XHR/fetch calls from a browser repo to an API repo,
   **When** `edges_from_rum(env)` is called, **Then** those service pairs appear as
   `ObservedEdge` records with `capability="rum"`.

---

### User Story 4 — Runtime Edges Visible to Query and Agent Tools (Priority: P2)

After a reconcile run, a coding agent calls `find_relevant_repos` or `impact_analysis`.
Runtime-discovered edges appear in those results alongside static edges, with their
`provenance=observed` label visible so the agent knows the edge came from live traffic
rather than source analysis. The `explain_edge` tool returns the APM/trace source
in the evidence chain.

**Why this priority**: The graph is only useful if all edges — static and observed — are
queryable through the same interface. Telemetry-discovered edges must be first-class
citizens in the graph store.

**Independent Test**: After a reconcile that writes a runtime-only edge, calling
`QueryEngine.explain_edge(from_id, to_id, env)` returns a result containing
`provenance=observed`, `confidence=high`, and evidence listing the Datadog APM source.

**Acceptance Scenarios**:

1. **Given** a runtime-only edge written to the graph by reconcile, **When**
   `explain_edge(from_id, to_id, env)` is called via the MCP server, **Then** the
   response includes `provenance="observed"`, `confidence="high"`, non-empty `evidence`,
   and `deployed_ref` (inherited from the static graph for the same environment, or null
   if the repo is not in the static graph). If the runtime-only edge's `from_repo` or
   `to_repo` is absent from the static graph (no DEPLOYED_AS record), `deployed_ref` on
   the written DEPENDS_ON edge is null; this null value is returned verbatim by
   `explain_edge` with no error.

2. **Given** a `find_relevant_repos` call, **When** the target repo is reachable only via
   a runtime-discovered edge, **Then** that repo appears in the results with
   `provenance="observed"` on the connecting edge.

---

### User Story 5 — Fixture-Mode for Testing Without Live Credentials (Priority: P2)

All M10 logic can be exercised against recorded Datadog API fixtures, with no live
credentials required. The CI suite runs entirely offline. A fixture directory can stand
in for the Datadog API, enabling contributors to add new test cases without Datadog access.

**Why this priority**: CLAUDE.md mandates fixtures over live calls in tests. M10 must
conform to this convention so CI remains zero-credential.

**Independent Test**: The full M10 integration test suite passes with `pytest tests/` on a
clean checkout, with no `DD_API_KEY` or `DD_APP_KEY` environment variables set.

**Acceptance Scenarios**:

1. **Given** `fixture_dir` is passed to `DatadogTelemetryProvider`, **When** any data
   method is called, **Then** responses are loaded from JSON files in that directory
   instead of calling the live Datadog API.

2. **Given** a fresh checkout with no Datadog credentials, **When** `pytest tests/` is
   run, **Then** all M10 tests pass.

---

### Edge Cases

- **No APM data for an env**: `probe()` returns `apm=false`; `service_dependencies()` is
  not called; the reconcile report notes the gap and exits cleanly.
- **Partial APM data** (some services instrumented, others not): observed edges are
  recorded for instrumented services only; un-instrumented services produce no
  `runtime_only` entry and no false "declared but no traffic" flag.
- **Service name mismatch** between Datadog service name and graph `repo_id` (e.g.,
  `payment-svc` vs `github:acme/payment-service`): identity resolution uses the same
  reverse-index lookup as the static pass; unmatched service names are recorded as
  unknowns with `reason="no-index-match"`.
- **Duplicate edges from multiple signals** (APM + logs report the same caller→callee):
  the edge is deduplicated; evidence accumulates from all contributing signals.
- **API rate limit from Datadog**: affected capability is marked as degraded with
  `reason='rate-limited'`; other capabilities proceed; the reconcile report notes the
  rate-limited signal; exit code 0. Data from capabilities that completed before the rate
  limit was encountered is retained and contributes to the DivergenceReport.
- **Datadog API returns unexpected schema**: affected call is skipped with a WARNING log
  quoting the unexpected field; remaining signals are processed normally. An 'unexpected
  schema' is defined per FR-008.
- **Static graph has no edges for the queried env** (env not yet built): reconcile
  produces `confirmed=[]`, `static_only=[]`, `runtime_only=[all resolved runtime edges]`.
  This is not an error (see FR-027).

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST implement a `TelemetryProvider` plugin for Datadog that
  exposes capability probing, service-dependency querying, trace-level edge extraction,
  log-level edge extraction, and RUM-level edge extraction — each independently callable.
  `DatadogTelemetryProvider` MUST implement every method in the `TelemetryProvider` ABC
  defined in `tendril/plugins/base.py`. Any method not supported by Datadog must raise
  `NotImplementedError` with a message explaining the gap. The provider must declare its
  capabilities via a `tendril-plugin.toml` manifest. The `probe(env: str) -> Capabilities`
  signature MUST match the `TelemetryProvider` ABC exactly. Callers MUST invoke
  `probe(env)` before calling any data method for that environment. Data methods called
  without a prior successful probe for the same env MUST raise a `ProbeRequiredError`.
  The intent is to ensure capability checks are never skipped, not to prevent independent
  testing.

- **FR-002**: The system MUST implement a `CrossValidator` that performs three-way
  reconciliation: `confirmed = static ∩ runtime`, `static_only = static − runtime`,
  `runtime_only = runtime − static`, and returns a `DivergenceReport` containing all
  three sets with per-edge evidence. The `confirmed` set is informational only — it does
  not alter the existing static DEPENDS_ON edges in the graph store. `confirmed` edges
  are not re-written, re-tagged, or modified in any way.

- **FR-003**: The system MUST probe available Datadog capabilities per environment before
  fetching any data. `probe()` MUST be called once per `(env)` per `reconcile()` call.
  Probe results MUST NOT be cached across `reconcile()` calls. Within a single
  `reconcile()` call, each capability is probed exactly once. Capabilities not confirmed
  as active MUST be skipped with a DEBUG-level log: 'capability {cap} inactive for env
  {env} — skipping'. This is distinct from missing credentials (INFO level per FR-007)
  and from probe failures (WARNING level per this section). If `probe(env)` raises any
  exception (network error, API error, timeout), the capability MUST be treated as
  inactive (`false`); a WARNING-level log MUST be emitted: 'probe failed for capability
  {cap} in env {env}: {error}'; reconcile continues with remaining capabilities. The probe
  mechanism for each capability MUST call the lowest-cost Datadog API endpoint that
  confirms the capability is active and data is available for the given env. For APM:
  `GET /api/v1/services` (or equivalent service catalog endpoint) with a 1-result limit.
  For Logs: `POST /api/v2/logs/events/search` with time range = last 1 minute and result
  limit = 1. For Traces: `GET /api/v1/service_dependencies` with a 1-result limit and
  dry-run semantics if available. For RUM: `POST /api/v2/rum/events/search` with result
  limit = 1. A 200 response with any data (even empty) constitutes active; a 404 or
  empty-data response constitutes inactive.

- **FR-004**: The system MUST write every `runtime_only` edge into the graph store as a
  `DEPENDS_ON` edge with `provenance=observed`, `confidence=high`, and non-empty
  `evidence` referencing the Datadog signal source and environment. Each runtime-only
  DEPENDS_ON edge must also carry the `deployed_ref` inherited from the static graph for
  the same environment and repository; if the repository is absent from the static graph,
  `deployed_ref` is null. The `confidence=high` assignment for APM service-map data
  reflects that it represents aggregated, observed production traffic and is the most
  reliable signal available. For trace- and log-derived edges, `confidence=high` is
  assigned only when the caller→callee pair appears in more than one span/log line;
  single-occurrence trace or log edges are assigned `confidence=medium`.

- **FR-005**: Static graph edges (from M0–M9) MUST NOT have their `provenance`,
  `confidence`, or `evidence` modified by the telemetry pass. Secret redaction (FR-013)
  applied during the telemetry pass operates only on newly constructed `ObservedEdge.evidence`
  values and `DivergenceReport` output. It MUST NOT re-process or modify evidence fields
  on existing static-graph edges.

- **FR-006**: The Datadog provider MUST support a `fixture_dir` parameter that substitutes
  local JSON files for live API responses, enabling zero-credential testing.

- **FR-007**: When Datadog credentials are absent or incomplete, the telemetry step MUST
  be skipped and a single INFO-level log message MUST be emitted: 'Datadog telemetry
  unconfigured (missing: {fields}); skipping telemetry pass.' The build MUST complete
  successfully using only the M0–M9 outputs. For the purposes of this requirement,
  credentials are "complete" when `DD_API_KEY`, `DD_APP_KEY`, and `DD_SITE` are all
  present and non-empty (via environment variables or `[telemetry.datadog]` config
  section).

- **FR-008**: When a Datadog API call fails (network error, rate limit, unexpected schema),
  the affected signal source MUST be marked degraded in the report metadata using the
  degradation notice schema defined in the DivergenceReport entity; other signal sources
  MUST continue processing; the overall build exit code MUST remain 0. An 'unexpected
  schema' is defined as a response where one or more required fields (as specified in the
  Datadog API documentation for that endpoint) are absent or have an incompatible type.
  Responses containing unrecognised additional fields are accepted without error
  (forward-compatible parsing). A rate limit encountered mid-run (after some capabilities
  have succeeded) does not invalidate results already fetched; data from capabilities that
  completed before the rate limit was encountered is retained and contributes to the
  DivergenceReport. Datadog rate limits apply at the API key level and may affect multiple
  capabilities in the same run. When a rate-limit response is received, the affected
  capability is marked degraded with `reason='rate-limited'`. Other capabilities sharing
  the same API key continue to be attempted; they may also encounter rate limits and will
  be independently marked degraded. No attempt is made to honour the `X-RateLimit-Reset`
  header in v0.

- **FR-009**: Service names returned by Datadog MUST be resolved to graph `repo_id`s via
  the existing reverse index; unresolvable service names MUST be recorded in the report's
  `unknowns` list with `reason="no-index-match"`, not silently dropped.

- **FR-010**: Duplicate edges contributed by multiple signal sources (APM + logs + traces)
  for the same `(from, to, env)` MUST be merged into one `ObservedEdge`; evidence from
  all contributing signals MUST appear in the merged edge's evidence list. When evidence
  from multiple sources is merged, the resulting `evidence` list MUST be sorted
  deterministically by `(capability, iso_timestamp, api_path)` to ensure reproducible
  output across runs.

- **FR-011**: The `DatadogTelemetryProvider` MUST NOT make any write calls to the Datadog
  API; all operations are read-only.

- **FR-012**: The telemetry pass MUST be independently executable (CLI flag or explicit API
  call) in addition to running automatically at the end of a full graph build.

- **FR-013**: Sensitive values present in Datadog log lines or trace metadata MUST be
  redacted before they are stored in evidence locators or the graph. For the purposes of
  this requirement, 'sensitive values' in telemetry contexts includes: HTTP Authorization
  header values, Bearer tokens, API keys in query parameters (e.g., `api_key=`,
  `token=`), password fields, and any value whose key name matches the PII field set
  defined in M9's ResidencyGate. Datadog service names and span operation names are not
  considered sensitive. PII patterns (email addresses, phone numbers) found in Datadog
  log message bodies parsed during `edges_from_logs()` MUST be redacted before the log
  line evidence is stored. Log lines where PII cannot be cleanly separated from the
  caller/callee fields MUST be skipped entirely rather than stored with PII. Redacted
  evidence items MUST retain the locator structure with the sensitive portion replaced by
  `[REDACTED]`. Evidence locators where the entire value is sensitive (no safe portion)
  MUST be omitted from the evidence list entirely. The `DivergenceReport` and graph edge
  evidence MUST never contain the unredacted value. The PII patterns defined in M9's
  ResidencyGate apply to telemetry evidence. If telemetry evidence passes secret redaction
  but still contains PII after redaction, that evidence item MUST be omitted. Unlike M9
  (which blocks the entire LLM call), M10 omits only the affected evidence item and
  continues; no telemetry edge is blocked solely due to PII in a single evidence item.
  The `DivergenceReport` object MUST pass through secret redaction before being serialized
  to JSON (stdout output, MCP response, or disk write). The `metadata` fields and evidence
  locators in all three edge sets MUST be screened. Datadog API credentials (`DD_API_KEY`,
  `DD_APP_KEY`) MUST NEVER be stored in evidence, logs, or graph edges; this is a
  corollary of FR-011 (read-only) and applies with equal force.

- **FR-014**: All time-windowed Datadog queries (traces, logs, RUM) MUST use a configurable
  lookback window; the default is 24 hours. The window is applied at query time using the
  environment's clock. The lookback duration must be configurable via
  `TENDRIL_DD_LOOKBACK_HOURS` env var or `[telemetry.datadog] lookback_hours` config key.

- **FR-015**: All Datadog data methods MUST handle paginated responses and collect all pages
  up to a configurable maximum result count (default 1 000 per method per env). Results
  exceeding the limit are truncated; the DivergenceReport metadata MUST record a
  `truncated: true` flag and the count of discarded records for each affected method.

- **FR-016**: Log-based edge extraction (FR-001) MUST parse structured JSON log lines that
  contain both a `service` field (caller) and at least one of: `peer.service`, `http.url`,
  or `out.host` (callee). Trace-based edge extraction MUST derive caller→callee pairs from
  spans where `span.kind == 'client'` and either `peer.service` or `out.host` is present.
  Lines or spans that lack these fields MUST be silently skipped; no error is raised.

- **FR-017**: Edges in the `static_only` set MUST be surfaced in the DivergenceReport and
  logged at INFO level with message 'static-only dependency: {from_id} → {to_id} @ {env}
  — no runtime traffic observed'. Static-only edges MUST NOT be deleted from the graph
  store, downgraded in confidence, or modified in any way by the telemetry pass.

- **FR-018**: The telemetry reconcile pass MUST run automatically at the end of
  `tendril graph build` when Datadog credentials are present and complete (per FR-007
  definition of 'complete'). It MUST also be executable as a standalone command:
  `tendril telemetry reconcile --env <env>` which runs reconcile only, assuming a static
  graph already exists in the graph store. The standalone `tendril telemetry reconcile
  --env <env>` command MUST write its DivergenceReport to stdout as JSON (same schema as
  the DivergenceReport entity) and also persist runtime-only edges to the graph store. The
  `--env` flag is required; omitting it is an error with exit code 1 and a usage message.

- **FR-019**: No Datadog API call is retried in v0. On any failure (network error, HTTP
  4xx/5xx, timeout, unexpected schema), the affected capability is marked degraded and
  processing continues. This is explicit policy, not an omission.

- **FR-020**: The `reconcile()` operation is idempotent with respect to the graph store.
  If a runtime-only edge already exists in the graph with `provenance=observed`, a
  subsequent reconcile for the same environment MUST update its evidence (merge new
  sources) and `deployed_ref` but MUST NOT create a duplicate edge. The upsert key is
  `(from_id, to_id, env, provenance=observed)`.

- **FR-021**: Evidence locators for telemetry-sourced edges MUST use the format
  `datadog:{capability}:{env}:{api_path}@{iso_timestamp}` where `api_path` is the Datadog
  API endpoint path (e.g., `/api/v1/service_dependencies`) and `iso_timestamp` is the UTC
  time the query was issued. Secret values MUST NOT appear in the api_path or timestamp
  fields.

- **FR-022**: If writing a runtime-only DEPENDS_ON edge to the graph store raises an error,
  the error MUST be logged at ERROR level including the `(from_id, to_id, env)` triple;
  that edge is skipped; remaining edges continue to be written; the overall reconcile exit
  code remains 0. The failed edge appears in `DivergenceReport.metadata` as a degradation
  notice with `reason='store-write-error'`.

- **FR-023**: Datadog service names MUST be resolved to graph `repo_id`s using a two-step
  lookup against the ReverseIndex: (1) Exact match on service name as a provider identity
  value of `kind=service-tag`. If no match, (2) exact match on service name as a string
  suffix of any indexed provider identity URL hostname (e.g., service name
  `payment-service` matches `https://payment-service.internal`). If neither step matches,
  the service name is recorded in `unknowns` with `reason='no-index-match'`. The
  `kind=service-tag` identity type is a new provider identity kind added in M10; VCS and
  CI/CD providers may register it by including `{"kind": "service-tag", "value":
  "<datadog-service-name>"}` in their ProviderIdentity output. No fuzzy or partial
  matching is performed in v0. A service name must match exactly (case-sensitive) to a
  known provider identity value or URL hostname suffix. Partial matches, edit-distance
  matches, and case-insensitive matches are out of scope for v0. If a service name matches
  more than one reverse-index entry (ambiguous match), it is recorded in `unknowns` with
  `reason='ambiguous-match'` and `candidates=[list of matched repo_ids]`. Ambiguous
  matches are NOT written as graph edges.

- **FR-024**: The `reconcile()` method MUST accept calls for any environment regardless of
  whether the static graph has entries for that env. If the static graph is empty for the
  given env, the static set is treated as empty (not an error). However, if no static
  graph has ever been built (the graph store is empty entirely), a WARNING is logged: 'No
  static graph found in store — all runtime edges will appear as runtime_only.'

- **FR-025**: All Datadog API calls (probe and data methods) MUST complete within a
  configurable per-call timeout; the default is 60 seconds. The timeout is configurable
  via `TENDRIL_DD_TIMEOUT_SECONDS` env var or `[telemetry.datadog] timeout_seconds` config
  key. A call that exceeds the timeout is treated as an error per FR-008 (capability
  marked degraded, reason='error').

- **FR-026**: If the total number of resolved `ObservedEdge` records for a single reconcile
  call exceeds 10 000, a WARNING is logged and processing continues normally. No hard cap
  is enforced in v0; the limit is a signal for operators that the estate may be too large
  for sequential reconciliation.

- **FR-027**: At the end of each `reconcile()` call, the system MUST log at INFO level a
  reconcile summary: 'Reconcile complete for env {env}: confirmed={N}, static_only={N},
  runtime_only={N}, unknowns={N}, degraded_capabilities={list}, elapsed={seconds}s'. If
  `reconcile(env)` is called and the static graph has no DEPENDS_ON or DEPLOYED_AS entries
  for `env`, the static edge set is treated as empty; `confirmed` and `static_only` will
  be empty; `runtime_only` contains all resolved runtime edges for that env. This is not
  an error.

### Key Entities

- **ObservedEdge**: A runtime-witnessed service-to-service call: `from_service` (Datadog
  service name), `to_service`, `env`, `capability` (apm | traces | logs | rum), `evidence`
  list (formatted per FR-021). May be unresolved (no graph `repo_id` match) until identity
  resolution runs.

- **DivergenceReport**: Result of reconciliation for one environment: `confirmed` (edges
  in both static and runtime), `static_only` (declared but no observed traffic),
  `runtime_only` (observed but not declared), `env`, `capabilities_probed` (dict of
  capability → active bool), `unknowns` (service names not matched to any repo),
  `metadata` (signal degradation notices). The `metadata` field is a list of degradation
  notice objects, each with schema: `{capability: str, reason:
  'inactive'|'rate-limited'|'error'|'schema-error'|'truncated'|'store-write-error',
  message: str}`. The `unknowns` field is a list of objects with schema: `{service: str,
  env: str, capability: str, reason: 'no-index-match'|'ambiguous-match', candidates:
  list[str]|null}` where `candidates` is populated only when `reason='ambiguous-match'`.

- **Capabilities**: Per-environment probe result: `apm: bool`, `logs: bool`, `rum: bool`,
  `traces: bool`. Returned by `probe(env)` before data is fetched.

**Two-stage resolution note**: Telemetry data is collected as `ObservedEdge` records
(pre-resolution, using Datadog service names) and then resolved to graph `repo_id`s via
FR-023 before being written as `DEPENDS_ON` graph edges. The `DivergenceReport` operates
on resolved `repo_id`s for `confirmed`, `static_only`, and `runtime_only` sets; unresolved
service names go to `unknowns` and are never written to the graph.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a Datadog fixture with 3 APM service edges (2 matching static graph,
  1 unknown), `reconcile(env="prod")` returns a report with `len(confirmed) == 2`,
  `len(runtime_only) == 1`; the runtime-only edge is present in the graph store with
  `provenance="observed"` and `confidence="high"`. The fixture format for this scenario
  is: `tests/fixtures/conformance/telemetry/datadog/service_dependencies_prod.json`
  containing a list of service pairs, two of which match `repo_id`s present in the static
  graph and one of which does not. The fixture must be readable by
  `DatadogTelemetryProvider(fixture_dir=...)`.

- **SC-002**: Given a fixture where all Datadog capabilities return empty results,
  `reconcile()` exits with code 0, produces a report with all sets empty, and no
  M0–M9 graph edges are modified.

- **SC-003**: Given a fixture where only `logs` capability is active (APM disabled), the
  divergence report is produced from log signal only; `capabilities_probed["apm"] == False`
  appears in the report metadata; no APM call is attempted.

- **SC-004**: Given a runtime-only edge written to the graph by reconcile, `explain_edge`
  returns it with `provenance="observed"`, `confidence="high"`, and evidence referencing
  the Datadog source; existing static edges for the same env are unchanged. If the
  runtime-only edge's `from_repo` or `to_repo` is absent from the static graph (no
  DEPLOYED_AS record), `deployed_ref` on the written DEPENDS_ON edge is null; this null
  value is returned verbatim by `explain_edge` with no error.

- **SC-005**: Given a fixture with a Datadog service name (`payment-svc`) that does not
  match any reverse-index entry, the reconcile report's `unknowns` list contains an entry
  with `service="payment-svc"` and `reason="no-index-match"`; the build exits with
  code 0.

- **SC-006**: Given APM and log fixtures that both report the same `(caller, callee, prod)`
  pair, the graph store contains exactly one `DEPENDS_ON@prod` edge for that pair;
  its evidence list references both the APM and log sources, sorted deterministically by
  `(capability, iso_timestamp, api_path)`.

- **SC-007**: `pytest tests/` passes all tests — including all M10 tests — with no
  `DD_API_KEY` or `DD_APP_KEY` environment variables set (fixture-mode only).

- **SC-008**: All 175 existing M0–M9 tests continue to pass after M10 is introduced;
  importing M10 modules is not required for any M0–M9 test to succeed.

- **SC-009**: Given a Datadog fixture where `traces=false` (distributed traces not
  enabled), the divergence report is produced from the remaining active signals (APM, logs,
  RUM); `capabilities_probed['traces'] == False` appears in report metadata; no trace
  query is attempted.

- **SC-010**: Given a Datadog fixture where `rum=false` (RUM not enabled), the divergence
  report is produced from remaining active signals; `capabilities_probed['rum'] == False`
  appears in report metadata; no RUM query is attempted.

- **SC-011**: Given a `DatadogTelemetryProvider` configured with an unreachable endpoint
  (connection refused), `reconcile()` exits with code 0; all four capabilities are recorded
  in `capabilities_probed` with `reason='error'` in the degradation metadata; the resulting
  DivergenceReport has all three sets empty; no exception propagates to the caller.

---

## Acceptance Gate

Before M10 is considered complete, `DatadogTelemetryProvider` MUST pass the
`TelemetryProvider` conformance suite in `tests/conformance/telemetry/`. The conformance
suite is the executable definition of the contract (per CLAUDE.md). This gate is mandatory
and must be run after both M5 and M10 are complete for US4 integration tests.

---

## Assumptions

- Datadog is the only telemetry provider implemented in M10. The `TelemetryProvider` ABC
  already exists in `tendril/plugins/base.py` from M0; M10 adds the Datadog implementation
  behind that contract. Other providers (Grafana, Honeycomb, New Relic) remain future work.

- v0 reconciliation is sequential and per-environment. For estates with many environments,
  total reconcile time scales linearly. A v1 parallelism path (concurrent env
  reconciliation) is planned but out of scope for M10. This is an explicit known
  limitation.

- "Service name" in Datadog APM maps to the `service:` tag on spans. Mapping from Datadog
  service name to graph `repo_id` uses a two-step reverse-index lookup as specified in
  FR-023. The `kind=service-tag` provider identity type is introduced in M10.

- Fixture format: each data method (`service_dependencies`, `edges_from_traces`,
  `edges_from_logs`, `edges_from_rum`) loads from a separate JSON file named after the
  method and environment (e.g., `service_dependencies_prod.json`), consistent with the
  fixture convention already established in M1–M9.

- The `static_only` set (declared in source, no observed traffic) is informational only
  in M10 — it is surfaced in the report (with INFO-level logging per FR-017) but does not
  trigger automatic edge deletion or confidence downgrade. Human review is the intended
  action path.

- Datadog credentials are supplied via environment variables (`DD_API_KEY`, `DD_APP_KEY`,
  `DD_SITE`) or a `[telemetry.datadog]` config section. The same `LLMConfig`-style
  resolution pattern from M9 is used: env var > config file > absent (skip with INFO log
  per FR-007).

- M10 depends on M4 (static graph must exist to cross-validate against) and on the
  `GraphStore` interface from M0 for writing `runtime_only` edges. US4 (runtime edges
  visible to query tools via `explain_edge`) requires `QueryEngine` from M5. M10 is
  therefore NOT fully independent of M5. The dependency is limited to the query layer:
  `CrossValidator` and `DatadogTelemetryProvider` themselves have no M5 dependency (they
  write to `GraphStore` directly). US4 integration tests must be run after both M5 and
  M10 are complete. This is an explicit dependency: M10 depends on M4 (static graph) and
  M5 (for US4 query integration only).

- The `CrossValidator` lives in `tendril/core/cross_validate.py` and takes a `GraphStore`
  and a `TelemetryProvider` as constructor arguments — no global state.

- The import of `tendril.llm.redactor.SecretRedactor` in `cross_validate.py` is an
  acceptable coupling because `tendril.llm` is always present (it is an installed module
  from M9, not an optional dependency). The coupling must be documented in code. If
  `tendril.llm` is ever made optional, the redaction logic must be extracted to a shared
  utility module. This is tracked as a known technical debt item.

- When multiple `DEPLOYED_AS` records exist for the same repository and environment in the
  static graph (e.g., from canary or blue/green deployments), the `deployed_ref` for
  runtime-only edges is taken from the most recent deployment record by timestamp. If no
  timestamp is available, the first record encountered is used and a WARNING is logged.
