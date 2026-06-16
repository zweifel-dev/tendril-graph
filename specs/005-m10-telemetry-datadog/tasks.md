# Tasks: M10 — Telemetry Cross-Validation (Datadog)

**Input**: Design documents from `/specs/005-m10-telemetry-datadog/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — the spec mandates conformance suite, integration tests, and unit tests.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, new module scaffolding, dependency registration

- [x] T001 Add `httpx` dependency to `pyproject.toml` under `[dev]` extras
- [x] T002 [P] Create `tendril/connectors/telemetry/datadog_provider.py` with module docstring and imports
- [x] T003 [P] Create `tendril/core/cross_validate.py` with module docstring and imports
- [x] T004 [P] Create fixture directory structure at `tests/fixtures/conformance/telemetry/datadog/` with placeholder README
- [x] T005 [P] Create `tendril-plugin.toml` manifest for the Datadog provider at `tendril/connectors/telemetry/tendril-plugin.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: IR model extensions, config loading, identity resolution changes, and error types that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Add `SERVICE_TAG = "service-tag"` to `IdentityClass` enum in `tendril/models/ir.py`
- [x] T007 Add `SERVICE_TAG` normalization case (strip whitespace, preserve case) to `ReverseIndex._normalize()` in `tendril/core/index.py`
- [x] T008 Add `SERVICE_TAG` confidence assignment (`HIGH`) to `ReverseIndex._class_confidence()` in `tendril/core/index.py`
- [x] T009 [P] Add new dataclasses to `tendril/models/ir.py`: `ResolvedObservedEdge`, `ConfirmedEdge`, `StaticOnlyEdge`, `RuntimeOnlyEdge`, `UnknownService`, `DegradationNotice`, `DivergenceReport` (with `to_dict()` method)
- [x] T010 [P] Add `DatadogConfig` dataclass with `is_complete()` method and `load_datadog_config()` factory to `tendril/config.py`
- [x] T011 [P] Add `ProbeRequiredError` exception class to `tendril/plugins/base.py` (or `tendril/models/ir.py`)
- [x] T012 [P] Create all Datadog JSON fixture files in `tests/fixtures/conformance/telemetry/datadog/`: `capabilities_prod.json`, `capabilities_logs_only.json`, `capabilities_none.json`, `service_dependencies_prod.json`, `edges_from_traces_prod.json`, `edges_from_logs_prod.json`, `edges_from_rum_prod.json`, `service_dependencies_staging.json`, `edges_from_logs_prod_with_pii.json`

**Checkpoint**: Foundation ready — all data models, config, identity type, and fixtures in place

---

## Phase 3: User Story 1 — Surface Undeclared Runtime Dependencies (Priority: P1) MVP

**Goal**: Implement `DatadogTelemetryProvider` (APM service-map data method + fixture mode) and `CrossValidator` three-way reconciliation that identifies `runtime_only` edges and writes them to the graph store with `provenance=observed`.

**Independent Test**: Given a Datadog fixture with 3 APM service edges (2 matching static graph, 1 unknown), reconcile produces `confirmed=2`, `runtime_only=1`; the runtime-only edge is in the graph store with `provenance=observed`, `confidence=high`, non-empty evidence.

### Tests for User Story 1

- [x] T013 [P] [US1] Write conformance test class `TestDatadogConformance` in `tests/conformance/telemetry/test_datadog_conformance.py` extending `ConformanceTelemetryProvider`
- [x] T014 [P] [US1] Write unit tests for `DatadogTelemetryProvider.probe()` and `service_dependencies()` in `tests/unit/test_datadog_provider.py`
- [x] T015 [P] [US1] Write unit tests for `CrossValidator.reconcile()` core set operations in `tests/unit/test_cross_validator.py` — SC-001 scenario (confirmed=2, runtime_only=1)
- [x] T016 [P] [US1] Write integration test `test_reconcile_writes_runtime_only_edge` in `tests/integration/test_telemetry_reconcile.py` — verifies edge in graph store with provenance/confidence/evidence

### Implementation for User Story 1

- [x] T017 [US1] Implement `DatadogTelemetryProvider.__init__()` with `fixture_dir` parameter, probe state tracking, and `id()` method in `tendril/connectors/telemetry/datadog_provider.py`
- [x] T018 [US1] Implement `DatadogTelemetryProvider.probe(env)` — fixture mode loads `capabilities_{env}.json`; returns `Capabilities` dict; tracks probed envs for `ProbeRequiredError` enforcement
- [x] T019 [US1] Implement `DatadogTelemetryProvider.service_dependencies(env)` — fixture mode loads `service_dependencies_{env}.json`; returns `list[ObservedEdge]` with `capability="apm"`; raises `ProbeRequiredError` if not probed
- [x] T020 [US1] Implement `CrossValidator.__init__()` and `resolve_service_name()` helper (FR-023 two-step reverse-index lookup: SERVICE_TAG exact match, then hostname-suffix match; ambiguous → `UnknownService`) in `tendril/core/cross_validate.py`
- [x] T021 [US1] Implement `CrossValidator.reconcile(env)` core flow: probe → fetch active capabilities → resolve service names → deduplicate edges (FR-010) → fetch static edges → compute confirmed/static_only/runtime_only sets → write runtime_only to store (FR-004, FR-020 upsert) → return `DivergenceReport`
- [x] T022 [US1] Add INFO-level reconcile summary log (FR-027) and WARNING for >10,000 edges (FR-026) in `CrossValidator.reconcile()`

**Checkpoint**: US1 complete — `DatadogTelemetryProvider` (APM only) + `CrossValidator` reconcile works end-to-end in fixture mode. SC-001 passes.

---

## Phase 4: User Story 2 — Capability-Aware Degradation (Priority: P1)

**Goal**: `probe()` handles missing/failed capabilities gracefully; missing credentials skip telemetry entirely; degraded capabilities are recorded in DivergenceReport metadata without failing the build.

**Independent Test**: Given a fixture with only `logs` capability active, reconcile produces a partial report from log signal only; `capabilities_probed["apm"]==False`; exit code 0.

### Tests for User Story 2

- [x] T023 [P] [US2] Write unit test `test_probe_partial_capabilities` in `tests/unit/test_datadog_provider.py` — uses `capabilities_logs_only.json`
- [x] T024 [P] [US2] Write unit test `test_probe_all_inactive` in `tests/unit/test_datadog_provider.py` — uses `capabilities_none.json`
- [x] T025 [P] [US2] Write unit test `test_missing_credentials_skips_telemetry` in `tests/unit/test_cross_validator.py` — SC-002 scenario
- [x] T026 [P] [US2] Write unit test `test_degraded_capability_in_metadata` in `tests/unit/test_cross_validator.py` — verifies `DegradationNotice` in report
- [x] T027 [P] [US2] Write integration test `test_reconcile_logs_only_capability` in `tests/integration/test_telemetry_reconcile.py` — SC-003 scenario

### Implementation for User Story 2

- [x] T028 [US2] Add probe-failure handling to `CrossValidator.reconcile()`: catch exceptions from `probe()`, treat all capabilities as inactive, emit WARNING log (FR-003)
- [x] T029 [US2] Add per-capability error handling in `CrossValidator.reconcile()` data-fetch loop: catch exceptions, record `DegradationNotice` with appropriate reason (`error`, `rate-limited`, `schema-error`), continue with remaining capabilities (FR-008)
- [x] T030 [US2] Add credential-absence check: when `DatadogConfig.is_complete() == False`, emit INFO log per FR-007 and skip telemetry pass entirely

**Checkpoint**: US2 complete — graceful degradation for all probe/fetch failure modes. SC-002, SC-003 pass.

---

## Phase 5: User Story 3 — Multi-Signal Edge Discovery (Priority: P2)

**Goal**: Implement `edges_from_traces()`, `edges_from_logs()`, and `edges_from_rum()` data methods. Each signal source independently contributes observed edges with correct capability labels and evidence.

**Independent Test**: Given fixtures for all four signal sources each contributing a distinct edge, reconcile produces observed edges with evidence referencing the correct signal source.

### Tests for User Story 3

- [x] T031 [P] [US3] Write unit test `test_edges_from_traces` in `tests/unit/test_datadog_provider.py` — verifies `capability="traces"` on returned edges
- [x] T032 [P] [US3] Write unit test `test_edges_from_logs` in `tests/unit/test_datadog_provider.py` — verifies `capability="logs"` and structured log field parsing (FR-016)
- [x] T033 [P] [US3] Write unit test `test_edges_from_rum` in `tests/unit/test_datadog_provider.py` — verifies `capability="rum"` on returned edges
- [x] T034 [P] [US3] Write unit test `test_duplicate_edge_merge` in `tests/unit/test_cross_validator.py` — SC-006: APM+logs same pair → single edge, evidence sorted (FR-010)
- [x] T035 [P] [US3] Write integration test `test_reconcile_all_four_signals` in `tests/integration/test_telemetry_reconcile.py` — all four capabilities active, distinct edges from each

### Implementation for User Story 3

- [x] T036 [US3] Implement `DatadogTelemetryProvider.edges_from_traces(env)` — fixture mode loads `edges_from_traces_{env}.json`; parses spans with `span.kind=="client"` and `peer.service`/`out.host` (FR-016); returns `list[ObservedEdge]`
- [x] T037 [US3] Implement `DatadogTelemetryProvider.edges_from_logs(env)` — fixture mode loads `edges_from_logs_{env}.json`; parses structured JSON logs with `service` + `peer.service`/`http.url`/`out.host` (FR-016); returns `list[ObservedEdge]`
- [x] T038 [US3] Implement `DatadogTelemetryProvider.edges_from_rum(env)` — fixture mode loads `edges_from_rum_{env}.json`; extracts browser-to-API pairs; returns `list[ObservedEdge]`

**Checkpoint**: US3 complete — all four signal sources produce edges. SC-006, SC-009, SC-010 pass.

---

## Phase 6: User Story 4 — Runtime Edges Visible to Query and Agent Tools (Priority: P2)

**Goal**: After reconcile writes runtime-only edges, `explain_edge` and `find_relevant_repos` return them with `provenance=observed` visible to agents.

**Independent Test**: After reconcile writes a runtime-only edge, `QueryEngine.explain_edge(from_id, to_id, env)` returns it with `provenance=observed`, `confidence=high`, and Datadog evidence.

### Tests for User Story 4

- [x] T039 [P] [US4] Write integration test `test_explain_edge_shows_observed_provenance` in `tests/integration/test_telemetry_reconcile.py` — SC-004 scenario
- [x] T040 [P] [US4] Write integration test `test_find_relevant_repos_includes_runtime_edge` in `tests/integration/test_telemetry_reconcile.py` — repo reachable only via observed edge appears in results

### Implementation for User Story 4

- [x] T041 [US4] Verify `KuzuStore` correctly persists and reads back `provenance=observed` edges — fix if needed in `tendril/store/kuzu_adapter.py` (or equivalent store implementation)
- [x] T042 [US4] Verify `QueryEngine.explain_edge()` returns `deployed_ref=null` without error when runtime-only edge's repo has no DEPLOYED_AS record — fix if needed in `tendril/query/engine.py`

**Checkpoint**: US4 complete — runtime-discovered edges are first-class citizens in query results. SC-004 passes.

---

## Phase 7: User Story 5 — Fixture-Mode for Testing Without Live Credentials (Priority: P2)

**Goal**: Full M10 test suite runs offline with no Datadog credentials. Fixture directory substitutes for live API.

**Independent Test**: `pytest tests/` passes on a clean checkout with no `DD_API_KEY`/`DD_APP_KEY` set.

### Tests for User Story 5

- [x] T043 [P] [US5] Write integration test `test_full_suite_no_credentials` in `tests/integration/test_telemetry_reconcile.py` — explicitly unsets DD env vars, runs full reconcile in fixture mode, asserts success

### Implementation for User Story 5

- [x] T044 [US5] Ensure all `DatadogTelemetryProvider` data methods short-circuit to fixture loading when `fixture_dir` is set — verify no HTTP imports or calls are triggered in fixture mode
- [x] T045 [US5] Add missing fixture file handling: when active capability has no corresponding fixture file, return empty list (not an error) per C-004

**Checkpoint**: US5 complete — full CI runs zero-credential. SC-007, SC-008 pass.

---

## Phase 8: CLI Integration & Secret Redaction (Cross-Cutting)

**Purpose**: Wire telemetry into CLI commands and ensure secret redaction across all outputs

- [x] T046 Add `tendril telemetry reconcile --env <env> [--db <path>] [--fixture-dir <path>]` subcommand to `tendril/cli/main.py` per FR-018 contract
- [x] T047 Add automatic telemetry reconcile at end of `tendril graph build` when `DatadogConfig.is_complete()` per FR-018 — skip with INFO log if incomplete
- [x] T048 Implement secret redaction in `CrossValidator`: apply `SecretRedactor` to evidence locators before persistence (FR-013) — redact Authorization headers, Bearer tokens, API keys in query params, PII patterns; omit fully-sensitive evidence items
- [x] T049 Implement PII handling for log-based evidence (FR-013): log lines where PII can't be separated from caller/callee fields are skipped entirely; affected items omitted from evidence list
- [x] T050 Add `DivergenceReport` JSON serialization pass through `SecretRedactor` before stdout/MCP output (FR-013)
- [x] T051 [P] Write unit test `test_evidence_redaction` in `tests/unit/test_cross_validator.py` — verifies sensitive values replaced with `[REDACTED]`, fully-sensitive items omitted
- [x] T052 [P] Write unit test `test_pii_log_lines_skipped` in `tests/unit/test_cross_validator.py` — uses `edges_from_logs_prod_with_pii.json` fixture
- [x] T053 [P] Write integration test `test_cli_telemetry_reconcile` in `tests/integration/test_telemetry_reconcile.py` — runs CLI command, verifies JSON output and graph store state
- [x] T054 [P] Write integration test `test_graph_build_auto_reconcile` in `tests/integration/test_telemetry_reconcile.py` — runs `graph build` with DD creds, verifies reconcile ran

**Checkpoint**: Full CLI integration and secret redaction complete.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, error robustness, SC verification, and existing test preservation

- [x] T055 [P] Implement configurable lookback window (`TENDRIL_DD_LOOKBACK_HOURS`, default 24h) in `DatadogTelemetryProvider` (FR-014)
- [x] T056 [P] Implement configurable per-call timeout (`TENDRIL_DD_TIMEOUT_SECONDS`, default 60s) in `DatadogTelemetryProvider` (FR-025)
- [x] T057 [P] Implement configurable max results (`TENDRIL_DD_MAX_RESULTS`, default 1000) with truncation metadata in `DatadogTelemetryProvider` (FR-015)
- [x] T058 [P] Implement idempotent upsert for runtime-only edges (FR-020) — verify re-running reconcile updates evidence without duplicating edges
- [x] T059 [P] Add store-write-error handling (FR-022): log ERROR for failed edge writes, record in metadata, continue with remaining edges
- [x] T060 [P] Add evidence locator format validation (FR-021): `datadog:{capability}:{env}:{api_path}@{iso_timestamp}`
- [x] T061 [P] Write unit test `test_unknown_service_recorded` in `tests/unit/test_cross_validator.py` — SC-005: unresolvable service → unknowns list
- [x] T062 [P] Write unit test `test_ambiguous_match_recorded` in `tests/unit/test_cross_validator.py` — service matching multiple index entries → unknowns with `ambiguous-match`
- [x] T063 [P] Write unit test `test_static_only_not_modified` in `tests/unit/test_cross_validator.py` — FR-005/FR-017: static edges unchanged after reconcile
- [x] T064 [P] Write unit test `test_empty_static_graph` in `tests/unit/test_cross_validator.py` — FR-024: no static edges → all runtime edges in `runtime_only`
- [x] T065 [P] Write integration test `test_all_capabilities_error` in `tests/integration/test_telemetry_reconcile.py` — SC-011: unreachable endpoint, all degraded, exit 0
- [x] T066 Run full test suite (`pytest tests/ -v`) and verify all 175+ existing M0–M9 tests pass (SC-008)
- [x] T067 Update `docs/architecture.md` Mermaid diagram to include telemetry cross-validation flow
- [x] T068 Update `CLAUDE.md` to reflect M10 completion status

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — core provider + cross-validator
- **US2 (Phase 4)**: Depends on Phase 3 (extends reconcile error handling)
- **US3 (Phase 5)**: Depends on Phase 3 (extends provider with 3 more data methods)
- **US4 (Phase 6)**: Depends on Phase 3 (needs runtime edges in graph store to query)
- **US5 (Phase 7)**: Depends on Phase 5 (needs all data methods implemented to verify fixture-mode)
- **CLI/Redaction (Phase 8)**: Depends on Phases 3–5 (needs full provider + validator)
- **Polish (Phase 9)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Requires Phase 2 only — MVP, no dependency on other stories
- **US2 (P1)**: Extends US1's reconcile() with error handling — sequential after US1
- **US3 (P2)**: Extends US1's provider with 3 data methods — can start after US1
- **US4 (P2)**: Consumes US1's output via QueryEngine — can start after US1
- **US5 (P2)**: Verifies all methods work in fixture mode — after US3

### Parallel Opportunities Within Phases

- Phase 1: T002, T003, T004, T005 can all run in parallel
- Phase 2: T009, T010, T011, T012 can all run in parallel (after T006–T008 sequential block)
- Phase 3: T013–T016 tests in parallel; T017–T019 sequential (each builds on previous)
- Phase 4: T023–T027 tests in parallel
- Phase 5: T031–T035 tests in parallel; T036–T038 implementation in parallel (different files)
- Phase 8: T051–T054 tests in parallel
- Phase 9: T055–T065 all parallelizable (different concerns, different files)

---

## Parallel Example: Phase 2 Foundation

```bash
# After T006–T008 (sequential IdentityClass/ReverseIndex changes):
# Launch all independent foundation tasks together:
Task T009: "Add IR dataclasses to tendril/models/ir.py"
Task T010: "Add DatadogConfig to tendril/config.py"
Task T011: "Add ProbeRequiredError to tendril/plugins/base.py"
Task T012: "Create all fixture JSON files in tests/fixtures/conformance/telemetry/datadog/"
```

## Parallel Example: Phase 5 Multi-Signal Implementation

```bash
# After US1 is complete:
Task T036: "Implement edges_from_traces in datadog_provider.py"
Task T037: "Implement edges_from_logs in datadog_provider.py"
Task T038: "Implement edges_from_rum in datadog_provider.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (scaffolding)
2. Complete Phase 2: Foundational (IR models, config, fixtures)
3. Complete Phase 3: User Story 1 (APM service-map + CrossValidator reconcile)
4. **STOP and VALIDATE**: SC-001 passes, runtime-only edge in graph store
5. All 175 existing tests still pass

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test independently → SC-001 (MVP!)
3. Add US2 → Test independently → SC-002, SC-003 (degradation)
4. Add US3 → Test independently → SC-006, SC-009, SC-010 (multi-signal)
5. Add US4 → Test independently → SC-004 (query integration)
6. Add US5 → Verify SC-007, SC-008 (fixture-only CI)
7. CLI + Redaction → Full feature
8. Polish → All SCs pass, all tests green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All fixture files are authored manually to match Datadog API response schemas
- `SecretRedactor` import from `tendril.llm.redactor` is documented coupling per spec Assumptions
- Evidence format: `datadog:{capability}:{env}:{api_path}@{iso_timestamp}`
- No live Datadog API calls in any test — fixture-only
