# Research: Production Readiness — Critical Fixes and Live API Mode

**Date**: 2026-06-17
**Feature**: [spec.md](spec.md)

## R1: Environment Filter Fix — Scope and Impact

**Decision**: Fix `_path_matches_env` return value AND note that `store.path()` is dead code from `QueryEngine`.

**Rationale**: Codebase research shows `QueryEngine.dependency_path()` uses direct Cypher queries with `WHERE r.env = $env`, NOT `store.path()`. The `_path_matches_env` function is only called from `KuzuStore.path()` (line 162), which is not called by any `QueryEngine` method. However, `store.path()` is part of the `GraphStore` public API — fixing it is correct even though the current query engine bypasses it. Someone calling `store.path()` directly (a future consumer, a plugin, or a test) would hit the bug.

**Alternatives considered**: (1) Delete `path()` and `_path_matches_env` as dead code — rejected because it's part of the `GraphStore` API. (2) Only document the issue — rejected because it's a one-line fix with zero risk.

## R2: LLM Grounding `to_id` — Exact Field

**Decision**: Change `entry.deployable_id` to `entry.repo_full_name` at `grounding.py:54`.

**Rationale**: `IndexEntry` (defined in `tendril/core/index.py:26-33`) has both `deployable_id` (short slug like `"myrepo"`) and `repo_full_name` (canonical `"github:acme/myrepo"` format). All other edges in the system use `repo_full_name` as `to_id`. The `deployable_id` field is used for index lookups, not for edge identifiers.

**Alternatives considered**: (1) Build a lookup function to resolve `deployable_id` → `repo_full_name` — rejected as unnecessary when `repo_full_name` is already on the same object.

## R3: Plugin Contract Version — Exact Change

**Decision**: Update `tendril/connectors/telemetry/tendril-plugin.toml` line 4 from `"0.1.0"` to `"1.0.0-alpha"`.

**Rationale**: Only one `tendril-plugin.toml` exists in the codebase. The validation in `manifest.py` extracts major version via `split(".")[0]` and requires exact match. `int("0") != int("1")` fails. The TOML file is the one that's wrong (the core `CONTRACT_VERSION = "1.0.0-alpha"` is correct).

**Alternatives considered**: (1) Lower `CONTRACT_VERSION` to `"0.1.0"` — rejected as backwards (the 1.x version is intentional). (2) Make validation more lenient — rejected as it would allow genuinely incompatible plugins.

## R4: Template Marker Detection — Exact Change

**Decision**: Change `not ref.raw_value.startswith("{")` to `"{" not in ref.raw_value` at `traversal.py:339`.

**Rationale**: The current check only catches values that begin with `{`. A URL like `https://{BaseUrl}/api` starts with `h`, passes the filter, and is treated as a resolved static value at rung 1 — it will never match the index. The fix checks for `{` anywhere in the string. This is a strict superset of the old check (all previously rejected values are still rejected) with no false positives because literal `{` in URLs is percent-encoded as `%7B`.

**Alternatives considered**: (1) Use regex `\{[^}]+\}` — more precise but overkill when a simple `in` check has no false positives for URL/config values. (2) Build a template parser — rejected as scope creep.

## R5: Evidence Update — Kuzu Capabilities

**Decision**: Implement read-then-SET sequence to update evidence on existing edges.

**Rationale**: The current `_write_runtime_edge` (cross_validate.py:397-408) checks `count(r)` and returns early if an edge exists. The v0 comment says "Kùzu doesn't support relationship property updates easily" — but this is misleading. Kùzu supports `MATCH (a)-[r]->(b) SET r.evidence = $val` on relationship properties. The implementation: (1) query existing edge to get current evidence JSON, (2) parse and merge with new evidence (deduplicate by `(locator, capability)`), (3) SET the merged evidence back.

**Alternatives considered**: (1) DELETE + re-CREATE the edge — works but loses any other properties that might have been updated. (2) Append-only evidence log in a separate table — rejected as over-engineering for v0.

## R6: Live Mode — Provider Construction Architecture

**Decision**: Add config dataclasses for VCS/CI/CD providers following the existing `LLMConfig`/`DatadogConfig` pattern, then add a provider factory in `_graph_build()`.

**Rationale**: The existing `_graph_build()` (cli/main.py:189) hard-blocks on `--fixture-dir` missing. The live mode branch replaces the fixture-loading blocks with provider construction from config. Each provider's constructor takes simple arguments:
- `GitHubProvider(token)` — needs `GH_TOKEN` or `GH_APP_ID`+`GH_INSTALL_ID`+`GH_PRIVATE_KEY_PATH`
- `BitbucketDCProvider(base_url, token)` — needs `BB_BASE_URL` + `BB_TOKEN`
- `TeamCityProvider(base_url, token)` — needs `TC_BASE_URL` + `TC_TOKEN`
- `OctopusProvider(base_url, api_key, space)` — needs `OCTO_URL` + `OCTO_API_KEY` + `OCTO_SPACE`

Config loading follows the existing `_find_toml()` → env var > TOML > default pattern in `config.py`.

**Alternatives considered**: (1) A single `ProviderRegistry` that auto-discovers from entry points — rejected as premature; manual construction is clearer for v0. (2) CLI `--provider` flags — rejected; env vars are the established pattern.

## R7: BB DC Recursive Tree — API Endpoint

**Decision**: Change from `/rest/api/1.0/projects/{org}/repos/{name}/files/{ref}` to `/rest/api/1.0/projects/{org}/repos/{name}/files?at={ref}`.

**Rationale**: The current code embeds `ref` as a path segment (line 75 in bitbucket_dc.py). The Bitbucket DC REST API `/files` endpoint with `at` as a **query parameter** (not path) returns file paths recursively across all directories. The `/files/{path}` variant lists files within a specific directory. The fix: remove `{ref}` from the URL path, add `at={ref}` as a query parameter alongside `start` and `limit`.

**Alternatives considered**: (1) Use `/browse` endpoint recursively — possible but returns directory entries requiring recursive calls per directory, which is N+1. The `/files?at=` endpoint returns flat paths for all files in one paginated call.

## R8: HTTP Resilience — Shared Utility Architecture

**Decision**: Create `tendril/connectors/_http.py` with a shared `resilient_get()` function wrapping `urllib.request`.

**Rationale**: All four VCS/CI/CD connectors independently implement `_get()` / `_get_json()` methods using raw `urllib.request.urlopen` with no timeout, retry, or error handling. A shared utility avoids duplicating resilience logic across 4+ connectors. The utility provides: configurable timeout (via `urlopen(timeout=...)`), retry with exponential backoff, Retry-After header respect, Content-Type checking, and structured error returns.

**Alternatives considered**: (1) Add retry to each connector individually — rejected as DRY violation. (2) Switch to `requests` or `httpx` — rejected; the codebase is stdlib-only for HTTP, and adding a new dependency is unnecessary when `urllib.request` supports timeout natively. (3) Use `urllib3.Retry` — rejected; brings in a transitive dependency for minimal gain over a simple retry loop.

## R9: MCP Server Tests — Test Architecture

**Decision**: Use `fastapi.testclient.TestClient(app)` with an in-memory Kuzu store seeded from golden fixtures.

**Rationale**: FastAPI's `TestClient` is the standard approach — it creates a synchronous test client that calls the ASGI app directly without a real HTTP server. The test setup overrides the `get_engine` dependency to inject a pre-seeded `QueryEngine`. Tests cover: 5 happy paths (one per endpoint), 1 validation error (bad `min_confidence`), 1 404 (unknown route), 1 503 (store unavailable).

**Alternatives considered**: (1) `httpx.AsyncClient` — more overhead, no advantage for sync tests. (2) Mock the QueryEngine entirely — rejected; integration with real Kuzu store is more valuable.

## R10: Constitution Compliance Verification

All proposed changes verified against constitution principles:
- **I (Plugin-first)**: No core changes for provider-specific logic. HTTP resilience is a shared utility, not core. Config classes are per-provider but follow established patterns.
- **V (Graceful degradation)**: Live mode degrades per-provider. HTTP resilience returns degraded results, never crashes.
- **VII (Non-fabrication)**: No changes introduce fabricated values. Template fix prevents false statics. Evidence merge preserves all data.
- **IX (Read-only, secret-redacting)**: No write paths added. Credential config reads env vars, never persists them.
- **X (Deployed-ref)**: Live mode inherits existing deployed-ref resolution from the traversal engine.
