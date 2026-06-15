# Research: Query Layer, MCP Server, OSS Hygiene, CI/CD Breadth (M5–M7)

**Date**: 2026-06-15
**Feature**: 002-query-mcp-oss-cicd

---

## Decision 1: MCP Wire Protocol for v0

**Decision**: HTTP JSON POST endpoints (`POST /mcp/<tool>`) with flat request/response bodies. No JSON-RPC envelope in v0.

**Rationale**: The review.md and spec clarification session both settled on this. FastAPI handles routing, Pydantic validates input. The endpoint URL structure (`/mcp/<tool_name>`) and flat JSON body are forward-compatible: a later `/mcp` manifest endpoint can return a tool-discovery JSON that lists these same paths, and a thin JSON-RPC wrapper can envelope them — neither change requires modifying the existing endpoint implementations.

**Alternatives considered**: Full MCP spec (JSON-RPC 2.0 + SSE/stdio transport) — deferred; the official MCP SDK adds setup complexity and the primary v0 consumer is a test client, not a production agent fleet.

---

## Decision 2: Kùzu Query Patterns

**Decision**: Use `KuzuStore.neighbors()` (already implemented, single-hop with env/confidence filters) and `KuzuStore.path()` (already implemented, uses `shortestPath()` with env-filter applied in Python) for the query engine. Both are already declared in the `GraphStore` ABC and implemented on `KuzuStore`. Direct multi-hop Kùzu Cypher (`*1..N`) is a fallback path to verify experimentally; if it doesn't support inline property filters, use iterative `neighbors()` calls.

**Rationale**: Kùzu supports variable-length relationship patterns `[:DEPENDS_ON*1..N]` for BFS, and `shortestPath` or `allShortestPaths` for path queries. The existing `KuzuStore.query()` method accepts parameterized Cypher strings and returns rows. The `GraphStore` ABC from `tendril/plugins/base.py` also declares `neighbors()` and `path()` stubs — these should be implemented on `KuzuStore` for clean separation, then called by the query engine.

**Alternatives considered**: Building a Python BFS over raw `upsert_node`/`upsert_edge` calls — rejected because it bypasses the graph store's native traversal and duplicates logic that already lives in M4's traversal engine.

**Key query patterns**:

```cypher
-- find_relevant_repos: BFS up to N hops from seed repos
MATCH (seed:Deployable)-[:DEPENDS_ON*0..3]->(r:Deployable)
WHERE seed.id IN $seed_ids AND r.env = $env
RETURN DISTINCT r.id, r.confidence, r.provenance

-- impact_analysis: reverse BFS
MATCH (a:Deployable)-[:DEPENDS_ON*1..5]->(b:Deployable {id: $repo_id})
WHERE a.env = $env
RETURN DISTINCT a.id

-- dependency_path: shortest path
MATCH p = shortestPath((a:Deployable {id: $from_id})-[:DEPENDS_ON*1..10]->(b:Deployable {id: $to_id}))
RETURN p

-- env_diff: two separate MATCH clauses, diff in Python
MATCH (a:Deployable)-[e:DEPENDS_ON]->(b:Deployable)
WHERE e.env = $env_a
RETURN a.id, b.id, e.confidence, e.provenance

-- explain_edge: specific edge detail
MATCH (a:Deployable {id: $from_id})-[e:DEPENDS_ON]->(b:Deployable {id: $to_id})
WHERE e.env = $env
RETURN e
```

---

## Decision 3: FastAPI Dependency Injection for the Query Engine

**Decision**: Use FastAPI's `Depends()` pattern to inject a `QueryEngine` instance per request from a module-level singleton initialized at startup with the configured db path.

**Rationale**: Simple, stateless-per-request design. The `KuzuStore` is initialized once at server startup via a lifespan context manager (`@asynccontextmanager`). All five endpoints share the same store instance. Thread safety is not a concern for v0 (single-worker Uvicorn, no concurrent writes).

**Alternatives considered**: Reinitializing the store per request — rejected, Kùzu file-based stores have a startup cost; Async ORM patterns — overkill for v0.

---

## Decision 4: Golden Fixture Structure

**Decision**: The golden fixture reuses existing test fixtures from `tests/fixtures/` (conformance fixtures already cover the 3-repo estate), organized under `tests/fixtures/golden/` with a new `expected/` subdirectory containing the canonical output edge JSON.

**Existing fixtures that can be reused or copied**:
- `tests/fixtures/vcs/bitbucket_dc/` — repos.json, webforms-solution_tree.json, webforms-solution_files.json ✓
- `tests/fixtures/vcs/github/` — repos.json, landing-page-ui_tree.json, landing-page-ui_files.json, landing-page-api_tree.json, landing-page-api_files.json ✓
- `tests/fixtures/cicd/octopus/` — deployments_Projects-1_prod.json, release_Releases-50.json, variables_Projects-1.json, variable_preview.json, environments.json, projects.json ✓
- `tests/fixtures/cicd/teamcity/` — build_types.json, parameters.json, server.json, vcs_roots.json ✓

**New files to create for M6**:
- `tests/fixtures/golden/expected/depends_on_prod.json` — canonical edge output (from_id, to_id, env, provenance, confidence, deployed_ref, evidence keys)

**Approach**: Create `tests/fixtures/golden/` as a restructured view pointing at the same data, implemented as a conftest.py helper that reads from the existing fixture paths. This avoids duplicating the JSON files and keeps a single source of truth.

---

## Decision 5: GitHub Actions YAML Parsing

**Decision**: Use Python's built-in `yaml` module (PyYAML, already likely installed) to parse workflow files. No dedicated GitHub Actions YAML library needed for v0.

**Key YAML paths to read**:
- `jobs.<job_id>.environment` — string or `{name: ..., url: ...}` object
- `jobs.<job_id>.steps[].uses` — scan for OctopusDeploy/* (deploy-step chaining signal)
- `env:` blocks at job or workflow level — for variable extraction

**Graceful degrade**: Any workflow file that fails YAML parsing (invalid syntax) emits a `cicd-profile-note` and is skipped — does not fail the run.

---

## Decision 6: Octopus Scope Priority Algorithm

**Decision**: Implement `_scope_matches()` and `_best_match()` in `OctopusProvider` as specified in review.md. The tiebreaker is: emit both as `ambiguous-match` candidates (per spec FR-010 and constitution principle VII).

**Full priority order**: environment-scoped (1) > role-scoped (2) > tenant-scoped (3) > channel-scoped (4) > unscoped (5). Within same priority: most scope dimensions set wins. Exact tie: emit all as candidates with `ambiguous=True`.

**Variable scope matching rule**: A variable matches if all specified scope dimensions match the query AND no dimension is explicitly set to a different value. Unscoped (empty scope) always matches but at lowest priority.

---

## Decision 7: Build Order

**Decision**: M6 → M5 → M7, as specified in review.md.

**Rationale**: 
- M6 first: golden fixtures and CI workflow enable all subsequent tests to run against fixture data
- M5 second: query engine tests need the golden fixture as seed data  
- M7 third: GitHub Actions and Bitbucket Pipelines extend the conformance suite independently

---

## Resolved NEEDS CLARIFICATION Items

All items from Technical Context resolved. No outstanding unknowns before Phase 1.
