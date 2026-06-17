# Implementation Plan: Production Readiness — Critical Fixes and Live API Mode

**Branch**: `006-production-readiness` | **Date**: 2026-06-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-production-readiness/spec.md`

## Summary

Fix 5 critical correctness bugs (env filtering, LLM edge IDs, plugin contract version, template marker detection, evidence staleness) and implement live API mode for `graph build` with credential configuration, HTTP resilience, Bitbucket DC recursive tree, and MCP server tests. The work bridges the gap from "working prototype against fixtures" to "first real run against live infrastructure."

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: Kùzu (graph store), FastAPI (MCP server), urllib.request (HTTP, stdlib), Pydantic v2 (schemas)

**Storage**: Embedded Kùzu (no external service)

**Testing**: pytest, FastAPI TestClient, fixture-mode (zero credentials in CI)

**Target Platform**: Linux/macOS (CLI tool)

**Project Type**: CLI + library + HTTP server

**Performance Goals**: Graph build completes against a ~50-repo estate without timeout; HTTP calls have 30s timeout with 3 retries

**Constraints**: Read-only provider access; secret-redacting; zero credentials in CI; all existing 210 tests must continue to pass

**Scale/Scope**: 5 bug fixes, 1 new module (HTTP resilience), 4 new config classes, 1 endpoint change, 1 new test file

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Plugin-First (NON-NEGOTIABLE) | PASS | No core changes for provider logic. HTTP resilience is a shared utility. Config classes are per-provider following established patterns. |
| II. Projection Join | PASS | No changes to join mechanism. FR-002 fixes the identifier format so joins work correctly. |
| III. Global Index, Anchor Traversal | PASS | No changes to indexing. FR-002 ensures LLM edges use indexed identifiers. |
| IV. CI/CD Attribution Per-Repo | PASS | No changes to attribution logic. |
| V. Graceful Degradation (NON-NEGOTIABLE) | PASS | Live mode degrades per-provider (FR-006). HTTP resilience returns degraded results (FR-009). Missing credentials skip, never crash. |
| VI. Evidence-Backed Edges | PASS | FR-005 improves evidence handling (merge, not discard). No edges lose evidence. |
| VII. Non-Fabrication (NON-NEGOTIABLE) | PASS | FR-004 prevents false static values. No fabrication introduced. |
| VIII. Grounded LLM Judgment | PASS | FR-002 fixes grounding output format. Grounding logic unchanged. |
| IX. Read-Only, Secret-Redacting (NON-NEGOTIABLE) | PASS | No write paths added. Credentials read from env vars, never persisted. |
| X. Deployed-Ref Accuracy | PASS | Live mode inherits existing deployed-ref resolution. |

**Pre-research gate: PASS.** No violations.

## Project Structure

### Documentation (this feature)

```text
specs/006-production-readiness/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 research findings
├── data-model.md        # Entity/data model
├── quickstart.md        # Developer quickstart
├── contracts/
│   ├── http-resilience.md   # HTTP utility contract
│   └── provider-config.md   # Credential config contract
├── checklists/
│   ├── requirements.md      # Spec quality validation
│   └── production-readiness.md  # Requirements completeness (40 items, all resolved)
└── tasks.md             # Phase 2 output (created by /speckit-tasks)
```

### Source Code (repository root)

```text
tendril/
├── config.py                      # MODIFY: add GitHubConfig, BitbucketDCConfig, TeamCityConfig, OctopusConfig, HTTPConfig
├── cli/
│   └── main.py                    # MODIFY: add live mode branch in _graph_build()
├── connectors/
│   ├── _http.py                   # NEW: shared HTTP resilience utility
│   ├── vcs/
│   │   ├── github.py              # MODIFY: use resilient_get()
│   │   └── bitbucket_dc.py        # MODIFY: fix read_tree endpoint + use resilient_get()
│   ├── cicd/
│   │   ├── teamcity.py            # MODIFY: use resilient_get()
│   │   └── octopus.py             # MODIFY: use resilient_get()
│   └── telemetry/
│       └── tendril-plugin.toml    # MODIFY: contract_version "0.1.0" → "1.0.0-alpha"
├── core/
│   ├── traversal.py               # MODIFY: fix _extract_static_values template check
│   └── cross_validate.py          # MODIFY: fix _write_runtime_edge evidence merge
├── llm/
│   └── grounding.py               # MODIFY: fix to_id field
├── plugins/
│   └── base.py                    # NO CHANGE (CONTRACT_VERSION is already correct)
├── store/
│   └── kuzu_store.py              # MODIFY: fix _path_matches_env return
└── mcp/
    ├── server.py                  # NO CHANGE
    └── schema.py                  # NO CHANGE

tests/
├── test_mcp_server.py             # NEW: MCP server TestClient tests
├── unit/
│   └── test_http_resilience.py    # NEW: HTTP utility unit tests
├── fixtures/
│   └── golden/                    # MODIFY: add multi-env fixtures for SC-001
└── [existing tests unchanged]
```

**Structure Decision**: All changes fit within the existing project structure. One new module (`connectors/_http.py`) and two new test files. No new packages or restructuring required.

## Implementation Phases

### Group A: Tier 1 Correctness Fixes (5 tasks, independent, parallelizable)

All five fixes are isolated one-to-few-line changes with no dependencies between them.

#### A1: Fix `_path_matches_env` (FR-001)

**File**: `tendril/store/kuzu_store.py:175`
**Change**: `return True` → `return False`
**Test**: Add multi-environment fixture and test to verify `store.path()` excludes non-matching envs. Add fixture with edges in "prod" and "staging" to validate SC-001.
**Risk**: Low. `store.path()` is not called by `QueryEngine` (all queries use direct Cypher with `WHERE r.env = $env`). The fix makes the `GraphStore.path()` API correct for any future caller.

#### A2: Fix LLM grounding `to_id` (FR-002)

**File**: `tendril/llm/grounding.py:54`
**Change**: `matched_identity=entry.deployable_id` → `matched_identity=entry.repo_full_name`
**Test**: Existing hybrid mode tests should catch the format change. Add an assertion in `test_hybrid_mode.py` that LLM-grounded edge `to_id` matches `provider:org/name` pattern.
**Risk**: Low. Single field swap; `repo_full_name` is already on the same `IndexEntry` object.

#### A3: Fix plugin contract version (FR-003)

**File**: `tendril/connectors/telemetry/tendril-plugin.toml:4`
**Change**: `contract_version = "0.1.0"` → `contract_version = "1.0.0-alpha"`
**Test**: Add a test that loads the manifest through `PluginManifest.validate()` and asserts it passes.
**Risk**: Minimal. Only one TOML manifest exists in the codebase.

#### A4: Fix template marker detection (FR-004)

**File**: `tendril/core/traversal.py:339`
**Change**: `not ref.raw_value.startswith("{")` → `"{" not in ref.raw_value`
**Test**: Add test case with `https://{BaseUrl}/api` — must be classified as a template, not a static value. Add test with `https://api.prod.example.com` — must remain classified as static.
**Risk**: Low. The new check is a strict superset of the old check. Literal `{` in config values is vanishingly rare (would be `%7B` in URLs).

#### A5: Fix evidence update on re-runs (FR-005)

**File**: `tendril/core/cross_validate.py:397-408`
**Change**: Replace the early `return` on existing edge with: (1) query existing evidence, (2) merge new + old evidence, (3) deduplicate by `(locator, capability)`, (4) `SET r.evidence = $merged`.
**Test**: Add test in `test_cross_validator.py`: run reconcile twice with different fixtures, assert evidence contains items from both runs with no duplicates.
**Risk**: Medium. Requires understanding Kùzu's `SET` on relationship properties. The v0 comment was wrong about Kùzu capabilities — SET works on relationships.

### Group B: Live Infrastructure (3 tasks, sequential)

Dependency chain: FR-009 (HTTP utility) → FR-007 (credential config) → FR-006 (live mode).

#### B1: HTTP Resilience Utility (FR-009)

**New file**: `tendril/connectors/_http.py`
**Contract**: See `contracts/http-resilience.md` for full interface.
**Changes to existing connectors**:
- `github.py`: Replace `_get()` with calls to `resilient_get()`
- `bitbucket_dc.py`: Same
- `teamcity.py`: Replace `_get_json()` / `_get_text()` with `resilient_get()`
- `octopus.py`: Same

**New config**: `HTTPConfig` dataclass in `config.py` with `timeout_seconds=30`, `max_retries=3`, `backoff_base=1.0`, `backoff_factor=2.0`.

**Test**: New `tests/unit/test_http_resilience.py` — mock `urllib.request.urlopen` to simulate: success, timeout, 429 with Retry-After, 500, connection error, HTML response. Verify retry count, backoff timing, and error propagation.
**Risk**: Medium. Touches all four connectors. Must ensure existing fixture-mode tests still pass (fixture-mode connectors read from files, not HTTP — so `resilient_get` should only be called in live mode paths).

#### B2: Provider Credential Configuration (FR-007)

**File**: `tendril/config.py`
**Contract**: See `contracts/provider-config.md` for full interface.
**Changes**: Add `GitHubConfig`, `BitbucketDCConfig`, `TeamCityConfig`, `OctopusConfig` dataclasses with `load_*_config()` factory functions following the existing `LLMConfig`/`DatadogConfig` pattern. Add `HTTPConfig`.
**Test**: Unit tests for each config class: env var priority over TOML, empty/whitespace treated as unset, `is_complete()` / `missing_fields()` behavior.
**Risk**: Low. Follows an established pattern with no novel logic.

#### B3: Live API Mode (FR-006)

**File**: `tendril/cli/main.py` — `_graph_build()` (lines 189+)
**Changes**:
1. Remove the `if not args.fixture_dir: print("Error..."); return 1` block
2. Add live mode branch: load configs → check `is_complete()` per provider → instantiate available providers → verify at least one VCS → proceed with traversal
3. Fixture mode remains the default when `--fixture-dir` is provided

**Test**: Add integration test: `_graph_build()` with mocked provider constructors (no real API calls) to verify the provider discovery and degradation logic. Existing `test_cli_graph_build.py` fixture tests must continue to pass unchanged.
**Risk**: High. This is the largest change. Must carefully preserve fixture-mode behavior as the default code path. The provider construction logic must handle all permutations of available/missing credentials.

### Group C: Connector Fix (1 task, independent)

#### C1: Bitbucket DC Recursive Tree (FR-008)

**File**: `tendril/connectors/vcs/bitbucket_dc.py:68-83`
**Change**: Modify `read_tree` to use `/rest/api/1.0/projects/{org}/repos/{name}/files?at={ref}&start={start}&limit=1000` (with `at` as query param, no path suffix) instead of `/files/{ref}`.
**Test**: Add a fixture with nested directories (3+ levels) and verify all files are returned. Add warning test for 10,000+ file count.
**Risk**: Medium. Changes the API endpoint. Must verify against Bitbucket DC API documentation that `/files?at=` returns recursive results. Existing fixture tests need fixture data that includes nested paths.

### Group D: Test Coverage (1 task, independent)

#### D1: MCP Server Tests (FR-010)

**New file**: `tests/test_mcp_server.py`
**Approach**: Use `fastapi.testclient.TestClient(app)` with dependency override to inject a pre-seeded `QueryEngine` backed by an in-memory Kùzu store with golden fixture data.

**Test cases** (minimum 10):
1. `POST /mcp/find_relevant_repos` — valid input → 200 + QueryResult shape
2. `POST /mcp/impact_analysis` — valid input → 200 + QueryResult shape
3. `POST /mcp/dependency_path` — valid input → 200 + QueryResult shape
4. `POST /mcp/env_diff` — valid input → 200 + QueryResult shape
5. `POST /mcp/explain_edge` — valid input → 200 + QueryResult shape
6. `POST /mcp/find_relevant_repos` — invalid `min_confidence` → 400 + error body
7. `GET /mcp` — discovery manifest → 200 + tool list
8. `GET /nonexistent` — unknown route → 404 + structured error body
9. `POST /mcp/find_relevant_repos` — store unavailable → 503 + error body
10. `POST /mcp/impact_analysis` — missing required field → 400 + validation error

**Risk**: Low. New test file only; no production code changes. Uses FastAPI's standard TestClient pattern.

## Recommended Execution Order

```
Week 1: Group A (all 5 fixes) + Group D (MCP tests)
         ├── A1-A5 can be done in any order or parallel
         └── D1 is independent

Week 2: Group B (sequential) + Group C
         ├── B1 (HTTP resilience) — first, since B2 and B3 depend on it
         ├── B2 (credential config) — after B1
         ├── C1 (BB DC tree) — independent, parallel with B1/B2
         └── B3 (live mode) — last, after B1+B2+C1

Final: Full regression run, documentation updates (FR-012, FR-013 from Tier 3)
```

## Complexity Tracking

No constitution violations to justify. All changes fit within existing architecture:
- No new packages (one new module in existing package)
- No new dependencies
- No new provider interfaces
- No core logic changes (only callers and utilities)

## Post-Phase 1 Constitution Re-Check

| Principle | Status | Notes |
|---|---|---|
| I. Plugin-First | PASS | `_http.py` is a shared utility, not a core change. Config classes are per-provider. |
| V. Graceful Degradation | PASS | Live mode auto-discovers available providers and degrades per-provider. HTTP utility never crashes. |
| VII. Non-Fabrication | PASS | Template fix prevents false statics. Evidence merge preserves all data. |
| IX. Read-Only, Secret-Redacting | PASS | No write paths. Credentials read from env, never stored. |

**Post-design gate: PASS.** No violations introduced by the design.
