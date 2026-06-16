# Release Gate Checklist: M10 — Telemetry Cross-Validation (Datadog)

**Purpose**: Full release-gate requirements quality review — comprehensive coverage across
all scenario classes, with mandatory gating sections for secret/data safety, capability
degradation semantics, and identity resolution.

**Created**: 2026-06-15
**Feature**: [spec.md](../spec.md)
**Depth**: Full release gate (Q1: B)
**Signal grouping**: Multi-signal (APM/traces/logs/RUM checked as a group)
**Risk gates**: Secret & Data Safety · Capability Degradation Semantics · Identity Resolution

---

## Requirement Completeness

- [x] CHK001 - Does the spec define `deployed_ref` handling for runtime-only edges? FR-004 specifies `provenance`, `confidence`, and `evidence` but omits `deployed_ref`; US4 mentions it as "inherited or null" — is that requirement captured in FRs, not just acceptance scenarios? [Completeness, Gap, Spec §FR-004]
  → Resolution: FR-004 extended to require `deployed_ref` inherited from the static graph for the same env/repo; null if repo absent from static graph.

- [x] CHK002 - Is the time window for Datadog data queries specified? Trace searches, log queries, and RUM events are time-bounded by nature — is the lookback window (e.g., last N hours) defined, or is it left undefined for implementation to decide? [Completeness, Gap]
  → Resolution: Added FR-014 requiring a configurable lookback window (default 24 hours) via `TENDRIL_DD_LOOKBACK_HOURS` or `[telemetry.datadog] lookback_hours`.

- [x] CHK003 - Are the data volume limits for Datadog API results specified? APM service maps may return hundreds of service pairs; log queries may page through thousands of lines — are maximum result counts, pagination handling, or truncation policies required anywhere? [Completeness, Gap]
  → Resolution: Added FR-015 requiring pagination handling up to a configurable max (default 1 000/method/env) with `truncated: true` flag in DivergenceReport metadata.

- [x] CHK004 - Are requirements for log line and span structure specified? US3 references "structured log lines containing outbound HTTP call records" and "aggregate caller→callee pairs" from traces — are the required log fields (service tag, peer tag, span kind) defined, or is parsing logic left entirely to implementation? [Completeness, Clarity, Gap]
  → Resolution: Added FR-016 specifying required JSON log fields (`service`, `peer.service`/`http.url`/`out.host`) and span filter criteria (`span.kind == 'client'`); missing-field lines silently skipped.

- [x] CHK005 - Is the `static_only` output contract fully specified? The Assumptions section calls it "informational only" but no FR or SC defines what "informational" means concretely: logged at what level, surfaced where in the report, available via which query tools? [Completeness, Gap, Spec §Assumptions]
  → Resolution: Added FR-017 requiring static_only edges surfaced in DivergenceReport, logged at INFO with prescribed message format, and explicitly protected from modification.

- [x] CHK006 - Is the format of a degradation notice in `DivergenceReport.metadata` specified? FR-008 says "marked degraded in report metadata" but doesn't define the structure (error code? message? affected capability field?), making the contract untestable without implementation choices. [Completeness, Clarity, Gap, Spec §FR-008]
  → Resolution: DivergenceReport entity extended with explicit degradation notice schema `{capability, reason, message}`; FR-008 updated to reference this schema.

- [x] CHK007 - Is the triggering mechanism for the automatic end-of-build telemetry pass specified? FR-012 says the pass must be "independently executable" but doesn't define how it integrates into the full `graph build` flow — is it implicit (always appended) or opt-in (flag required)? [Completeness, Gap, Spec §FR-012]
  → Resolution: Added FR-018 specifying automatic execution at end of `tendril graph build` when credentials complete, plus standalone `tendril telemetry reconcile --env <env>` command.

- [x] CHK008 - Are retry semantics for Datadog API calls specified? M9 explicitly states "no retry on HTTP 429 in v0" — does M10 inherit the same stance, and if so, is it documented? The absence of a retry policy is a policy, not an omission. [Completeness, Gap]
  → Resolution: Added FR-019 explicitly stating no retry in v0 as policy for all failure types (network error, 4xx/5xx, timeout, unexpected schema).

- [x] CHK009 - Is a requirement present for how `runtime_only` edges are handled on a subsequent static graph rebuild? If the same edge later appears in the static graph, should its provenance be upgraded from `observed` to the static provenance, or should both records coexist? [Completeness, Gap]
  → Resolution: Added FR-020 requiring idempotent upsert keyed on `(from_id, to_id, env, provenance=observed)`; evidence merged, deployed_ref updated, no duplicate created.

---

## Requirement Clarity

- [x] CHK010 - Is "silently skipped" in FR-007 consistent with "single INFO log" in US2 Scenario 3? FR-007 says the telemetry step "MUST be silently skipped" when credentials are absent, but the corresponding acceptance scenario requires a log message — "silently" and "logged" are contradictory. [Clarity, Conflict, Spec §FR-007 vs §US2]
  → Resolution: FR-007 reworded to "MUST be skipped and a single INFO-level log MUST be emitted: 'Datadog telemetry unconfigured (missing: {fields}); skipping telemetry pass.'"; US2 Scenario 3 updated to match.

- [x] CHK011 - Is "sensitive values" in FR-013 defined for the telemetry context? FR-013 mandates redaction of "API keys, tokens" in Datadog log lines and trace metadata, but "sensitive" in span context can include HTTP Authorization headers, query parameters, and user identifiers — is the scope of what must be redacted bounded? [Clarity, Ambiguity, Spec §FR-013]
  → Resolution: FR-013 expanded to enumerate sensitive value types: HTTP Authorization headers, Bearer tokens, API keys in query params (`api_key=`, `token=`), password fields, and PII field names from M9 ResidencyGate; service names and span op names explicitly not sensitive.

- [x] CHK012 - Is the content format of the `evidence` field in `ObservedEdge` specified? The entity definition lists `evidence list` but gives no format — unlike static-pass evidence (file:line, store:scope:key), what does an APM evidence locator look like (API endpoint? timestamp? span ID?)? [Clarity, Gap, Spec §Key Entities]
  → Resolution: Added FR-021 defining evidence locator format `datadog:{capability}:{env}:{api_path}@{iso_timestamp}`; ObservedEdge entity updated to reference FR-021.

- [x] CHK013 - Is "unexpected schema" in FR-008 precisely defined? The edge case references "Datadog API returns unexpected schema" — is this limited to missing required fields, or does it include extra unrecognised fields, wrong types, or empty payloads? An implementer needs a clear boundary. [Clarity, Ambiguity, Spec §FR-008]
  → Resolution: FR-008 clarified: unexpected schema = missing required fields or wrong types; unrecognised additional fields accepted without error (forward-compatible parsing).

- [x] CHK014 - Is the `deployed_ref` selection rule specified when a repo has multiple deployments in the same environment? US4 says `deployed_ref` is "inherited from the static graph for the same environment" — but if the static graph records multiple DEPLOYED_AS entries for that env, which SHA is used? [Clarity, Ambiguity, Spec §US4]
  → Resolution: Added to Assumptions: most recent DEPLOYED_AS record by timestamp is used; if no timestamp, first record encountered with WARNING logged.

- [x] CHK015 - Is "independently callable" (FR-001) defined with respect to `probe()`? The requirement that each data method is "independently callable" raises the question of whether `probe()` must succeed before any data method can be called, or whether callers may bypass probing. [Clarity, Ambiguity, Spec §FR-001]
  → Resolution: FR-001 extended: callers MUST invoke `probe(env)` before calling any data method for that env; data methods called without prior probe raise `ProbeRequiredError`.

- [x] CHK016 - Is the `unknowns` entry format in `DivergenceReport` specified? FR-009 requires unresolvable service names appear in `unknowns` with `reason="no-index-match"` but the full entry schema (service name, env, signal source, timestamp) is not defined. [Clarity, Gap, Spec §FR-009]
  → Resolution: DivergenceReport entity extended with `unknowns` schema: `{service, env, capability, reason, candidates}` where `candidates` populated only for `ambiguous-match`.

---

## Requirement Consistency

- [x] CHK017 - Is FR-004 (`confidence=high` for all runtime-only edges) justified across all signal sources? APM service maps have high confidence (they aggregate all traffic); log-parsing edges may have false positives from malformed log lines. Should confidence be uniformly `high` regardless of signal quality? [Consistency, Ambiguity, Spec §FR-004]
  → Resolution: FR-004 updated: APM edges always `confidence=high`; trace/log edges `confidence=high` only when pair appears in more than one span/log line; single-occurrence = `confidence=medium`.

- [x] CHK018 - Do the `Capabilities` entity and the acceptance criteria have symmetric coverage? The `Capabilities` entity defines four fields (`apm`, `logs`, `rum`, `traces`) but SC-003 only tests APM absence independently. No SC tests `traces=false` or `rum=false` independently — is that coverage intentional? [Consistency, Spec §Key Entities vs §SC-003]
  → Resolution: Added SC-009 (traces=false scenario) and SC-010 (rum=false scenario) to provide symmetric coverage for all four Capabilities fields.

- [x] CHK019 - Does the spec consistently distinguish `ObservedEdge` (pre-identity-resolution) from a `DEPENDS_ON` graph edge (post-resolution)? Some FRs and scenarios use these terms interchangeably, which may obscure the two-step process: collect observed edges → resolve service names → write graph edges. [Consistency, Clarity, Spec §FR-002, FR-004, FR-009]
  → Resolution: Added "Two-stage resolution note" paragraph in Key Entities section explicitly describing the pre/post-resolution distinction and where DivergenceReport sets operate.

- [x] CHK020 - Is the relationship between `DivergenceReport.confirmed` and the static graph's existing edges specified consistently? US1 Scenario 2 says `confirmed` edges retain their "original provenance and confidence unchanged" — but FR-002 defines `confirmed` as edges present in both sets without specifying what happens to the graph record for those edges. [Consistency, Spec §FR-002 vs §US1]
  → Resolution: FR-002 extended to explicitly state confirmed set is informational only; confirmed edges are not re-written, re-tagged, or modified in any way.

- [x] CHK021 - Is FR-005 (static edges must not be modified) consistent with the secret redaction assumption? The Assumptions section states M9's `SecretRedactor` may be imported in `cross_validate.py` — if redaction is applied to evidence during the telemetry pass, could it inadvertently alter evidence on static edges that are part of `confirmed`? [Consistency, Conflict, Spec §FR-005 vs §Assumptions]
  → Resolution: FR-005 extended to state redaction operates only on newly constructed ObservedEdge.evidence and DivergenceReport output; MUST NOT re-process evidence on existing static-graph edges.

---

## Acceptance Criteria Quality

- [x] CHK022 - Are the SC-001 counts (`confirmed==2`, `runtime_only==1`) measurable without knowing Datadog's deduplication logic? The count depends on how the fixture is constructed — is the fixture format specified sufficiently for any implementer to reproduce these exact counts? [Measurability, Spec §SC-001]
  → Resolution: SC-001 updated to specify the exact fixture file path (`tests/fixtures/conformance/telemetry/datadog/service_dependencies_prod.json`) and fixture structure (2 matching pairs + 1 non-matching pair).

- [x] CHK023 - Does SC-006 specify the tie-breaking or merge order for duplicate-edge evidence? SC-006 requires one `DEPENDS_ON` edge with evidence from both APM and log sources but doesn't specify the evidence ordering (deterministic sort? insertion order?) — can this criterion be objectively verified? [Measurability, Spec §SC-006]
  → Resolution: FR-010 extended and SC-006 updated to require evidence list sorted deterministically by `(capability, iso_timestamp, api_path)`.

- [x] CHK024 - Is there a success criterion for the timeout/unreachable endpoint scenario? The spec defines graceful degradation behaviour in FR-008 and the edge cases section but no SC validates the degradation path end-to-end (compare: M9's SC-005 for unreachable endpoint). [Coverage, Gap]
  → Resolution: Added SC-011: unreachable endpoint scenario verified by fixture; all capabilities degraded with reason='error'; DivergenceReport has empty sets; exit code 0.

- [x] CHK025 - Can SC-004's `deployed_ref` assertion be verified for the "or null" case? SC-004 states `deployed_ref` is present referencing the Datadog source — but the "or null" branch (repo not in static graph) is mentioned in US4 without a corresponding SC. Is the null case intentionally out of SC scope? [Measurability, Coverage, Spec §SC-004]
  → Resolution: SC-004 extended with explicit null-deployed_ref sub-case; US4 Scenario 1 also extended with the null path verification.

---

## Scenario Coverage — Primary & Alternate Flows

- [x] CHK026 - Are requirements defined for running reconcile when the static graph was built for a different environment than the one queried? E.g., static graph has `prod` edges only but `reconcile(env="staging")` is called — is this a defined failure, an empty report, or an error? [Coverage, Gap]
  → Resolution: Added FR-027 (and FR-024) specifying that reconcile treats a missing-env static graph as empty set; confirmed and static_only are empty; runtime_only contains all resolved runtime edges; not an error.

- [x] CHK027 - Are requirements defined for the independent execution path (FR-012)? What CLI command, flags, and output format apply when the telemetry pass is run standalone (not as part of `graph build`)? The FR mandates the capability but doesn't specify the interface. [Coverage, Gap, Spec §FR-012]
  → Resolution: FR-018 extended to specify `tendril telemetry reconcile --env <env>`, JSON stdout output matching DivergenceReport schema, --env required (exit 1 + usage if omitted).

- [x] CHK028 - Are requirements defined for running reconcile twice against the same environment? The second run may encounter runtime-only edges already written by the first run — should they be deduplicated, overwritten with refreshed evidence, or left as-is? [Coverage, Alternate Flow, Gap]
  → Resolution: Resolved via FR-020 (idempotency): second run upserts on `(from_id, to_id, env, provenance=observed)`, merging evidence and updating deployed_ref without duplicating.

- [x] CHK029 - Are multi-signal fixture requirements defined for all four sources? US3's Independent Test references "APM service dependencies, span search results, and structured log lines" — RUM is described in the acceptance scenario but is it included in the conformance fixture? [Coverage, Spec §US3]
  → Resolution: US3 Independent Test updated to explicitly require all four fixture files (APM, traces, logs, RUM) each contributing at least one distinct edge.

---

## Scenario Coverage — Exception & Recovery Flows

- [x] CHK030 - Are requirements defined for partial probe failure? FR-003 says capabilities not confirmed active are skipped — but if `probe()` itself raises an exception (not just returns `false`), should the entire reconcile abort, or should that capability be treated as inactive? [Coverage, Exception Flow, Gap, Spec §FR-003]
  → Resolution: FR-003 extended: probe exception → capability treated as inactive; WARNING emitted with format 'probe failed for capability {cap} in env {env}: {error}'; reconcile continues.

- [x] CHK031 - Are requirements defined for a mid-stream rate limit (rate limit hits after APM succeeds but before traces complete)? The edge case only mentions "affected capability is marked degraded" but doesn't specify whether already-fetched APM results are used or discarded. [Coverage, Exception Flow, Spec §Edge Cases]
  → Resolution: FR-008 extended and Edge Cases section updated: data from capabilities that completed before the rate limit is retained and contributes to the DivergenceReport.

- [x] CHK032 - Are requirements defined for graph store write failure when persisting a runtime-only edge? If `KuzuStore.upsert_edge()` fails for one edge, should the reconcile abort, skip that edge and continue, or roll back all writes for that run? [Coverage, Recovery Flow, Gap]
  → Resolution: Added FR-022: write failure logs ERROR with triple, skips that edge, continues remaining writes, exit code 0; failed edge appears in DivergenceReport.metadata with reason='store-write-error'.

- [x] CHK033 - Are requirements defined for what happens when `static graph is not yet built` for the queried env? The edge case states `confirmed=[], static_only=[], runtime_only=[all APM edges]` but FR-004 requires writing runtime-only edges to the graph — should M10 create the DEPENDS_ON nodes and edges even when the from/to repos don't yet exist in the graph? [Coverage, Exception Flow, Spec §Edge Cases vs §FR-004]
  → Resolution: Resolved via FR-027 (empty static set treated as valid, not error) and FR-024 (empty entire store logs WARNING); CHK026 resolution covers the same scenario.

---

## 🔴 Risk Gate: Secret & Data Safety *(mandatory gating)*

- [x] CHK034 - Is "sensitive" defined specifically for Datadog span and log contexts? Spans commonly capture HTTP request headers including `Authorization`, `Cookie`, and `X-API-Key` — are these field names enumerated in the redaction requirement, or is the definition left to the implementer? A vague definition here is a data-safety gap. [**GATE**, Clarity, Spec §FR-013]
  → Resolution: FR-013 expanded with explicit enumeration of sensitive value types including HTTP Authorization headers, Bearer tokens, API keys in query params, password fields, and PII field names from M9 ResidencyGate.

- [x] CHK035 - Does FR-013 cover PII that may appear in Datadog service names, log messages, or trace tags? Service names are typically safe, but log lines (parsed for caller→callee) may contain email addresses, user IDs, or session tokens inline with URL paths — is PII redaction in scope for M10, or explicitly deferred? [**GATE**, Coverage, Gap, Spec §FR-013]
  → Resolution: FR-013 extended to require PII redaction in log line evidence; log lines where PII cannot be cleanly separated from caller/callee fields MUST be skipped entirely.

- [x] CHK036 - Is the post-redaction evidence format specified? When a secret value is found in a Datadog evidence locator, should the locator be omitted from evidence entirely, replaced with `[REDACTED]`, or stored as a redacted summary record? An unspecified post-redaction format creates divergent implementations. [**GATE**, Clarity, Gap, Spec §FR-013]
  → Resolution: FR-013 extended: sensitive portion replaced with `[REDACTED]`; if entire locator value is sensitive, the locator is omitted entirely from evidence list.

- [x] CHK037 - Is the M9 `ResidencyGate` applicable to telemetry evidence, and is that stated? M9's `ResidencyGate` blocks LLM calls when evidence contains PII patterns — does M10 require the same PII screening before storing telemetry evidence in the graph, or only before LLM calls (which M10 doesn't make)? [**GATE**, Coverage, Spec §Assumptions]
  → Resolution: FR-013 extended: M9 PII patterns apply to telemetry evidence; PII found after secret redaction causes omission of that evidence item only (not blocking entire edge), since M10 makes no LLM calls.

- [x] CHK038 - Is there a requirement that the `DivergenceReport` itself is not persisted with un-redacted values? The report contains evidence and metadata that may include Datadog API responses — if the report is written to disk or returned via MCP, should it be subject to the same secret redaction as graph edges? [**GATE**, Gap]
  → Resolution: FR-013 extended to require DivergenceReport pass through secret redaction before serialization (stdout, MCP response, disk write); metadata fields and evidence locators in all three sets must be screened.

- [x] CHK039 - Does the spec specify that Datadog API credentials (`DD_API_KEY`, `DD_APP_KEY`) are never stored in evidence, logs, or graph edges? This is a corollary of FR-011 (read-only) and FR-013 (redact), but the specific case of the credentials used for the Datadog calls leaking into output is not mentioned. [**GATE**, Gap, Spec §FR-011, §FR-013]
  → Resolution: FR-013 extended with explicit statement that DD_API_KEY and DD_APP_KEY MUST NEVER appear in evidence, logs, or graph edges; this is noted as a corollary of FR-011.

---

## 🔴 Risk Gate: Capability Degradation Semantics *(mandatory gating)*

- [x] CHK040 - Is the probe mechanism specified precisely enough to be implemented without Datadog API knowledge? FR-003 says "probe available capabilities" but doesn't define what API call constitutes the probe — is it a dedicated `/api/v1/validate` call, an attempt at the actual data endpoint, or inspection of account features? [**GATE**, Clarity, Gap, Spec §FR-003]
  → Resolution: FR-003 extended with exact probe API endpoints and semantics for each capability (APM: GET /api/v1/services; Logs: POST /api/v2/logs/events/search; Traces: GET /api/v1/service_dependencies; RUM: POST /api/v2/rum/events/search); 200 = active, 404/empty = inactive.

- [x] CHK041 - Is the probe failure behavior (exception, not just `false`) defined? The spec handles probe returning `false` (skip capability) but not probe raising an exception. These are different failure modes with different operator implications: one means "not enabled," the other means "can't tell." [**GATE**, Coverage, Exception Flow, Spec §FR-003]
  → Resolution: Resolved via CHK030 — FR-003 extended to treat probe exception as inactive with WARNING log; distinct from not-enabled (DEBUG) and missing credentials (INFO).

- [x] CHK042 - Is the scope of "silently skipped" for missing capabilities consistent with observability needs? "Skip silently" (FR-003) means no log output for each skipped capability — is that the right level for operators who need to know why their trace-level edges are absent from a reconcile report? [**GATE**, Clarity, Consistency, Spec §FR-003]
  → Resolution: FR-003 updated to distinguish log levels: inactive capability = DEBUG; probe exception = WARNING; missing credentials = INFO (FR-007). "Silently" removed; observability levels explicitly specified.

- [x] CHK043 - Is the rate-limit cascade boundary defined? If APM is rate-limited, does that affect the rate-limit budget for traces and logs in the same run (shared Datadog org budget), or are they independent? The spec treats each capability independently but Datadog rate limits apply at the API key level. [**GATE**, Coverage, Gap, Spec §FR-008, §Edge Cases]
  → Resolution: FR-008 extended to acknowledge rate limits apply at API key level; each capability independently marked degraded; no attempt to honour X-RateLimit-Reset header in v0.

- [x] CHK044 - Is `probe()` required to be called per-environment, or once per provider instance? The `Capabilities` entity is described as "per-environment probe result" but no FR explicitly mandates re-probing on each `reconcile(env)` call vs. caching the probe result across environments. [**GATE**, Clarity, Spec §Key Entities vs §FR-003]
  → Resolution: FR-003 extended to explicitly require probe called once per (env) per reconcile() call; probe results MUST NOT be cached across reconcile() calls.

---

## 🔴 Risk Gate: Identity Resolution *(mandatory gating)*

- [x] CHK045 - Is the Datadog service name → graph `repo_id` mapping mechanism specified? The Assumption states "service: tag maps to `repo_id` via the reverse index" but the reverse index was built from provider identities (URLs, package names, hostnames) — not Datadog service names. The mapping path is assumed but not designed. [**GATE**, Gap, Ambiguity, Spec §Assumptions]
  → Resolution: Added FR-023 defining two-step lookup (exact match on kind=service-tag, then URL hostname suffix match); introduced kind=service-tag as new provider identity kind in M10.

- [x] CHK046 - Is the ordering requirement for static graph build vs. telemetry pass formally stated? The Assumptions note "M10 depends on M4 (static graph must exist)" but this ordering constraint is not in any FR — is a reconcile call before any `graph build` an error, a no-op, or undefined behavior? [**GATE**, Completeness, Spec §Assumptions]
  → Resolution: Added FR-024 specifying reconcile accepts any env regardless; empty static graph logs WARNING 'No static graph found in store — all runtime edges will appear as runtime_only'; not an error.

- [x] CHK047 - Is partial/fuzzy matching of service names explicitly out of scope? `payment-svc` vs `payment-service` vs `acme/payment-service` are all plausible variants — if the spec is silent on fuzzy matching, implementations may silently differ. Explicitly ruling it out is as important as specifying it. [**GATE**, Clarity, Scope, Gap]
  → Resolution: FR-023 extended with explicit statement: no fuzzy, partial, edit-distance, or case-insensitive matching in v0; exact case-sensitive match only.

- [x] CHK048 - Is the full schema of an `unknowns` entry in `DivergenceReport` specified? FR-009 says entries appear with `reason="no-index-match"` but the full entry format (does it carry the Datadog service name, the env, the signal source that produced it, a timestamp?) is not defined — making SC-005's assertion about `service="payment-svc"` only partially verifiable. [**GATE**, Completeness, Spec §FR-009, §SC-005]
  → Resolution: Resolved via CHK016 — DivergenceReport entity extended with complete unknowns entry schema `{service, env, capability, reason, candidates}`.

- [x] CHK049 - Are requirements defined for service names that partially resolve (match multiple reverse-index entries)? The static pass emits `ambiguous=True` edges for ambiguous matches — should the telemetry pass do the same, or treat all multi-match service names as `no-index-match`? [**GATE**, Coverage, Gap]
  → Resolution: FR-023 extended: ambiguous match (multiple entries) recorded in unknowns with `reason='ambiguous-match'` and `candidates=[list of matched repo_ids]`; NOT written as graph edges.

---

## Non-Functional Requirements

- [x] CHK050 - Is a timeout requirement defined for Datadog API calls? M9 defines `timeout_seconds=60` as a configurable default for LLM calls — M10 makes comparable long-polling calls to Datadog APIs but no timeout or configurability requirement is present. [Coverage, Gap]
  → Resolution: Added FR-025 requiring configurable per-call timeout (default 60s) via `TENDRIL_DD_TIMEOUT_SECONDS` or `[telemetry.datadog] timeout_seconds`; timeout treated as error per FR-008.

- [x] CHK051 - Are performance requirements defined for large service graphs? If the Datadog APM service map returns 500+ service pairs, are there requirements for maximum reconcile wall-clock time, memory usage, or result truncation? [Coverage, Gap]
  → Resolution: Added FR-026: if total resolved ObservedEdges exceeds 10 000, WARNING logged; no hard cap in v0; serves as operator signal for sequential reconciliation limits.

- [x] CHK052 - Are observability requirements specified for M10's own execution? The spec defines what M10 reports about the estate topology but not what M10 itself emits (how long reconcile took, how many API calls were made, how many edges were written) — is structured timing/count output a requirement? [Coverage, Gap]
  → Resolution: Added FR-027 requiring INFO-level reconcile summary log at end of each reconcile() call with confirmed/static_only/runtime_only/unknowns counts, degraded capabilities list, and elapsed time.

---

## Plugin Contract Alignment

- [x] CHK053 - Does the spec explicitly state that `DatadogTelemetryProvider` must implement all methods in the `TelemetryProvider` ABC from M0? The Assumptions reference the ABC but no FR states that the full interface must be satisfied — this matters because partial implementations could silently violate the contract. [Completeness, Spec §Assumptions]
  → Resolution: FR-001 extended to explicitly require DatadogTelemetryProvider implement every method in the TelemetryProvider ABC; unsupported methods raise NotImplementedError with explanation; plugin manifest required.

- [x] CHK054 - Is the `probe()` method signature in `DatadogTelemetryProvider` required to match the ABC definition in `tendril/plugins/base.py`? If the ABC defines `probe(env: str) -> Capabilities` but the spec describes different parameter shapes, the implementation cannot satisfy the contract. [Consistency, Spec §US2, §Key Entities]
  → Resolution: FR-001 extended to state probe(env: str) -> Capabilities signature MUST match the TelemetryProvider ABC exactly.

- [x] CHK055 - Is the conformance suite for `TelemetryProvider` mentioned as a gating requirement? CLAUDE.md mandates that all providers must pass their conformance suite — the spec should reference this gate explicitly, as M1–M8 do in their acceptance sections. [Completeness, Gap, Spec §FR-001]
  → Resolution: Added "Acceptance Gate" section after Requirements explicitly requiring DatadogTelemetryProvider pass the TelemetryProvider conformance suite in tests/conformance/telemetry/ before M10 is considered complete.

---

## Dependencies & Assumptions

- [x] CHK056 - Is the assumption that `CrossValidator` is independent of M5–M9 validated? The spec states M10 "is independent of M5–M9" but US4 (runtime edges visible to query tools) requires `QueryEngine.explain_edge()` — which lives in M5. Is M10 actually independent of M5, or does US4 add an undeclared dependency? [Consistency, Conflict, Spec §US4 vs §Assumptions]
  → Resolution: Assumptions updated to clarify M10 is NOT fully independent of M5: CrossValidator/DatadogTelemetryProvider have no M5 dependency; US4 query integration requires M5; explicit dependency documented.

- [x] CHK057 - Is the coupling of `cross_validate.py` to `tendril.llm.redactor` (from M9) acceptable given the stated independence? The Assumptions permit importing M9's `SecretRedactor` but note "M10 must not require M9 to be enabled" — is this soft coupling documented as a dependency risk if M9 is refactored? [Consistency, Spec §Assumptions]
  → Resolution: Assumptions updated to document the coupling explicitly: tendril.llm always present (not optional), coupling must be documented in code, extraction to shared utility tracked as known technical debt if tendril.llm becomes optional.

- [x] CHK058 - Is the assumption "sequential per-environment reconciliation" sufficient for estates with many environments? Large estates may run prod, staging, and qa simultaneously — if sequential processing takes too long, is there a documented plan for v1 parallelism, or is this left entirely open? [Coverage, Spec §Assumptions]
  → Resolution: Assumptions updated to explicitly state v0 is sequential; linear scaling is a known limitation; v1 parallelism path planned but out of scope for M10; documented as explicit known limitation.

---

## Notes

- Items marked **🔴 GATE** (CHK034–CHK049) are mandatory: all must be resolved before
  proceeding to `/speckit.plan`. Any GATE item that remains open requires a spec update.
- All 58 items are now resolved and checked. All GATE items have corresponding spec
  updates (new FRs, extended FRs, entity schema updates, or Assumptions clarifications).
- The spec now covers FR-001 through FR-027 and SC-001 through SC-011.
- CHK010 (FR-007 "silently" vs US2 "INFO log") conflict is resolved — consistent INFO log
  wording throughout.
- CHK045 (service name → repo_id mapping) now has a designed mechanism in FR-023 with
  the new `kind=service-tag` provider identity type.
- CHK056 (M10 independence from M5) is resolved by explicitly documenting the M5
  dependency for US4 while noting CrossValidator/DatadogTelemetryProvider themselves
  remain M5-independent.
