# Implementation Plan: Query Layer, MCP Server, OSS Hygiene, and CI/CD Breadth (M5–M7)

**Branch**: `002-query-mcp-oss-cicd` | **Date**: 2026-06-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-query-mcp-oss-cicd/spec.md`

---

## Summary

Implement M5 (query engine + MCP HTTP server), M6 (golden fixture + CI workflow + LICENSE), and M7 (GitHub Actions connector + full Octopus scope priority + Bitbucket Pipelines stub), building on the complete M0–M4 foundation. Build order is M6 → M5 → M7. All work is behind existing plugin seams; no core changes required.

---

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: FastAPI + Uvicorn (MCP server — already in `[project.optional-dependencies.mcp]` in `pyproject.toml`), Pydantic v2 (input validation — bundled with FastAPI), PyYAML (workflow file parsing — already in core dependencies), Kùzu (embedded graph store — already in use), pytest (existing test suite)

**Storage**: Kùzu embedded graph store (existing). Schema unchanged. All query operations use the existing `KuzuStore.query()` method with parameterized Cypher strings.

**Testing**: pytest (existing). New test files: `tests/test_m5_query.py`, `tests/integration/test_golden_fixture.py`, `tests/conformance/github_actions/`, `tests/conformance/bitbucket_pipelines/`

**Target Platform**: Linux/macOS/Windows server (Python process). CI on GitHub Actions hosted runners (ubuntu-latest).

**Performance Goals**: Interactive response on small-to-mid estates (tens to hundreds of nodes). No formal SLA in v0. Kùzu's embedded query engine handles this without caching.

**Constraints**: Zero external credentials required for tests. All CI runs must pass with only fixture data.

**Scale/Scope**: 3-repo golden fixture estate. Kùzu in-memory for tests, file-backed for production.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Plugin-First | ✅ PASS | `GitHubActionsProvider` and `BitbucketPipelinesProvider` implement `CICDProvider` ABC. `QueryEngine` reads from `GraphStore` ABC. No core changes. |
| II. Projection Join | ✅ PASS | Query layer reads existing `DEPENDS_ON` edges produced by the projection join. No bypass. |
| III. Global Index / Anchor Traversal | ✅ PASS | Query layer traverses the already-built global index. No new indexing logic. |
| IV. CI/CD Attribution Per-Repo | ✅ PASS | `GitHubActionsProvider` produces per-repo `PipelineBinding[]`. Octopus scoping update is per-variable resolution. |
| V. Capability Detection (NON-NEG) | ✅ PASS | `GitHubActionsProvider` degrades gracefully when no `environment:` blocks found. Bitbucket Pipelines stub returns empty variable store. LLM layer is optional. |
| VI. Evidence-Backed Edges | ✅ PASS | Query results surface `evidence[]`, `deployed_ref`, `provenance`, `confidence` from existing edges. New edges from M7 connectors carry evidence from workflow files. |
| VII. Honesty / Non-Fabrication (NON-NEG) | ✅ PASS | Octopus tiebreaker emits `ambiguous-match` candidates. `unknowns[]` is always present on every 200 response. No auto-picking. |
| VIII. Grounded LLM | ✅ PASS | LLM-assisted relevance in `find_relevant_repos` is optional, secondary, and proposals must be grounded against the reverse index before inclusion. |
| IX. Read-Only / Secret-Redacting (NON-NEG) | ✅ PASS | Query layer is read-only. GitHub Actions `secrets.*` recorded as name-only with `is_secret=True, value=None`. MCP server has no write endpoints. |
| X. Deployed-Ref Accuracy | ✅ PASS | `deployed_ref` is read from existing `DEPLOYED_AS` edges built by M4. Query layer surfaces it unchanged. |

**Constitution Check result: ALL PASS. Proceed.**

---

## Project Structure

### Documentation (this feature)

```text
specs/002-query-mcp-oss-cicd/
├── plan.md              # This file
├── research.md          # Phase 0 — research decisions
├── data-model.md        # Phase 1 — QueryResult, UnknownsEntry, input models
├── contracts/
│   └── mcp-endpoints.md # HTTP endpoint schemas for all 5 tools
└── tasks.md             # Phase 2 — task breakdown (/speckit-tasks)
```

### Source Code Layout (additions and changes)

```text
tendril/
├── query/
│   ├── __init__.py           (exists — empty, no change)
│   ├── engine.py             (NEW — QueryEngine: 5 query methods)
│   └── response.py           (NEW — QueryResult, UnknownsEntry dataclasses)
├── mcp/
│   ├── __init__.py           (exists — empty, no change)
│   ├── server.py             (NEW — FastAPI app, 5 POST endpoints)
│   └── schema.py             (NEW — Pydantic input models)
├── connectors/
│   └── cicd/
│       ├── github_actions.py (NEW — GitHubActionsProvider)
│       └── bitbucket_pipelines.py (NEW — BitbucketPipelinesProvider stub)
└── cli/
    └── main.py               (UPDATE — wire _query() and _serve() to real impls)

tests/
├── fixtures/
│   └── golden/               (NEW directory)
│       ├── __init__.py
│       ├── vcs/
│       │   ├── bitbucket_dc/ (symlink-equivalent: reuse tests/fixtures/vcs/bitbucket_dc/)
│       │   └── github/       (symlink-equivalent: reuse tests/fixtures/vcs/github/)
│       ├── cicd/
│       │   ├── octopus/      (symlink-equivalent: reuse tests/fixtures/cicd/octopus/)
│       │   └── teamcity/     (symlink-equivalent: reuse tests/fixtures/cicd/teamcity/)
│       └── expected/
│           └── depends_on_prod.json  (NEW — canonical expected output)
├── integration/
│   ├── test_golden_fixture.py  (NEW — M6 acceptance: full pipeline, no credentials)
│   └── test_m7_github_actions.py (NEW — M7 acceptance: GHA staging edge)
├── conformance/
│   ├── github_actions/         (NEW directory)
│   │   ├── __init__.py
│   │   └── test_github_actions_conformance.py
│   └── bitbucket_pipelines/    (NEW directory)
│       ├── __init__.py
│       └── test_bitbucket_pipelines_conformance.py
└── test_m5_query.py            (NEW — QueryEngine unit tests)

.github/
└── workflows/
    └── ci.yml                  (NEW — public CI pipeline)

LICENSE                         (NEW — Apache-2.0)
pyproject.toml                  (UPDATE — add fastapi, uvicorn, pyyaml to dependencies)
```

**Structure Decision**: Flat top-level package layout per existing convention. New packages added at the same level as existing `query/`, `mcp/`, `connectors/cicd/`. Golden fixture reuses existing fixture files via a conftest helper rather than duplicating JSON.

---

## Complexity Tracking

No constitution violations. No complexity justification required.

---

## Phase 0: Research

*Complete. See `research.md`.*

Key decisions resolved:
- **Wire protocol**: HTTP JSON POST, flat body, forward-compatible with MCP framing (Decision 1)
- **Kùzu queries**: Variable-length Cypher patterns via existing `KuzuStore.query()` (Decision 2)
- **FastAPI pattern**: Module-level singleton store, injected via `Depends()` (Decision 3)
- **Golden fixture**: Reuse existing conformance fixtures + add `expected/` output file (Decision 4)
- **YAML parsing**: PyYAML for GitHub Actions workflow files (Decision 5)
- **Octopus scoping**: 4-dimension priority + ambiguous-emit tiebreaker (Decision 6)
- **Build order**: M6 → M5 → M7 (Decision 7)

---

## Phase 1: Design & Contracts

*Complete. See `data-model.md` and `contracts/mcp-endpoints.md`.*

### Post-Design Constitution Re-Check

All five query operations return `QueryResult` with `unknowns[]` always present — principle VII satisfied. No endpoint writes to the graph store — principle IX satisfied. GitHub Actions `secrets.*` masked — principle IX satisfied. Octopus ambiguous ties emitted as candidates — principle VII satisfied. All good.

---

## Phase 2: Implementation Milestones

### M6 — OSS Hygiene + Golden Fixtures (implement first)

**Goal**: Any contributor reproduces the first edge with no credentials. CI runs automatically.

#### M6-1: License file
- Create `LICENSE` at project root with Apache-2.0 text.

#### M6-2: GitHub Actions CI workflow
- Create `.github/workflows/ci.yml` targeting pushes and PRs to `main`.
- Steps: `actions/checkout@v4`, `actions/setup-python@v5` (python 3.12), `pip install -e ".[dev]"`, `pytest tests/ -v --tb=short`.
- No secrets required; all tests run against fixtures.

#### M6-3: Golden fixture structure
- Create `tests/fixtures/golden/` directory with `__init__.py`.
- Create `tests/fixtures/golden/expected/depends_on_prod.json` with the canonical expected edge output (matching M4 SC-003 assertions).
- Create `tests/conftest.py` fixture helper `golden_fixture_paths()` that returns paths to existing fixture files, allowing `test_golden_fixture.py` to use the existing `tests/fixtures/` files without duplication.

**`expected/depends_on_prod.json` contents**:
```json
{
  "from_id": "bitbucket-dc:acme/webforms-solution",
  "to_id": "github:acme/landing-page-ui",
  "env": "prod",
  "provenance": "injected",
  "confidence": "high",
  "deployed_ref": "abc123def456",
  "evidence_contains": ["home.aspx", "appsettings.prod.json", "octopus"],
  "unknowns": []
}
```

#### M6-4: Golden fixture integration test
- Create `tests/integration/test_golden_fixture.py`.
- Wire up all providers from fixture files (using the pattern established in `test_end_to_end.py`).
- Run `TraversalEngine.traverse()` from the anchor.
- Assert the golden edge fields match `expected/depends_on_prod.json`.
- **Acceptance**: `pytest tests/integration/test_golden_fixture.py -v` passes with zero credentials.

---

### M5 — Query Layer + MCP Server

**Goal**: Five query operations accessible via HTTP and CLI.

#### M5-1: `tendril/query/response.py`
- `UnknownsEntry` dataclass with fields: `kind`, `description`, `repo_id=None`, `token=None`, `candidates=None`.
- `QueryResult` dataclass with all fields per data-model.md. Include `to_dict()` method for JSON serialization.
- Helper `aggregate_confidence(items)` → weakest link. Helper `aggregate_provenance(items)` → most conservative.

#### M5-2: `tendril/query/engine.py`
- `QueryEngine(store: GraphStore)` with five public methods matching the contract in `contracts/mcp-endpoints.md`.
- All methods return `QueryResult`. All data-level empty/missing cases return 200-equivalent `QueryResult` with appropriate `unknowns` entry.
- **Kùzu traversal note**: `KuzuStore` already implements `neighbors()` (single-hop, with env/confidence filtering) and `path()` (shortestPath — env filter applied in Python post-query, not inline). Variable-length `*1..N` Cypher patterns may not be supported for filtered multi-hop in Kùzu v0.8; use iterative `neighbors()` calls for BFS up to `max_hops` as a safe fallback. Verify `*1..N` syntax support experimentally during implementation and use the iterative approach if it fails.
- `find_relevant_repos`: keyword match on `Repo.name` and `Repo.id` to seed repos; iterative `store.neighbors()` BFS up to `max_hops`; filter results by env and min_confidence.
- `impact_analysis`: reverse `neighbors()` (inbound edges) iteratively up to 5 hops to find all dependents of target repo.
- `dependency_path`: `store.path(from_id, to_id, env)` (already implemented, env-filter in Python).
- `env_diff`: two MATCH queries (one per env), Python set diff.
- `explain_edge`: full edge detail including `evidence`, `ambiguous`, `stale`, `llm_trace=None`.

#### M5-3: `tendril/mcp/schema.py`
- Pydantic v2 `BaseModel` subclasses for each tool input: `FindRelevantReposInput`, `ImpactAnalysisInput`, `DependencyPathInput`, `EnvDiffInput`, `ExplainEdgeInput`.
- Field validators where needed (e.g., `min_confidence` must be one of `high|medium|low`).

#### M5-4: `tendril/mcp/server.py`
- `FastAPI(title="tendril-graph MCP", version="0.1.0-alpha")`.
- Lifespan context manager initializes `KuzuStore` from `TENDRIL_DB_PATH` env var (default `:memory:`).
- `QueryEngine` injected via `Depends()`.
- Five `@app.post("/mcp/<tool>")` endpoints returning `JSONResponse`.
- `HTTPException` for 400/404/500 cases. Custom exception handler for `503` when store is unavailable.
- `GET /mcp` returns a tool discovery manifest (list of tool names and their input schemas) — the forward-compat MCP seam.

#### M5-5: Update `tendril/cli/main.py`
- Wire `_query(args)` to instantiate `QueryEngine(KuzuStore(db_path))` and call the appropriate method.
- Wire `_serve(args)` to launch `uvicorn.run("tendril.mcp.server:app", port=args.port)`.
- Rename existing query subcommands to match FR-004 names: `find-relevant-repos`, `impact`, `path`, `env-diff`, `explain-edge`.
- Each subcommand adds the appropriate CLI flags (e.g., `--task`, `--env`, `--max-hops`).
- Output: `print(json.dumps(result.to_dict(), indent=2))`.

#### M5-6: Update `pyproject.toml`
- FastAPI `>=0.115` and `uvicorn>=0.30` already exist in `[project.optional-dependencies.mcp]`. PyYAML `>=6.0` already in core dependencies. No new server-side deps needed.
- Add `httpx>=0.27` to `[project.optional-dependencies.dev]` for the FastAPI `TestClient` used in `test_m5_query.py`.
- Ensure the `dev` extra includes the `mcp` extras (i.e., `dev = ["tendril-graph[mcp]", "httpx>=0.27", ...]`) so `pip install -e ".[dev]"` pulls FastAPI/uvicorn for test runs.

#### M5-7: `tests/test_m5_query.py`
- Fixture: seed an in-memory `KuzuStore` from the golden fixture data (using the conftest helper).
- Test each of the five `QueryEngine` methods:
  - `test_find_relevant_repos_returns_seeded_repo` — keyword matches `webforms-solution`.
  - `test_find_relevant_repos_no_match_returns_unknowns` — keyword with no match → `unknowns[{kind: "no-match"}]`.
  - `test_impact_analysis_finds_dependents` — webforms-solution appears in impact analysis of landing-page-ui.
  - `test_impact_analysis_leaf_returns_unknowns` — leaf repo → `unknowns[{kind: "no-match"}]`.
  - `test_dependency_path_found` — path from webforms-solution to landing-page-ui.
  - `test_dependency_path_no_path_returns_unknowns` — no path → `unknowns[{kind: "no-source"}]`.
  - `test_env_diff_same_env_empty_diff` — same env produces empty diff.
  - `test_env_diff_one_empty_env_valid` — one empty env returns valid response.
  - `test_explain_edge_full_evidence` — evidence, deployed_ref, provenance all present.
  - `test_query_result_deployed_refs_never_null` — `deployed_refs` is `{}` not `None`.
  - `test_query_result_unknowns_never_null` — `unknowns` is `[]` not `None`.
- **Acceptance**: all tests pass. `QueryResult` fields match contract.

---

### M7 — GitHub Actions + Octopus Full Scoping + Bitbucket Pipelines

**Goal**: GitHub-hosted repos with GHA workflows produce scoped edges; Octopus scoping handles all 4 dimensions with honest tiebreaking; Bitbucket Pipelines stub passes conformance.

#### M7-1: `tendril/connectors/cicd/github_actions.py`
- `GitHubActionsProvider(CICDProvider)` implementing `id()`, `capabilities()`, `discover_for_repo()`, `read_variable_store()`, `read_provider_identities()`.
- `id()` → `"github-actions"`.
- `capabilities()` → `{intrinsic: True, env_scoping_model: "github-environments", variable_preview: False, deploy_logs: False}`.
- `discover_for_repo()`: scan `repo_ir` file tree for `.github/workflows/*.yml`; parse each with PyYAML; iterate `jobs`; for each job with `environment:` field produce `PipelineBinding(provider="github-actions", roles=["deploy"], env=<env_name>)`; if no environment blocks, produce `PipelineBinding(roles=["build"])` with `cicd-profile-note`.
- `read_variable_store()`: read GitHub Environments variables from fixture or API; map `vars.*` to readable entries, `secrets.*` to masked entries.
- `read_provider_identities()`: extract URLs from environment variable values.
- Add `tendril-plugin.toml` manifest for this provider.

#### M7-2: Update `tendril/connectors/cicd/octopus.py` — full scope priority
- Add private `_scope_matches(var_scope: dict, env: str, role=None, tenant=None, channel=None) -> bool` method.
- Add private `_best_match(candidates: list[VarEntry], env: str) -> VarEntry | list[VarEntry]` method:
  - Priority: env-scoped (1) > role-scoped (2) > tenant-scoped (3) > channel-scoped (4) > unscoped (5).
  - Within same priority: most scope dimensions set wins.
  - Exact tie: return all tied candidates (caller emits `ambiguous-match`).
- Update `read_variable_store()` to use `_best_match()` instead of simple env-name filtering.
- Return `ambiguous=True` metadata when `_best_match()` returns multiple candidates.

#### M7-3: `tendril/connectors/cicd/bitbucket_pipelines.py`
- `BitbucketPipelinesProvider(CICDProvider)` implementing `id()`, `capabilities()`, `discover_for_repo()`.
- `id()` → `"bitbucket-pipelines"`.
- `capabilities()` → `{intrinsic: True, env_scoping_model: "bitbucket-deployments", variable_preview: False, deploy_logs: False}`.
- `discover_for_repo()`: check for `bitbucket-pipelines.yml` in repo tree; parse with PyYAML; scan `pipelines.branches`, `pipelines.pull-requests`, `pipelines.custom`, `pipelines.default` for steps with `deployment:` field; produce `PipelineBinding(provider="bitbucket-pipelines", env=<deployment_value>, roles=["deploy"])`.
- `read_variable_store()`: returns empty `VariableStore` (deferred to future milestone).
- Add `tendril-plugin.toml` manifest.

#### M7-4: GitHub Actions conformance suite
- Create `tests/conformance/github_actions/test_github_actions_conformance.py`.
- Subclass the `CICDProviderConformance` abstract test class (from `tests/conformance/test_cicd_provider.py`).
- Provide fixture data: a repo with `.github/workflows/deploy.yml` containing `environment: staging`.
- Assert: `discover_for_repo()` returns a `PipelineBinding` with `env="staging"` and `roles=["deploy"]`.
- Assert: no-environment workflow degrades gracefully (returns build-only binding, no exception).
- Create `tests/fixtures/conformance/cicd/github_actions/` with fixture YAML files.

#### M7-5: Bitbucket Pipelines conformance suite
- Create `tests/conformance/bitbucket_pipelines/test_bitbucket_pipelines_conformance.py`.
- Subclass `CICDProviderConformance`.
- Provide fixture: a `bitbucket-pipelines.yml` with a `deployment: staging` step.
- Assert: `discover_for_repo()` returns `PipelineBinding(env="staging", roles=["deploy"])`.
- Create `tests/fixtures/conformance/cicd/bitbucket_pipelines/` with fixture YAML.

#### M7-6: M7 integration test
- Create `tests/integration/test_m7_github_actions.py`.
- Wire up a fixture estate where `landing-page-ui` has a `.github/workflows/deploy.yml` with `environment: staging`.
- Run full traversal.
- Assert: `DEPENDS_ON@staging` edge produced with `provenance=injected`, `confidence=high` (or `medium` if env-var resolution degrades).
- Assert: Octopus scoped variable overrides unscoped default in the `prod` environment.

---

## Acceptance Criteria Summary

| Milestone | Gate |
|---|---|
| M6 | `pytest tests/integration/test_golden_fixture.py` passes with zero credentials. LICENSE at root. `.github/workflows/ci.yml` present. |
| M5 | `pytest tests/test_m5_query.py` all pass. `tendril serve --mcp --port 8420` starts. `POST /mcp/find_relevant_repos` with golden fixture data returns correct shape. |
| M7 | `pytest tests/conformance/github_actions/ tests/conformance/bitbucket_pipelines/` all pass. `pytest tests/integration/test_m7_github_actions.py` passes. Octopus scope override verified. |
| All | `pytest tests/` all pass (existing 68 + all new tests). |
