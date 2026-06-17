# Feature Specification: Production Readiness — Critical Fixes and Live API Mode

**Feature Branch**: `006-production-readiness`

**Created**: 2026-06-15

**Status**: Draft

**Input**: Architecture and code review (review-v2.md) identified 5 critical bugs, major architecture gaps, connector production gaps, test coverage holes, and documentation drift that collectively block Tendril-Graph from running against a real multi-repo estate. This spec covers the path from "working prototype against recorded fixtures" to "first real run against live infrastructure."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Correct Environment Filtering in Graph Queries (Priority: P1)

A platform engineer queries the dependency graph for a specific environment (e.g., "prod") and receives only edges and paths that belong to that environment. Today, environment filtering is broken — `_path_matches_env` always returns `True`, so queries return cross-environment results that mislead impact analysis and change planning.

**Why this priority**: Environment-scoped correctness is the foundational promise of Tendril-Graph. Every downstream query (impact analysis, env-diff, find-relevant-repos) depends on accurate per-environment filtering. Without it, every answer is wrong.

**Independent Test**: Run `dependency_path(from_id, to_id, env="prod")` against a graph containing edges in both "prod" and "staging" — only prod-scoped edges appear in the result.

**Acceptance Scenarios**:

1. **Given** a graph with DEPENDS_ON edges in both "prod" and "staging" environments, **When** a user queries `dependency_path` for env="prod", **Then** only edges where at least one node has `env == "prod"` are returned.
2. **Given** a graph with edges spanning three environments, **When** a user runs `impact_analysis` for env="staging", **Then** the results exclude all edges that belong exclusively to other environments.
3. **Given** no edges exist for env="dev", **When** a user queries for env="dev", **Then** an empty result set is returned with appropriate metadata — not a false-positive set from other environments.

---

### User Story 2 — LLM-Judged Edges Visible in Graph Queries (Priority: P1)

A platform engineer running in hybrid mode sees LLM-contributed edges in impact analysis and find-relevant-repos results. Today, LLM grounding writes `deployable_id` (a short slug) as `to_id` instead of the `provider:org/name` format used by all other edges, making LLM-contributed edges invisible to the query layer.

**Why this priority**: LLM hybrid mode is a key differentiator. If LLM-resolved edges silently disappear from queries, the system gives incomplete answers without any indication that information was lost.

**Independent Test**: Build a graph in hybrid mode where the LLM resolves an ambiguous reference, then query `find_relevant_repos` — the LLM-contributed edge appears in results with `provenance=llm-judged`.

**Acceptance Scenarios**:

1. **Given** an LLM-judged edge is written to the graph, **When** `impact_analysis` is run for the target repo, **Then** the LLM-contributed edge appears in results with correct `from_id` and `to_id` in `provider:org/name` format.
2. **Given** an LLM-judged edge exists, **When** `explain_edge` is called for that edge, **Then** the full evidence chain and LLM reasoning trace are returned.

---

### User Story 3 — Graph Build Against Live Infrastructure (Priority: P1)

A platform engineer runs `tendril graph build` against their actual Bitbucket/TeamCity/Octopus/GitHub estate (not fixture files) and produces a dependency graph. Today, graph build is hard-blocked on `--fixture-dir` — there is no live API mode.

**Why this priority**: This is the blocking gap between "working prototype" and "deployable tool." Without live API mode, Tendril-Graph cannot be used for its intended purpose.

**Independent Test**: With valid read-only credentials configured, run `tendril graph build --anchor bitbucket-dc:acme/webforms-solution --env prod` without `--fixture-dir` — the command completes and writes edges to the graph store.

**Acceptance Scenarios**:

1. **Given** valid VCS and CI/CD credentials are configured via environment variables or config file, **When** `tendril graph build --anchor <repo> --env prod` is run without `--fixture-dir`, **Then** the system connects to live APIs, traverses the dependency graph, and writes edges to the store.
2. **Given** one provider's credentials are missing, **When** graph build runs, **Then** that provider is skipped with a WARNING log naming the provider and reason, the build continues with available providers, the exit code is 0, and the output includes the skipped provider in `metadata.degradation_notices`.
3. **Given** a provider API returns an error (timeout, auth failure, rate limit), **When** graph build encounters the error, **Then** the error is logged at WARNING level, the affected edges are flagged as `unresolved` with the error reason, the build does not crash, and the exit code is 0.
4. **Given** ALL VCS provider credentials are missing in live mode (no `--fixture-dir`), **When** graph build runs, **Then** the system exits immediately with a non-zero exit code and an error message listing the required credentials and referencing `.env.example`.

---

### User Story 4 — Plugin Contract Validation Works for Third-Party Plugins (Priority: P2)

A plugin developer creates a new provider, declares `contract_version` in their `tendril-plugin.toml`, and the plugin validator accepts it. Today, the only existing manifest declares version `"0.1.0"` while the validator expects `"1.0.0-alpha"` — a major-version mismatch that rejects every plugin.

**Why this priority**: The plugin-first architecture is a core design principle. A broken plugin contract validator blocks the extensibility story and any third-party adoption.

**Independent Test**: Load the in-tree Datadog `tendril-plugin.toml` manifest — it passes validation without modification.

**Acceptance Scenarios**:

1. **Given** a `tendril-plugin.toml` with `contract_version = "1.0.0-alpha"`, **When** the plugin validator runs, **Then** it accepts the manifest.
2. **Given** a manifest with a truly incompatible version (e.g., `"2.0.0"`), **When** the validator runs, **Then** it rejects the manifest with a clear error message.

---

### User Story 5 — Accurate Static Value Extraction (Priority: P2)

The traversal engine correctly distinguishes between fully-resolved static values and values that still contain unresolved template substitutions. Today, `_extract_static_values` accepts strings like `https://{BaseUrl}/api` as static because it only checks `startswith("{")`, missing embedded template markers.

**Why this priority**: False static values at rung 1 of the acquisition ladder mean the resolver treats template strings as resolved URLs — these never match the index, silently producing missing edges.

**Independent Test**: Pass a value containing `{BaseUrl}` through static extraction — it is rejected as unresolved, not accepted as a static value.

**Acceptance Scenarios**:

1. **Given** a config value `https://{BaseUrl}/api/v2`, **When** the extractor processes it, **Then** it is classified as a template requiring resolution, not a static value.
2. **Given** a config value `https://api.prod.example.com/v2` (no templates), **When** the extractor processes it, **Then** it is correctly classified as a static value at rung 1.
3. **Given** a config value `{ServiceUrl}` (starts with `{`), **When** the extractor processes it, **Then** it is correctly classified as a template (existing behavior preserved).

---

### User Story 6 — Telemetry Evidence Updates on Re-Runs (Priority: P2)

A platform engineer runs telemetry reconciliation multiple times as their infrastructure evolves, and the evidence on observed edges updates to reflect the latest telemetry data. Today, `_write_runtime_edge` silently discards updated evidence on re-runs after finding an existing edge.

**Why this priority**: Stale telemetry evidence erodes trust. If an operator's second reconciliation run doesn't refresh evidence, the graph's "observed" provenance becomes unreliable.

**Independent Test**: Run reconcile twice with different telemetry fixtures — the edge evidence reflects the second run's data, not the first.

**Acceptance Scenarios**:

1. **Given** an observed edge already exists in the graph from a prior reconciliation, **When** reconciliation runs again with updated telemetry, **Then** the edge's evidence is updated to include the new telemetry data.
2. **Given** an observed edge exists, **When** reconciliation runs and the same evidence is found, **Then** no duplicate evidence entries are created.

---

### User Story 7 — Connector Resilience Against Live APIs (Priority: P2)

VCS and CI/CD connectors handle real-world API conditions (errors, timeouts, rate limits, pagination) without crashing the graph build. Today, VCS HTTP errors crash the run, connectors lack timeouts, and pagination is missing from TeamCity and Octopus list operations.

**Why this priority**: Any real-world run against a non-trivial estate will encounter API errors, large result sets, and rate limits. Without resilience, graph build is unusable in practice.

**Independent Test**: Simulate an HTTP 500 from the Bitbucket DC API during `read_tree` — the connector logs the error and returns a degraded result instead of crashing.

**Acceptance Scenarios**:

1. **Given** a VCS API returns HTTP 500, **When** the connector encounters the error, **Then** it logs the error at WARNING level, marks affected operations as degraded, and does not crash the build.
2. **Given** an API does not respond within the configured timeout (default 30s), **When** the connector times out, **Then** it logs the timeout and degrades gracefully.
3. **Given** a rate limit response (HTTP 429), **When** the connector receives it, **Then** it respects the `Retry-After` header when present, falls back to exponential backoff (1s, 2s, 4s) when absent, and retries up to 3 times.
4. **Given** an API returns a non-JSON response (e.g., HTML error page), **When** the connector receives it, **Then** it treats the response as an error and degrades gracefully.

*Note: Pagination of large result sets (e.g., TeamCity build types, Octopus projects) is covered by FR-011 (Tier 3) and is independent of this resilience work.*

---

### User Story 8 — Bitbucket DC Returns Complete File Trees (Priority: P2)

The Bitbucket Data Center connector returns the full recursive file tree for a repository, not just root-level entries. Today, `read_tree` returns a flat root listing, missing all nested files — which means most config files are invisible to extraction.

**Why this priority**: Bitbucket DC is the primary VCS for the v0 reference target (ASP.NET WebForms solution). A flat file listing misses all nested config files, breaking the extraction pipeline for the core use case.

**Independent Test**: Call `read_tree` on a fixture repository with nested directories — all files at all depths are returned.

**Acceptance Scenarios**:

1. **Given** a repository with files in nested directories (e.g., `src/config/appsettings.prod.json`), **When** `read_tree` is called, **Then** all files at all directory depths are included in the result.
2. **Given** a repository with 500+ files across many directories, **When** `read_tree` is called, **Then** it returns all files (handling pagination of the recursive browse API).

---

### User Story 9 — MCP Server Has Test Coverage (Priority: P3)

The MCP server — the primary interface for coding agents — has automated test coverage using a test client. Today, it has zero tests, meaning any regression in the agent-facing interface goes undetected.

**Why this priority**: The MCP server is how coding agents consume the graph. Untested, any change to the query layer or server could silently break the agent integration.

**Independent Test**: Run the MCP server test suite — all five endpoints return correct response shapes and error codes.

**Acceptance Scenarios**:

1. **Given** the MCP server is running with a seeded graph store, **When** each of the 5 endpoints is called with valid input, **Then** it returns a well-formed response matching the expected schema.
2. **Given** the server receives a request for a non-existent route, **When** the request is processed, **Then** it returns a structured error response (not an HTML 404 page).
3. **Given** the graph store is not initialized, **When** a query endpoint is called, **Then** it returns a 503 with a structured error body.

---

### User Story 10 — Documentation Matches Reality (Priority: P3)

A new user or contributor reads the README and CLAUDE.md and finds instructions, command names, and architecture descriptions that match the actual CLI interface and code layout.

**Why this priority**: Misleading documentation wastes onboarding time and erodes trust. The README quickstart describes commands that don't exist and uses wrong argument syntax.

**Independent Test**: Every command shown in the README quickstart can be run (or has a clear "planned" marker), and CLAUDE.md's package layout description matches the actual directory structure.

**Acceptance Scenarios**:

1. **Given** the README quickstart section, **When** a user reads the CLI commands, **Then** every command either works as documented or is clearly marked as planned/future.
2. **Given** the CLAUDE.md package layout description, **When** compared to the actual directory structure, **Then** the description accurately reflects reality (code lives inside `tendril/` as subpackages).
3. **Given** the README command examples, **When** a user tries them, **Then** argument names and positions match the actual CLI interface.

---

### Edge Cases

- What happens when credentials are configured for some providers but not all? (Graceful degradation — build with available providers, warn about missing ones. VCS is required; CI/CD and telemetry are optional.)
- What happens when ALL VCS credentials are missing in live mode? (Error immediately with a clear message listing required credentials and referencing `.env.example`.)
- What happens when a live API returns truncated data (e.g., GitHub tree API truncation flag)? (Log a warning, flag affected edges as potentially incomplete.)
- What happens when the plugin contract version is updated in a future release? (Semver-compatible versions pass validation; breaking changes require explicit migration.)
- What happens when template markers use non-standard syntax (e.g., `$(Var)` instead of `{Var}`)? (Each extractor handles its platform's template syntax; the core check is for `{...}` patterns in the general case. Template markers inside comments are not a concern — config file parsers strip comments before values reach the extractor.)
- What happens when an observed edge's evidence format doesn't match the expected locator pattern? (Evidence is logged but flagged; the edge is still written with a degradation notice.)
- What happens when Bitbucket DC recursive tree exceeds 10,000 files? (All files are still returned via pagination; a WARNING log is emitted noting potential performance impact.)
- What happens when an LLM-judged edge's target repo is removed on a subsequent re-build? (Normal lifecycle — each graph build replaces the graph; orphaned edges from prior builds do not persist.)
- What happens when a graph build is interrupted (e.g., network failure mid-traversal)? (Partial results are acceptable for v0. The graph store is transactional — committed edges survive, uncommitted edges are lost. No resume mechanism is provided.)
- What happens when an API returns a non-JSON response (e.g., HTML error page)? (Treated as an error; connector degrades gracefully with a WARNING log.)
- What happens when credential environment variables contain empty or whitespace values? (Treated as "not configured" — equivalent to the variable being unset.)

## Requirements *(mandatory)*

### Functional Requirements

**Tier 1 — Correctness Fixes (blocks all real use)**

- **FR-001**: System MUST filter dependency paths by the requested environment. Every DEPENDS_ON edge carries an explicit `env` property; filtering is by exact match on that property. Primary filtering occurs at the query level (Cypher `WHERE r.env = $env`). The secondary path filter (`_path_matches_env`) MUST return `False` — not `True` — when no node or edge in the path row matches the requested environment. This ensures `dependency_path` results contain only edges scoped to the requested environment.
- **FR-002**: System MUST use the canonical repo identifier (in `provider:org/name` format) as `to_id` for LLM-grounded edges, matching the format used by all other edge types. When grounding finds a match in the reverse index, `to_id` MUST be constructed from the matched `IndexEntry`'s canonical identifier, not its `deployable_id` slug. Ungrounded proposals (no index match) are already handled by the existing `grounding-failed` logic and are unaffected by this fix.
- **FR-003**: System MUST set the `contract_version` in all in-tree `tendril-plugin.toml` manifests to `"1.0.0-alpha"`, matching the `CONTRACT_VERSION` constant in `tendril/plugins/base.py`. The existing validation requires major-version match (parsed from the first segment before `.`). Manifests declaring major version 0 (e.g., `"0.1.0"`) will fail validation against the core's major version 1.
- **FR-004**: System MUST reject config values containing unresolved template substitution markers as non-static, regardless of where the marker appears in the string. The general-case check MUST detect `{...}` patterns (any substring matching the regex `\{[^}]+\}`) anywhere in the value, not only at the string start. Platform-specific template syntaxes (e.g., MSBuild `$(Var)`, Ruby `#{var}`) are the responsibility of each extractor and are out of scope for this core fix.
- **FR-005**: System MUST update evidence on existing observed edges during re-runs of telemetry reconciliation, rather than silently discarding new evidence. The merge strategy is **accumulate-and-deduplicate**: new evidence items are appended to the existing evidence list, then deduplicated by `(locator, capability)` tuple, retaining the newest timestamp for each unique evidence item. This aligns with the existing `_deduplicate_edges` pattern in the cross-validator. No evidence history is lost — only exact duplicates are collapsed.

**Tier 2 — Live Infrastructure Support (blocks real-world use)**

- **FR-006**: System MUST support a live API mode for `graph build` that constructs VCS and CI/CD provider instances from configured credentials without requiring `--fixture-dir`. Provider discovery is automatic: for each known provider type, the system checks whether the required credentials are available (via env vars or `tendril.toml`); if yes, the provider is instantiated; if no, it is skipped with a WARNING log. Provider dependency chain: at least one VCS provider is required for any graph build; CI/CD providers require at least one VCS provider to know which repos to process; telemetry is fully independent. If ALL VCS credentials are missing, the system MUST exit with an error listing required credentials and referencing `.env.example`. **Build dependency**: FR-007 (credential config) must be complete before FR-006 can be implemented.
- **FR-007**: System MUST provide a credential configuration mechanism for all supported providers, following the existing resolution pattern: environment variables > `tendril.toml` sections > built-in defaults. VCS/CI/CD credential sections MUST be added to `tendril.toml` schema (currently only LLM and Datadog are covered). Credential loading for Datadog is already implemented and is in scope only for consistency verification. Empty or whitespace-only values in environment variables MUST be treated as "not configured" (equivalent to the variable being unset). On provider initialization, a lightweight validation call (e.g., a read-only API call with `limit=1`) SHOULD be attempted; if it fails, the provider is skipped with a WARNING log indicating whether the credential was invalid or the endpoint was unreachable.
- **FR-008**: System MUST implement recursive file tree retrieval for Bitbucket Data Center, returning files at all directory depths. The current implementation uses the `/files/{ref}` endpoint which returns a flat root-level listing. The fix MUST use the recursive browse API (`/browse?at={ref}` with recursive traversal or equivalent) to return the complete tree. All entries reported by the API are returned; content-type filtering (binary files, etc.) is the extractor's responsibility and out of scope for this fix. If total file count exceeds 10,000, a WARNING log is emitted noting potential performance impact.
- **FR-009**: System MUST add HTTP error handling, configurable timeouts, and rate-limit retry to all VCS and CI/CD connector HTTP methods. Connectors currently use `urllib.request` (standard library) with no timeout or retry logic. Defaults: **30-second connection timeout**, **3 retries** with **exponential backoff** (1s, 2s, 4s base delays). When a `Retry-After` header is present in a 429 response, it MUST be respected (overriding the backoff schedule). On non-JSON response bodies (e.g., HTML error pages), the response MUST be treated as an error and the connector MUST degrade gracefully. Configuration follows the existing pattern: env vars (`TENDRIL_HTTP_TIMEOUT`, `TENDRIL_HTTP_RETRIES`) > `tendril.toml` `[http]` section > built-in defaults. No CLI flags are needed — these are operational settings. FR-009 applies to all HTTP requests including those made during paginated fetches (FR-011).
- **FR-010**: System MUST guarantee consistent response contracts for the MCP server: all five endpoints MUST return JSON bodies conforming to their Pydantic response schemas on success, and MUST return structured error bodies (`{"error": {"code": <int>, "message": <string>}}`) for all error conditions (400 bad request, 404 not found, 503 store unavailable). These contracts MUST be validated by automated tests using a test client, covering both success paths and error paths for all five endpoints.

**Tier 3 — Quality and Trust**

- **FR-011**: System MUST add pagination support to TeamCity `list_pipelines` and Octopus `list_pipelines` to handle large estates.
- **FR-012**: System MUST update the README quickstart to reflect the actual CLI interface (command names, argument syntax, and subcommand structure).
- **FR-013**: System MUST correct the CLAUDE.md package layout description to state that all code lives inside `tendril/` as subpackages.
- **FR-014**: System MUST add test coverage for BFS cycle detection and ReverseIndex operations (URL normalization, www-stripping, multi-candidate returns).
- **FR-015**: System MUST register in-tree providers as `pyproject.toml` entry points so that `tendril providers list` reflects all available providers.

### Key Entities

- **Credential Config**: Per-provider authentication configuration sourced from environment variables or a TOML config file. Key attributes: provider ID, credential type, credential values (never persisted in plaintext), validation status.
- **HTTP Resilience Policy**: Per-connector configuration for timeout duration (default 30s), retry count (default 3), rate-limit backoff strategy (exponential: 1s, 2s, 4s; Retry-After header respected). Applied uniformly across all connector HTTP methods via a shared utility wrapper around `urllib.request`.
- **Plugin Contract Version**: Semver string declared in both `tendril-plugin.toml` manifests and `tendril/plugins/base.py`. Must be consistent across all in-tree providers and validated at plugin load time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All environment-scoped queries return exclusively edges belonging to the requested environment — zero cross-environment leakage in the test suite. New test fixtures with edges in both "prod" and "staging" environments are required to validate this criterion.
- **SC-002**: LLM-judged edges appear in `find_relevant_repos` and `impact_analysis` results with correct `provider:org/name` identifiers — verifiable via `explain_edge` returning the LLM reasoning trace.
- **SC-003a** (automated): `tendril graph build` with fixture providers produces the same edges as the existing golden fixture test — verifiable in CI with zero credentials.
- **SC-003b** (manual): `tendril graph build` completes successfully against live provider APIs with valid credentials, producing at least one DEPENDS_ON edge — without requiring `--fixture-dir`. This is a manual acceptance criterion for first deployment. "At least one edge" is the correct threshold — it proves the live pipeline works end-to-end; completeness is validated by subsequent queries.
- **SC-004**: `tendril graph build` completes with graceful degradation when one or more provider credentials are missing or one provider API returns errors. Observable outcomes: exit code 0, WARNING log lines for each degraded provider, JSON output includes `metadata.degradation_notices` array with entries for each skipped or failed provider.
- **SC-005**: All in-tree `tendril-plugin.toml` manifests pass the plugin contract validator without modification.
- **SC-006**: Template strings containing `{...}` substitution markers are never classified as resolved static values — zero false-positive static values in the test suite.
- **SC-007**: Telemetry reconciliation re-runs update edge evidence — verifiable by running reconcile twice with different fixtures and checking that evidence reflects the second run's data with no duplicates.
- **SC-008**: Bitbucket DC `read_tree` returns files from nested directories — verifiable against a fixture with at least 3 directory levels (sufficient to distinguish flat listing from recursive traversal).
- **SC-009**: MCP server test suite covers all 5 endpoints with both success and error paths — test count increases by at least 10.
- **SC-010**: All existing tests at the start of this work continue to pass — zero regressions.

## Assumptions

- Credentials for live provider APIs will be supplied by the operator via environment variables (existing `GH_TOKEN`, `BB_TOKEN`, `TC_TOKEN`, `OCTO_API_KEY`, etc.) or a `tendril.toml` config file. No interactive credential prompts are needed.
- The `providers add` CLI command described in the README is deferred to future work — this spec covers credential reading from env vars and config files, not an interactive registration flow.
- The MCP server remains a REST/HTTP server for this phase. Converting to the MCP JSON-RPC protocol (stdio/SSE) is deferred to a separate specification. The shared surface between this spec and the future MCP protocol spec is limited to the five endpoint names and their request/response schemas (defined by QueryEngine and Pydantic models), which are unchanged by a transport swap — no conflict risk.
- Bitbucket Cloud VCS provider, full JS/TS extractor, and IaC extractor (Helm, k8s, Terraform, Docker) are out of scope — they are documented as future work in the review.
- The Datadog connector's live API mode is out of scope for this spec — it remains fixture-only, with live mode as future work. However, Datadog credential configuration (FR-007) IS in scope for consistency — the credential loading already exists in `config.py` and only needs verification, not new implementation.
- HTTP resilience (timeouts, retries, error handling) uses Python standard library (`urllib.request`, which all connectors currently use) — no new HTTP client libraries are required. `urllib.request.urlopen` supports the `timeout` parameter natively. Retry and backoff logic will be implemented as a small utility wrapper around the existing `_get()` methods.
- The `.env.example` file exists at the project root and documents all provider credentials with placeholder values.
- Secret redaction patterns will be extended to cover `*connstr*` variants (common in .NET connection strings) as part of the correctness fixes.
- Live mode starts from a clean graph store. Behavior when encountering repos previously indexed from fixtures is not defined — this is out of scope for v0.
- Concurrent reconciliation runs (multiple `tendril telemetry reconcile` processes) are not supported. Kuzu is an embedded (single-process) store. This is documented but not enforced.
- Interrupted graph builds produce partial results — committed edges survive, uncommitted edges are lost. No resume mechanism is provided for v0.
