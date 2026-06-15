# Tasks: Query Layer, MCP Server, OSS Hygiene, and CI/CD Breadth (M5–M7)

**Input**: Design documents from `/specs/002-query-mcp-oss-cicd/`

**Build order** (per `plan.md`): M6 → M5 → M7

**Organization**: Tasks are grouped by user story (US1–US4). M6 OSS-hygiene items split across Phase 1 (setup) and Phase 2 (foundational fixture infrastructure shared by all subsequent tests), with the golden-fixture integration test landing in Phase 5 as US3's acceptance gate.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Exact file paths are included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: OSS hygiene baseline that any contributor or CI runner needs before anything else runs.

- [X] T001 [P] Create `LICENSE` at project root with full Apache-2.0 text (M6-1)
- [X] T002 [P] Create `.github/workflows/ci.yml`: triggers on push and PR to `main`; steps: `actions/checkout@v4`, `actions/setup-python@v5` (python-version: "3.12"), `pip install -e ".[dev]"`, `pytest tests/ -v --tb=short`; no secrets required (M6-2)
- [X] T003 [P] Update `pyproject.toml`: add `httpx>=0.27` to `[project.optional-dependencies.dev]`; ensure `dev` extra includes `mcp` extras so `pip install -e ".[dev]"` pulls FastAPI and uvicorn (M5-6)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Golden fixture directory and conftest helper needed by US1, US2, and US3 tests. No user story can run its test suite until these exist.

**⚠️ CRITICAL**: Complete before any user story phase.

- [X] T004 [P] Create `tests/fixtures/golden/__init__.py` (empty) and `tests/fixtures/golden/expected/depends_on_prod.json` with the canonical expected edge: `from_id`, `to_id`, `env`, `provenance`, `confidence`, `deployed_ref`, `evidence_contains`, `unknowns` (M6-3 golden dir + expected output)
- [X] T005 Create `tests/conftest.py` with `golden_fixture_paths()` pytest fixture that returns a dict of absolute paths to existing fixture files under `tests/fixtures/vcs/`, `tests/fixtures/cicd/`, avoiding any duplication of JSON (M6-3 conftest helper; must be importable by test_m5_query.py, test_golden_fixture.py, test_m7_github_actions.py)

**Checkpoint**: Foundation ready — user story phases can now proceed.

---

## Phase 3: User Story 1 — AI Agent Queries the Dependency Graph (Priority: P1) 🎯 MVP

**Goal**: All five query operations accessible via HTTP JSON POST (`/mcp/<tool>`), returning `QueryResult` with confidence, provenance, deployed refs, and unknowns on every 200 response. A coding agent can call `POST /mcp/find_relevant_repos` against a seeded graph.

**Independent Test**: Seed an in-memory KuzuStore from golden fixture data; call each QueryEngine method; verify QueryResult shape. `pytest tests/test_m5_query.py -v` must pass.

### Implementation for User Story 1

- [X] T006 [P] [US1] Create `tendril/query/response.py`: `UnknownsEntry` dataclass (fields: `kind`, `description`, `repo_id=None`, `token=None`, `candidates=None`); `QueryResult` dataclass (fields: `operation`, `env`, `results`, `confidence`, `provenance`, `deployed_refs`, `unknowns`, `metadata`) with `to_dict()` method; `aggregate_confidence(items)` (weakest link) and `aggregate_provenance(items)` (most conservative) helpers (M5-1)
- [X] T007 [P] [US1] Create `tendril/mcp/schema.py`: Pydantic v2 `BaseModel` subclasses `FindRelevantReposInput` (task, env, max_hops=3, min_confidence="low"), `ImpactAnalysisInput` (repo_id, env, min_confidence="low"), `DependencyPathInput` (from_id, to_id, env), `EnvDiffInput` (repo_id, env_a, env_b), `ExplainEdgeInput` (from_id, to_id, env); field validators for `min_confidence` enum (M5-3)
- [X] T008 [US1] Create `tendril/query/engine.py`: `QueryEngine(store: GraphStore)` with five public methods — `find_relevant_repos` (keyword BFS up to max_hops via iterative `store.neighbors()`; seed repo returned with `hop_depth=0` when no outbound edges; no-match → unknowns), `impact_analysis` (reverse neighbors BFS up to 5 hops; leaf → unknowns no-match), `dependency_path` (`store.path()`; no path → unknowns no-source), `env_diff` (two MATCH queries, Python set diff), `explain_edge` (full edge detail with evidence, ambiguous, stale, `llm_trace=None`); all return `QueryResult`; `deployed_refs={}` never None; `unknowns=[]` never None (M5-2; depends on T006)
- [X] T009 [US1] Create `tendril/mcp/server.py`: `FastAPI(title="tendril-graph MCP", version="0.1.0-alpha")`; `@asynccontextmanager` lifespan initializes `KuzuStore` from `TENDRIL_DB_PATH` env var (default `:memory:`); `QueryEngine` injected via `Depends()`; five `@app.post("/mcp/<tool>")` endpoints returning `JSONResponse`; `GET /mcp` returns tool discovery manifest listing tool names and input schemas; `HTTPException` for 400/404/500; custom 503 handler when store unavailable (M5-4; depends on T007, T008)
- [X] T010 [US1] Create `tests/test_m5_query.py`: fixture seeds in-memory `KuzuStore` from `golden_fixture_paths()`; 11 tests covering `find_relevant_repos` (keyword match, no-match → unknowns), `impact_analysis` (finds dependents, leaf → unknowns no-match), `dependency_path` (found, no path → unknowns no-source), `env_diff` (same env empty diff, one empty env valid), `explain_edge` (full evidence), `deployed_refs` never null, `unknowns` never null; verify all QueryResult fields match contract from `contracts/mcp-endpoints.md` (M5-7; depends on T004, T005, T006, T008)

**Checkpoint**: `pytest tests/test_m5_query.py -v` green. `QueryResult` field contract verified.

---

## Phase 4: User Story 2 — Developer Performs Impact Analysis via CLI (Priority: P2)

**Goal**: All five query operations accessible as CLI subcommands producing JSON output identical to HTTP responses. Developer can run `tendril query impact --repo-id <id> --env prod` and pipe or parse the result.

**Independent Test**: Invoke each CLI subcommand against the fixture graph and assert JSON output shape matches HTTP response schema. `pytest tests/test_m5_query.py` already covers engine; CLI wiring can be validated via subprocess or direct call in the existing test file.

### Implementation for User Story 2

- [X] T011 [US2] Update `tendril/cli/main.py`: wire `_query(args)` to instantiate `QueryEngine(KuzuStore(db_path))` and dispatch to the appropriate method; wire `_serve(args)` to `uvicorn.run("tendril.mcp.server:app", port=args.port)`; add five subcommands `find-relevant-repos` (flags: `--task`, `--env`, `--max-hops`, `--min-confidence`), `impact` (flags: `--repo-id`, `--env`, `--min-confidence`), `path` (flags: `--from-id`, `--to-id`, `--env`), `env-diff` (flags: `--repo-id`, `--env-a`, `--env-b`), `explain-edge` (flags: `--from-id`, `--to-id`, `--env`); output: `print(json.dumps(result.to_dict(), indent=2))` (M5-5; depends on T008, T009)

**Checkpoint**: `tendril query impact --help` shows correct flags. `tendril serve --mcp --port 8420` starts.

---

## Phase 5: User Story 3 — Open Source Contributor Reproduces the First Edge (Priority: P3)

**Goal**: Any contributor with a fresh checkout and `pip install -e ".[dev]"` can run `pytest tests/` and see all tests pass, including a test that proves the full pipeline from fixture input to a `DEPENDS_ON` edge with provenance, confidence, deployed_ref, and evidence chain matching `expected/depends_on_prod.json`.

**Independent Test**: `pytest tests/integration/test_golden_fixture.py -v` passes with zero credentials.

### Implementation for User Story 3

- [X] T012 [US3] Create `tests/integration/test_golden_fixture.py`: wire all providers from fixture files using the same pattern as `tests/test_end_to_end.py`; run `TraversalEngine.traverse()` from the anchor repo; assert at least one `DEPENDS_ON` edge matches every field in `tests/fixtures/golden/expected/depends_on_prod.json` (`from_id`, `to_id`, `env`, `provenance`, `confidence`, `deployed_ref`, `evidence_contains` substring checks, `unknowns=[]`); no live API calls, no credentials (M6-4; depends on T004, T005)

**Checkpoint**: `pytest tests/integration/test_golden_fixture.py -v` green on a fresh checkout with no credentials.

---

## Phase 6: User Story 4 — GitHub Actions Repository Gets Correct Edge Attribution (Priority: P4)

**Goal**: Repos with GitHub Actions workflows produce env-scoped `DEPENDS_ON` edges. GHA build + Octopus deploy chaining is recorded separately. Octopus 4-dimension variable scoping resolves correctly with honest tiebreaking. Bitbucket Pipelines stub passes its conformance suite.

**Independent Test**: `pytest tests/conformance/github_actions/ tests/conformance/bitbucket_pipelines/ tests/integration/test_m7_github_actions.py -v` all pass.

### Implementation for User Story 4

- [X] T013 [P] [US4] Create `tests/fixtures/conformance/cicd/github_actions/deploy_with_environment.yml` (GHA workflow with `environment: staging` on a deploy job) and `tests/fixtures/conformance/cicd/github_actions/deploy_no_environment.yml` (GHA workflow with no `environment:` blocks, build-only) (M7-4 fixtures)
- [X] T014 [P] [US4] Create `tests/fixtures/conformance/cicd/bitbucket_pipelines/bitbucket-pipelines.yml` (Bitbucket Pipelines YAML with a step containing `deployment: staging`) (M7-5 fixture)
- [X] T015 [P] [US4] Create `tendril/connectors/cicd/github_actions.py` with `GitHubActionsProvider(CICDProvider)`: `id()→"github-actions"`, `capabilities()`, `discover_for_repo()` scanning `.github/workflows/*.yml` via PyYAML (both string and `{name:..., url:...}` `environment:` forms; each job-environment pair → `PipelineBinding(roles=["deploy"], env=<name>)`; no environment blocks → `PipelineBinding(roles=["build"])` + `cicd-profile-note`; invalid YAML → skip file + note), `read_variable_store()` (vars.* readable, secrets.* masked `value=None`), `read_provider_identities()`; create `tendril/connectors/cicd/tendril-plugin-github-actions.toml` manifest (M7-1)
- [X] T016 [P] [US4] Create `tendril/connectors/cicd/bitbucket_pipelines.py` with `BitbucketPipelinesProvider(CICDProvider)` stub: `id()→"bitbucket-pipelines"`, `capabilities()`, `discover_for_repo()` parsing `bitbucket-pipelines.yml` `deployment:` fields under `pipelines.branches`, `pipelines.pull-requests`, `pipelines.custom`, `pipelines.default`; `read_variable_store()` returns empty `VariableStore`; create `tendril/connectors/cicd/tendril-plugin-bitbucket-pipelines.toml` manifest (M7-3)
- [X] T017 [US4] Update `tendril/connectors/cicd/octopus.py`: add `_scope_matches(var_scope, env, role=None, tenant=None, channel=None)→bool`; add `_best_match(candidates, env)→VarEntry|list[VarEntry]` (priority: env-scoped>role>tenant>channel>unscoped; most dimensions set wins at same priority; exact tie → return all tied candidates); update `read_variable_store()` to use `_best_match()` and return `ambiguous=True` metadata when multiple candidates returned (M7-2)
- [X] T018 [P] [US4] Create `tests/conformance/github_actions/__init__.py` (empty) and `tests/conformance/github_actions/test_github_actions_conformance.py` subclassing `CICDProviderConformance`; fixtures from T013; assert `discover_for_repo()` returns `PipelineBinding(env="staging", roles=["deploy"])` for deploy workflow; assert no-environment workflow returns build-only binding without raising (M7-4; depends on T013, T015)
- [X] T019 [P] [US4] Create `tests/conformance/bitbucket_pipelines/__init__.py` (empty) and `tests/conformance/bitbucket_pipelines/test_bitbucket_pipelines_conformance.py` subclassing `CICDProviderConformance`; fixture from T014; assert `discover_for_repo()` returns `PipelineBinding(env="staging", roles=["deploy"])` (M7-5; depends on T014, T016)
- [X] T020 [US4] Create `tests/integration/test_m7_github_actions.py`: wire fixture estate where `landing-page-ui` has `.github/workflows/deploy.yml` with `environment: staging`; run full traversal; assert `DEPENDS_ON@staging` edge with `provenance=injected`; assert Octopus variable `LandingPageUrl` scoped to `Environment=Environments-1` overrides unscoped default; assert `ambiguous=True` appears when two variables tie exactly (M7-6; depends on T015, T016, T017)

**Checkpoint**: `pytest tests/conformance/github_actions/ tests/conformance/bitbucket_pipelines/ tests/integration/test_m7_github_actions.py -v` all green.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [X] T021 Run `pytest tests/ -v --tb=short` and verify all existing 68 plus all new tests pass (zero failures, zero errors)
- [X] T022 [P] Smoke-test MCP server: start `tendril serve --mcp --port 8420`, send `POST /mcp/find_relevant_repos` with golden fixture data, verify response contains `operation`, `env`, `results`, `confidence`, `provenance`, `deployed_refs`, `unknowns`, `metadata` fields

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately. All three tasks run in parallel.
- **Phase 2 (Foundational)**: Depends on Phase 1 completion. T004 and T005 run in parallel. BLOCKS all user story tests.
- **Phase 3 (US1/P1)**: Depends on Phase 2. T006 and T007 run in parallel → T008 depends on T006 → T009 depends on T007+T008 → T010 depends on T004+T005+T006+T008.
- **Phase 4 (US2/P2)**: Depends on T008+T009. Single task.
- **Phase 5 (US3/P3)**: Depends on T004+T005. Single task. Can run in parallel with Phases 3–4 if the foundational phase is complete.
- **Phase 6 (US4/P4)**: Depends on Phase 2. T013, T014, T015, T016 run in parallel → T017 is independent update → T018 depends on T013+T015; T019 depends on T014+T016 (T018 and T019 parallel) → T020 depends on T015+T016+T017.
- **Final Phase**: Depends on all preceding phases.

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2. No dependency on other user stories.
- **US2 (P2)**: Can start after US1's T008+T009 are complete.
- **US3 (P3)**: Can start after Phase 2 (only needs conftest + fixture dir). Independent of US1 and US2.
- **US4 (P4)**: Can start after Phase 2. Independent of US1 and US2 (different files).

### Parallel Opportunities

```bash
# Phase 1 — launch all three at once:
Task: T001  # LICENSE
Task: T002  # ci.yml
Task: T003  # pyproject.toml

# Phase 2 — T004 and T005 in parallel, then T005 depends on directory existing from T004:
Task: T004  # golden fixture directory + expected JSON
Task: T005  # conftest helper

# US1 — parallel start:
Task: T006  # response.py
Task: T007  # schema.py
# Then:
Task: T008  # engine.py (needs T006)
# Then:
Task: T009  # server.py (needs T007, T008)
Task: T010  # tests (needs T004, T005, T006, T008)

# US4 — parallel start:
Task: T013  # GHA fixture files
Task: T014  # Bitbucket fixture file
Task: T015  # GHA provider
Task: T016  # Bitbucket provider
Task: T017  # Octopus update
# Then parallel:
Task: T018  # GHA conformance (needs T013, T015)
Task: T019  # Bitbucket conformance (needs T014, T016)
# Then:
Task: T020  # M7 integration test (needs T015, T016, T017)
```

---

## Implementation Strategy

### MVP First (User Story 1 — P1)

1. Complete Phase 1 (Setup) — parallel
2. Complete Phase 2 (Foundational) — fast, two files
3. Complete Phase 3 (US1): T006+T007 → T008 → T009 → T010
4. **STOP and VALIDATE**: `pytest tests/test_m5_query.py -v` green
5. Agent can now query the graph via HTTP

### Incremental Delivery

1. Phase 1+2 → Foundation
2. Phase 3 (US1) → `POST /mcp/*` endpoints live, tests green
3. Phase 4 (US2) → CLI subcommands wired
4. Phase 5 (US3) → Golden fixture integration test green, repo is contributor-ready
5. Phase 6 (US4) → GitHub Actions + Bitbucket Pipelines connectors, Octopus scoping hardened
6. Final Phase → Full 68+ test suite green, smoke test passes

---

## Summary

| Phase | Tasks | User Story | Milestone |
|---|---|---|---|
| Phase 1: Setup | T001–T003 | — | M6 hygiene base |
| Phase 2: Foundational | T004–T005 | — | M6 fixture infrastructure |
| Phase 3: Query + MCP Server | T006–T010 | US1 (P1) | M5 |
| Phase 4: CLI | T011 | US2 (P2) | M5 |
| Phase 5: Golden Fixture Test | T012 | US3 (P3) | M6 |
| Phase 6: CI/CD Connectors | T013–T020 | US4 (P4) | M7 |
| Final Phase: Polish | T021–T022 | — | All |

**Total**: 22 tasks across 7 phases
**Parallel opportunities**: 12 tasks marked [P]
**Suggested MVP scope**: Phases 1–3 (User Story 1 only — agent can query graph via HTTP)
