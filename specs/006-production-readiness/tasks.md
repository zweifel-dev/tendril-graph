# Tasks: Production Readiness — Critical Fixes and Live API Mode

**Input**: Design documents from `specs/006-production-readiness/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Tests are included where the spec requires new test coverage (FR-010, SC-001, etc.) or where the plan identifies a fix that needs regression verification. Existing 210 tests are the baseline.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing. User stories are ordered by execution dependency, not strictly by priority — US7 (P2) precedes US3 (P1) because US3 depends on the HTTP resilience utility.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new project setup needed — existing project structure is sufficient. All changes fit within existing packages.

*(No tasks — Phase 2 starts immediately.)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the shared HTTP resilience utility that US3, US7, and US8 depend on. Must complete before connector resilience or live mode work begins.

**CRITICAL**: US7 (connector resilience) and US3 (live mode) cannot begin until this phase is complete.

- [x] T001 Create `HTTPConfig` dataclass with `timeout_seconds=30`, `max_retries=3`, `backoff_base=1.0`, `backoff_factor=2.0` and `load_http_config()` factory in tendril/config.py
- [x] T002 Create `resilient_get()` function with timeout, exponential backoff retry, Retry-After header support, Content-Type checking, and `HTTPResult` dataclass in tendril/connectors/_http.py (see contracts/http-resilience.md)
- [x] T003 Create unit tests for `resilient_get()` in tests/unit/test_http_resilience.py — mock `urllib.request.urlopen` to simulate: success, timeout, 429 with Retry-After, 500 with retry, connection error, HTML response body. Verify retry count, backoff delays, and error propagation.

**Checkpoint**: `resilient_get()` is tested and available. Connector resilience and live mode work can begin.

---

## Phase 3: User Story 1 — Correct Environment Filtering (Priority: P1)

**Goal**: Fix `_path_matches_env` so it returns `False` when no path row node matches the requested environment, and add multi-env test coverage for SC-001.

**Independent Test**: Run `dependency_path` against a graph with edges in "prod" and "staging" — only the requested env's edges appear.

- [x] T004 [P] [US1] Fix `_path_matches_env` in tendril/store/kuzu_store.py:175 — change `return True` to `return False`
- [x] T005 [P] [US1] Add multi-environment fixture data (edges in both "prod" and "staging") to tests/fixtures/golden/ and add test in tests/unit/ or tests/integration/ that calls `store.path()` for env="prod" and asserts no staging edges are returned (SC-001)

**Checkpoint**: US1 complete. Environment-scoped path queries are correct. Run `pytest tests/ -v` — all tests pass.

---

## Phase 4: User Story 2 — LLM-Judged Edges Visible in Queries (Priority: P1)

**Goal**: Fix LLM grounding to use `repo_full_name` instead of `deployable_id` as edge `to_id`.

**Independent Test**: Verify an LLM-grounded edge has `to_id` in `provider:org/name` format.

- [x] T006 [P] [US2] Fix `matched_identity` in tendril/llm/grounding.py:54 — change `entry.deployable_id` to `entry.repo_full_name`
- [x] T007 [P] [US2] Add assertion in tests/integration/test_hybrid_mode.py that LLM-grounded edge `to_id` matches `provider:org/name` pattern (not a bare slug)

**Checkpoint**: US2 complete. LLM-judged edges are queryable. Run `pytest tests/ -v` — all tests pass.

---

## Phase 5: User Story 4 — Plugin Contract Validation (Priority: P2)

**Goal**: Align the in-tree `tendril-plugin.toml` contract version with `CONTRACT_VERSION` in `base.py`.

**Independent Test**: Load the Datadog manifest through `PluginManifest.validate()` — it passes.

- [x] T008 [P] [US4] Update `contract_version` from `"0.1.0"` to `"1.0.0-alpha"` in tendril/connectors/telemetry/tendril-plugin.toml:4
- [x] T009 [P] [US4] Add test that loads the Datadog manifest through `PluginManifest.validate()` and asserts it passes. Also test that a manifest with `contract_version = "2.0.0"` is rejected.

**Checkpoint**: US4 complete. Plugin validation works for in-tree providers. Run `pytest tests/ -v` — all tests pass.

---

## Phase 6: User Story 5 — Accurate Static Value Extraction (Priority: P2)

**Goal**: Fix `_extract_static_values` to reject values containing `{...}` template markers anywhere in the string, not only at the start.

**Independent Test**: Pass `https://{BaseUrl}/api` through extraction — rejected as template. Pass `https://api.prod.example.com` — accepted as static.

- [x] T010 [P] [US5] Fix template marker check in tendril/core/traversal.py:339 — change `not ref.raw_value.startswith("{")` to `"{" not in ref.raw_value`
- [x] T011 [P] [US5] Add test cases in tests/ for template detection: (1) `https://{BaseUrl}/api` classified as template, (2) `https://api.prod.example.com` classified as static, (3) `{ServiceUrl}` classified as template (regression)

**Checkpoint**: US5 complete. No false-positive static values. Run `pytest tests/ -v` — all tests pass.

---

## Phase 7: User Story 6 — Telemetry Evidence Updates on Re-Runs (Priority: P2)

**Goal**: Fix `_write_runtime_edge` to merge new evidence into existing edges instead of silently discarding it. Merge strategy: accumulate-and-deduplicate by `(locator, capability)`.

**Independent Test**: Run reconcile twice with different fixtures — evidence reflects both runs, no duplicates.

- [x] T012 [US6] Replace early return in tendril/core/cross_validate.py:397-408 with: (1) query existing edge's evidence, (2) merge old + new evidence lists, (3) deduplicate by (locator, capability) keeping newest timestamp, (4) `MATCH ... SET r.evidence = $merged` to update
- [x] T013 [US6] Add test in tests/unit/test_cross_validator.py that runs reconcile twice with different fixture data and asserts: evidence contains items from both runs, no duplicate (locator, capability) pairs exist

**Checkpoint**: US6 complete. Telemetry evidence stays fresh across re-runs. Run `pytest tests/ -v` — all tests pass.

---

## Phase 8: User Story 7 — Connector Resilience Against Live APIs (Priority: P2)

**Goal**: Wire the shared `resilient_get()` utility (from Phase 2) into all four VCS/CI/CD connectors, replacing raw `urllib.request.urlopen` calls.

**Independent Test**: Simulate HTTP 500 during `read_tree` — connector degrades gracefully, no crash.

**Depends on**: Phase 2 (Foundational) complete

- [x] T014 [P] [US7] Replace `_get()` in tendril/connectors/vcs/github.py with calls to `resilient_get()` from tendril/connectors/_http.py
- [x] T015 [P] [US7] Replace `_get()` in tendril/connectors/vcs/bitbucket_dc.py with calls to `resilient_get()`
- [x] T016 [P] [US7] Replace `_get_json()` and `_get_text()` in tendril/connectors/cicd/teamcity.py with calls to `resilient_get()`
- [x] T017 [P] [US7] Replace `_get_json()` and `_get_text()` in tendril/connectors/cicd/octopus.py with calls to `resilient_get()`
- [x] T018 [US7] Run full test suite to verify all existing fixture-mode tests pass (fixture connectors read from files, not HTTP — `resilient_get` should only be called in live-mode paths)

**Checkpoint**: US7 complete. All connectors have timeout, retry, and error handling. Run `pytest tests/ -v` — all 210+ tests pass.

---

## Phase 9: User Story 8 — Bitbucket DC Returns Complete File Trees (Priority: P2)

**Goal**: Fix `read_tree` to use the recursive browse API endpoint, returning files at all directory depths.

**Independent Test**: Call `read_tree` on a fixture with 3+ directory levels — all nested files returned.

- [x] T019 [US8] Fix `read_tree` in tendril/connectors/vcs/bitbucket_dc.py:68-83 — change URL from `/rest/api/1.0/projects/{org}/repos/{name}/files/{ref}` to `/rest/api/1.0/projects/{org}/repos/{name}/files?at={ref}&start={start}&limit=1000` (ref as query param, not path segment). Add WARNING log if file count exceeds 10,000.
- [x] T020 [P] [US8] Add fixture data with nested directories (3+ levels, e.g., `src/config/appsettings.prod.json`) to tests/fixtures/ for Bitbucket DC and add test asserting all nested files are returned by `read_tree`
- [x] T021 [US8] Update existing Bitbucket DC conformance tests in tests/conformance/bitbucket_dc/ to verify recursive tree behavior with the new endpoint format

**Checkpoint**: US8 complete. BB DC returns full recursive tree. Run `pytest tests/ -v` — all tests pass.

---

## Phase 10: User Story 3 — Graph Build Against Live Infrastructure (Priority: P1)

**Goal**: Implement live API mode for `tendril graph build` with credential configuration and provider auto-discovery. This is the largest change and the key deliverable.

**Independent Test**: Run `_graph_build()` with mocked provider constructors (no real APIs) — providers are discovered from config, missing providers are skipped with warnings, all-VCS-missing produces an error.

**Depends on**: Phase 2 (HTTP utility), Phase 8 (US7, connector resilience)

### Credential Configuration

- [x] T022 [P] [US3] Add `GitHubConfig` dataclass with `load_github_config()` factory in tendril/config.py — fields: `token`, `app_id`, `install_id`, `private_key_path`. Resolution: GH_TOKEN / GH_APP_ID+GH_INSTALL_ID+GH_PRIVATE_KEY_PATH > `[vcs.github]` TOML > empty. `is_complete()` returns True if token is set OR all three app fields are set.
- [x] T023 [P] [US3] Add `BitbucketDCConfig` dataclass with `load_bitbucket_dc_config()` factory in tendril/config.py — fields: `base_url`, `token`. Resolution: BB_BASE_URL+BB_TOKEN > `[vcs.bitbucket_dc]` TOML > empty.
- [x] T024 [P] [US3] Add `TeamCityConfig` dataclass with `load_teamcity_config()` factory in tendril/config.py — fields: `base_url`, `token`. Resolution: TC_BASE_URL+TC_TOKEN > `[cicd.teamcity]` TOML > empty.
- [x] T025 [P] [US3] Add `OctopusConfig` dataclass with `load_octopus_config()` factory in tendril/config.py — fields: `base_url`, `api_key`, `space`. Resolution: OCTO_URL+OCTO_API_KEY+OCTO_SPACE > `[cicd.octopus]` TOML > empty.
- [x] T026 [US3] Add unit tests for all four config classes in tests/unit/test_provider_config.py — verify: env var priority over TOML, empty/whitespace treated as unset, `is_complete()` and `missing_fields()` behavior for each provider

### Live Mode Branch

- [x] T027 [US3] Implement live mode in tendril/cli/main.py `_graph_build()`: remove the `if not args.fixture_dir: error` block (line 189-194). Add live mode branch that: (1) loads all provider configs, (2) checks `is_complete()` per provider, (3) instantiates available providers, (4) verifies at least one VCS provider exists (else exit 1 with error referencing .env.example), (5) passes providers to TraversalEngine. Preserve fixture mode when `--fixture-dir` is provided.
- [x] T028 [US3] Add integration test in tests/integration/test_live_mode.py — use monkeypatch to set credential env vars, mock provider constructors (no real API calls), verify: (1) providers discovered from config, (2) missing providers skipped with WARNING, (3) `metadata.degradation_notices` populated for skipped providers, (4) all-VCS-missing produces exit code 1
- [x] T029 [US3] Verify existing fixture-mode tests in tests/integration/test_cli_graph_build.py pass unchanged — fixture mode must remain the default when `--fixture-dir` is provided

**Checkpoint**: US3 complete. `tendril graph build` works in both fixture and live mode. Run `pytest tests/ -v` — all tests pass. SC-003a (automated fixture test) passes.

---

## Phase 11: User Story 9 — MCP Server Test Coverage (Priority: P3)

**Goal**: Add automated test coverage for all 5 MCP server endpoints using FastAPI TestClient.

**Independent Test**: Run the new test file — all endpoints return correct response shapes and error codes.

- [x] T030 [US9] Create tests/test_mcp_server.py with TestClient setup: override `get_engine` dependency to inject QueryEngine backed by in-memory Kùzu store seeded from golden fixture data. Implement 10+ test cases per FR-010:
  1. `POST /mcp/find_relevant_repos` — valid input → 200 + QueryResult shape
  2. `POST /mcp/impact_analysis` — valid input → 200 + QueryResult shape
  3. `POST /mcp/dependency_path` — valid input → 200 + QueryResult shape
  4. `POST /mcp/env_diff` — valid input → 200 + QueryResult shape
  5. `POST /mcp/explain_edge` — valid input → 200 + QueryResult shape
  6. `POST /mcp/find_relevant_repos` — invalid `min_confidence` → 400 + structured error body
  7. `GET /mcp` — discovery manifest → 200 + tool list
  8. `GET /nonexistent` — 404 + `{"error": {"code": 404, "message": ...}}`
  9. `POST /mcp/find_relevant_repos` — store unavailable → 503 + structured error body
  10. `POST /mcp/impact_analysis` — missing required field → 400 + validation error

**Checkpoint**: US9 complete. MCP server has 10+ automated tests. Run `pytest tests/test_mcp_server.py -v` — all pass.

---

## Phase 12: User Story 10 — Documentation Matches Reality (Priority: P3)

**Goal**: Update README quickstart and CLAUDE.md package layout description to match the actual CLI interface and code structure.

**Independent Test**: Every command in the README quickstart section either works or is marked as planned. CLAUDE.md describes the real package layout.

- [x] T031 [P] [US10] Update README.md quickstart section: replace `Tendril-Graph init` / `Tendril-Graph providers add` / `Tendril-Graph graph build` with actual CLI commands (`tendril graph build`, `tendril query ...`, `tendril serve --mcp`). Mark unimplemented commands (e.g., `providers add`) as "planned." Fix argument names/positions to match actual CLI (e.g., `--task` not positional, `--repo-id` not positional, `--from-id --to-id --env` not `<edge-id>`).
- [x] T032 [P] [US10] Fix CLAUDE.md "Package layout note" section — replace "All implementation packages live at the project root as flat top-level packages. `tendril/` is a thin shim" with accurate description: "All code lives inside `tendril/` as subpackages. Imports use `from tendril.X import Y`."
- [x] T033 [US10] Verify all commands listed in the updated README quickstart by running them with `--help` flag to confirm they exist and accept the documented arguments

**Checkpoint**: US10 complete. Documentation matches reality. New users can follow the quickstart without hitting non-existent commands.

---

## Phase 13: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, regression testing, and cross-story validation.

- [x] T034 Run full regression: `pytest tests/ -v --tb=short` — all existing + new tests pass (SC-010)
- [x] T035 Run quickstart.md verification commands from specs/006-production-readiness/quickstart.md
- [x] T036 Verify SC-003a: fixture-mode graph build produces same edges as golden fixture test
- [x] T037 [P] Extend secret redaction patterns in tendril/llm/redactor.py to cover `*connstr*` variants (common in .NET connection strings) per spec Assumptions

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) ── nothing needed
Phase 2 (Foundational: HTTP utility) ── no dependencies, start immediately
  │
  ├── Phase 3 (US1: env filter) ── independent, can start after Phase 2
  ├── Phase 4 (US2: LLM to_id) ── independent, can start after Phase 2
  ├── Phase 5 (US4: plugin version) ── independent, can start immediately
  ├── Phase 6 (US5: template markers) ── independent, can start immediately
  ├── Phase 7 (US6: evidence merge) ── independent, can start immediately
  │
  ├── Phase 8 (US7: connector resilience) ── depends on Phase 2
  ├── Phase 9 (US8: BB DC tree) ── independent, can start immediately
  │
  └── Phase 10 (US3: live mode) ── depends on Phase 2 + Phase 8 (US7)
      │
      ├── Phase 11 (US9: MCP tests) ── independent, can start immediately
      └── Phase 12 (US10: docs) ── independent, can start immediately

Phase 13 (Polish) ── depends on all above
```

### User Story Dependencies

- **US1 (env filter)**: Independent — can start immediately
- **US2 (LLM to_id)**: Independent — can start immediately
- **US3 (live mode)**: Depends on US7 (connector resilience) + Phase 2 (HTTP utility)
- **US4 (plugin contract)**: Independent — can start immediately
- **US5 (template markers)**: Independent — can start immediately
- **US6 (evidence merge)**: Independent — can start immediately
- **US7 (connector resilience)**: Depends on Phase 2 (HTTP utility)
- **US8 (BB DC tree)**: Independent — can start immediately
- **US9 (MCP tests)**: Independent — can start immediately
- **US10 (docs)**: Independent — can start immediately

### Within Each User Story

- Fix before test (the fix is needed for tests to pass)
- Core implementation before integration verification
- Run full `pytest tests/ -v` after each story checkpoint

### Parallel Opportunities

**Maximum parallelism (9 stories simultaneously)**:
- Phase 2 + US1 + US2 + US4 + US5 + US6 + US8 + US9 + US10 can all start immediately
- US7 starts once Phase 2 completes
- US3 starts once Phase 2 + US7 complete

**Typical serial execution order**:
1. Phase 2 (HTTP utility) — 3 tasks
2. US1, US2, US4, US5, US6 (all simple fixes) — 10 tasks, parallelizable
3. US7 (connector resilience) — 5 tasks
4. US8 (BB DC tree) — 3 tasks, parallel with US7
5. US3 (live mode) — 8 tasks, the big one
6. US9, US10 (test coverage, docs) — 4 tasks, parallelizable
7. Phase 13 (polish) — 4 tasks

---

## Parallel Example: Tier 1 Correctness Fixes

```text
# All five fixes can run in parallel (different files, no dependencies):
T004 [US1] Fix _path_matches_env in tendril/store/kuzu_store.py
T006 [US2] Fix matched_identity in tendril/llm/grounding.py
T008 [US4] Update contract_version in tendril/connectors/telemetry/tendril-plugin.toml
T010 [US5] Fix template check in tendril/core/traversal.py
T012 [US6] Fix evidence merge in tendril/core/cross_validate.py

# All five test tasks can also run in parallel:
T005 [US1] Add multi-env fixture and test
T007 [US2] Add LLM to_id format assertion
T009 [US4] Add manifest validation test
T011 [US5] Add template detection test cases
T013 [US6] Add evidence re-run merge test
```

---

## Parallel Example: Live Mode Credential Config

```text
# All four config classes can be created in parallel (same file, different classes):
T022 [US3] GitHubConfig in tendril/config.py
T023 [US3] BitbucketDCConfig in tendril/config.py
T024 [US3] TeamCityConfig in tendril/config.py
T025 [US3] OctopusConfig in tendril/config.py
```

---

## Implementation Strategy

### MVP First (Tier 1 Fixes)

1. Complete Phase 2: HTTP utility (3 tasks)
2. Complete US1 + US2 + US4 + US5 + US6 (10 tasks, parallelizable)
3. **STOP and VALIDATE**: All 5 critical bugs fixed. Run `pytest tests/ -v`.
4. All existing queries are now correct.

### Incremental Delivery

1. Tier 1 fixes → All bugs fixed, queries correct
2. US7 (connector resilience) → Connectors handle errors gracefully
3. US8 (BB DC tree) → Bitbucket DC returns complete trees
4. US3 (live mode) → **First real run possible** — the key milestone
5. US9 (MCP tests) → Agent interface is tested
6. US10 (docs) → Documentation matches reality
7. Polish → Full regression, secret redaction extension

### Key Milestone

**After US3 (T029)**: Tendril-Graph can run `tendril graph build --anchor <repo> --env prod` against a real Bitbucket/TeamCity/Octopus/GitHub estate with valid credentials. This is the "first real run" milestone that closes the gap identified in review-v2.md.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- US3 is P1 priority but Phase 10 in execution order due to dependency on US7 + HTTP utility
- Each user story is independently testable at its checkpoint
- Commit after each task or logical group
- All 210 existing tests must continue to pass throughout (SC-010)
- Total: 37 tasks across 13 phases
