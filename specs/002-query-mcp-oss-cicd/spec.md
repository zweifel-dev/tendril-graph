# Feature Specification: Query Layer, MCP Server, OSS Hygiene, and CI/CD Breadth (M5–M7)

**Feature Branch**: `002-query-mcp-oss-cicd`

**Created**: 2026-06-15

**Status**: Draft

**Input**: User description: "I am building out a cross repo dependency graph of a multi repo estate from source, ci/cd configs, telemetry, and serving it coding agents. Read through the @CLAUDE.md @README.md then the files in @specs/000-initial-plan/ This will give you the baseline. For this spec I want M5, M6, and M7 to be completed which you can find more details in the @specs/000-initial-plan/implementation-plan.md and @review.md"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - AI Agent Queries the Dependency Graph (Priority: P1)

A coding agent is asked to understand which repositories are relevant to a task such as "checkout flow." The agent sends a single request to the dependency graph service and receives a ranked list of repositories, each annotated with confidence, provenance, the deployed code revision, and any gaps the system could not determine. The agent uses this to decide which repos to focus its analysis on.

**Why this priority**: This is the primary use case for the entire system — serving coding agents. Without a queryable interface, the graph built in M0–M4 is inaccessible to its main consumer.

**Independent Test**: Can be tested by seeding the graph from the golden fixture, sending a query request, and verifying the response contains the expected repos, confidence levels, and unknowns list.

**Acceptance Scenarios**:

1. **Given** a dependency graph has been built from the fixture estate, **When** an agent queries for repos relevant to "checkout", **Then** the response includes the expected repository identifiers, each with a confidence value, a provenance tag, a deployed revision reference, and an explicit unknowns list (which may be empty).
2. **Given** the graph contains an edge with unresolved candidates, **When** an agent queries, **Then** those unresolved candidates appear in the `unknowns` field rather than being silently omitted.
3. **Given** no matching repos exist, **When** an agent queries, **Then** the response returns an empty results list with an explicit unknowns entry indicating no repositories matched, rather than an error.

---

### User Story 2 - Developer Performs Impact Analysis via CLI (Priority: P2)

A developer plans to change a shared service and wants to know which other repositories depend on it in production. They run a command-line query and receive a list of downstream dependents, ordered by confidence, with provenance and deployed revision for each.

**Why this priority**: Human operators need the same graph data as agents. The CLI surface is the primary human entry point and validates that the query layer works end-to-end before agent integration.

**Independent Test**: Can be tested by running the CLI query command against the fixture graph and asserting the correct dependents appear in the output with confidence and provenance metadata.

**Acceptance Scenarios**:

1. **Given** a seeded graph where repo A depends on repo B, **When** a developer runs an impact analysis for repo B, **Then** repo A appears in the results with its confidence, provenance, and deployed revision.
2. **Given** the developer requests an explanation for a specific dependency edge, **Then** the full evidence chain for that edge is returned, including all source file locations and variable store references that contributed to it.
3. **Given** the developer compares dependencies for the same repo across two environments, **Then** the response shows which dependencies differ between those environments.

---

### User Story 3 - Open Source Contributor Reproduces the First Edge (Priority: P3)

A new contributor clones the repository and wants to verify the system works end-to-end. They install dependencies and run the test suite. No external API credentials are required. The tests pass, including a test that proves the full pipeline from fixture input to `DEPENDS_ON` edge output.

**Why this priority**: Reproducibility without credentials is the gate for open-source participation. Without it, contributors cannot verify their changes, and CI cannot run in a public context.

**Independent Test**: Can be tested with a fresh checkout and a single test run command that exercises the complete pipeline against synthetic fixture data only.

**Acceptance Scenarios**:

1. **Given** a fresh repository checkout with no external credentials configured, **When** the contributor installs dependencies and runs the test suite, **Then** all tests pass including the golden-fixture integration test.
2. **Given** the golden fixture represents a 3-repo estate, **When** the integration test runs, **Then** at least one `DEPENDS_ON` edge is produced with provenance, confidence, deployed revision, and evidence chain matching the expected output.
3. **Given** a public CI pipeline is configured, **When** a pull request is submitted, **Then** the test suite runs automatically and reports pass/fail without any manual credential setup.

---

### User Story 4 - GitHub Actions Repository Gets Correct Edge Attribution (Priority: P4)

A development team uses GitHub Actions for CI with environment-scoped deployments (`staging`, `prod`). Tendril-Graph correctly identifies the dependency edges for that repository and scopes them to the right environment, just as it does for TeamCity + Octopus estates.

**Why this priority**: GitHub Actions is the most widely used CI platform. Without this connector, the system cannot map GitHub-hosted repositories, which are present in the reference estate (landing-page-ui and landing-page-api are GitHub-hosted).

**Independent Test**: Can be tested using a fixture with a `.github/workflows/deploy.yml` file containing an `environment: staging` block, and asserting that the resulting edge is scoped to `staging`.

**Acceptance Scenarios**:

1. **Given** a repository contains GitHub Actions workflow files that reference a deployment environment named `staging`, **When** the attribution step runs, **Then** a `DEPENDS_ON@staging` edge is produced for that repository.
2. **Given** a repository uses both GitHub Actions for CI and Octopus Deploy for deployment, **When** attribution runs, **Then** the system correctly represents the chained CI/deploy ownership without conflating the two.
3. **Given** an Octopus Deploy variable is defined at both the project level and with an environment-specific scope, **When** variable resolution runs for that environment, **Then** the environment-scoped value takes precedence over the project default.

---

### Edge Cases

- What happens when a coding agent queries for repos that have stale deployment data (deployed revision no longer resolvable)?
- How does the system handle a query for an environment that exists in the fixture but has no dependency edges?
- What happens when the MCP server receives a request with an unknown query operation?
- What happens when two Octopus variables share the same name but have different environment scopes — does the resolver select the most specific match or return both?
- What if a GitHub Actions workflow file exists but defines no `environment:` blocks — does the system degrade gracefully rather than fail?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-000**: `find_relevant_repos` MUST operate in two layers: (1) a deterministic structured mode that seeds from repos whose IDs or names match task keywords and expands via BFS along `DEPENDS_ON` edges up to a configurable hop limit (default: 3 hops; configurable via the `max_hops` input parameter) — this path MUST work without any LLM; (2) an optional LLM-assisted layer, active only when an `LLMProvider` plugin is registered in the plugin registry, that scores ambiguous or unmatched candidates for relevance and flags LLM-contributed results with `provenance=llm-judged` and `confidence=low`. The structured path is always the primary fast path. If the keyword matches a repo but BFS finds no outbound edges, the seed repo is returned in results with `hop_depth=0`. A `min_confidence` input parameter (default: `low`) filters results before return.
- **FR-001**: The system MUST expose all five dependency graph query operations (find relevant repos, impact analysis, dependency path, environment diff, edge explanation) as HTTP JSON POST endpoints (`POST /mcp/<tool>`). Each endpoint must accept and return structured JSON. The endpoint design MUST be forward-compatible with full MCP protocol framing (tool discovery manifest, JSON-RPC envelope) so that adding MCP compliance later is additive, not a rewrite.
- **FR-002**: Every query response MUST include, for each result: confidence level (`high`, `medium`, `low`), provenance (`declared`, `injected`, `observed`), the deployed code revision for each repository referenced, and an explicit unknowns list.
- **FR-003**: The unknowns list MUST be present on every `200` response and MUST distinguish between "no dependency" and "could not determine." The following HTTP status codes apply: `400 Bad Request` for malformed input (missing required fields, invalid parameter values); `404 Not Found` for requests to unrecognized tool endpoints (`/mcp/<unknown_tool>`); `503 Service Unavailable` when the graph store is uninitialized or unreachable at request time; `500 Internal Server Error` for unexpected server failures. All error responses use the `Error Response` schema (see Key Entities). Data-level outcomes (no matching repos, graph empty, unresolvable reference, `dependency_path` with no path between repos, `impact_analysis` with no inbound edges for a repo) MUST return `200` with an empty results list and at least one `unknowns` entry with the appropriate `kind` and `description`, so agents can distinguish a retryable failure from an absence of data.
- **FR-004**: The system MUST expose all five query operations via the command-line interface, producing JSON output (same schema as the HTTP endpoint response) that can be piped or parsed by scripts. Each operation is a distinct subcommand: `tendril query find-relevant-repos`, `tendril query impact`, `tendril query path`, `tendril query env-diff`, `tendril query explain-edge`. Each subcommand accepts the same parameters as its HTTP counterpart as CLI flags.
- **FR-005**: The system MUST include a complete synthetic fixture set representing a 3-repository estate (one Bitbucket DC repo, two GitHub repos) such that the full pipeline can be exercised with no external credentials.
- **FR-006**: The project MUST include a public CI workflow that runs the full test suite automatically on every commit and pull request.
- **FR-007**: The system MUST include an Apache-2.0 license file at the project root.
- **FR-008**: The system MUST detect and attribute dependencies for repositories using GitHub Actions workflows by reading `.github/workflows/*.yml`. The `jobs.<job_id>.environment` YAML field (both string form and object form with a `name` key) identifies deployment environments. Each job with an `environment:` field produces one `PipelineBinding` with `roles=[deploy]` for that environment. If a workflow file exists but no jobs define `environment:` blocks, the connector MUST degrade gracefully: produce `PipelineBinding` records with `roles=[build]` and no environment scope, emit a `cicd-profile-note` flag on the profile, and continue without error. GitHub Actions `vars.*` values MUST be read as plain string values; `secrets.*` MUST be recorded as name-only with `is_secret=True` and `value=None`.
- **FR-009**: When GitHub Actions is used for build and Octopus Deploy is used for deployment (detected via deploy-step signatures in `data/deploy_step_signatures.yaml`), the CI/CD profile MUST record `build_owner: {provider_id: "github-actions", confidence, evidence[]}` and `deploy_owner: {provider_id: "octopus", confidence, evidence[]}` as separate, distinct fields. The two roles MUST NOT be collapsed into a single provider entry. Deploy-time variable resolution routes to the deploy owner's store; build-time-only tokens route to the build owner's store.
- **FR-010**: Octopus Deploy variable resolution MUST implement the full scope priority across all four scope dimensions: environment, role, tenant, channel. Priority order (highest to lowest): environment-scoped > role-scoped > tenant-scoped > channel-scoped > unscoped. Within the same priority level, the variable with the most scope dimensions set wins. When two variables have an identical priority level and the same number of scope dimensions set (exact tie), the system MUST NOT auto-select one — both must be emitted as candidates with `kind=ambiguous-match` in the unknowns list, and the edge flagged `ambiguous=True`.
- **FR-011**: The system MUST include a Bitbucket Pipelines connector stub that detects `bitbucket-pipelines.yml` and produces `PipelineBinding` records by parsing the `deployment:` field on pipeline steps (under `pipelines.branches`, `pipelines.pull-requests`, `pipelines.custom`, and `pipelines.default`) as the environment identifier. The stub is sufficient to pass the `CICDProvider` conformance suite (implementing `id()`, `capabilities()`, and `discover_for_repo()` against fixture data); full variable store reads are deferred.
- **FR-012**: The golden fixture integration test MUST assert the expected `DEPENDS_ON` edge output (from_id, to_id, env, provenance, confidence, deployed_ref, evidence chain) against the synthetic fixture.
- **FR-013**: The `impact_analysis` operation MUST return an empty results list (not an error) when the target repository has no inbound `DEPENDS_ON` edges in the specified environment. The `unknowns` list MUST contain an entry with `kind=no-match` and a description indicating that no repositories were found to depend on the target.
- **FR-014**: The `dependency_path` operation MUST return an empty results list (not an error) when no path exists between the specified source and target repositories. The `unknowns` list MUST contain an entry with `kind=no-source` and a description indicating no path was found.
- **FR-015**: The `env_diff` operation MUST return a valid response when one or both of the specified environments have no dependency edges. Empty edge sets are valid input; the diff result is an empty change set with no unknowns unless specific resolution failures occurred.

### Key Entities

- **QueryResult**: Represents the response to any query operation. Top-level fields: `operation` (string, the tool name), `env` (string), `results` (array, may be empty), `confidence` (string — weakest link across all results: `high` > `medium` > `low`; if any result is `low` the response-level value is `low`), `provenance` (string — most conservative across all results, ordered least-to-most trustworthy: `declared` > `injected` > `observed` > `llm-judged`; if any result is `llm-judged` the response-level value is `llm-judged`), `deployed_refs` (object mapping repo_id string to SHA string; always present, never null; empty object `{}` when no deployment records exist), `unknowns` (array, always present, never null; empty array `[]` when nothing is unresolved), `metadata` (object, optional, always present as `{}`). Each entry in `results` must include at minimum: `repo_id` (string), `confidence` (string), `provenance` (string), `deployed_ref` (string or null if unavailable for that specific repo). Additional per-operation fields are additive.

- **Unknowns Entry**: Each entry in the `unknowns` array must include: `kind` (string enum — one of `unresolved-ref`, `unresolved-secret`, `no-source`, `stale-data`, `ambiguous-match`, `no-match`), `description` (string, human-readable explanation). Optional fields: `repo_id` (string), `token` (string, the variable or reference that could not be resolved), `candidates` (array of repo_id strings, for `ambiguous-match` kind only).

- **Error Response**: Returned on HTTP `4xx`/`5xx` responses. Required fields: `error` (object containing `code` (integer, mirrors the HTTP status code) and `message` (string, human-readable description)). No `QueryResult` fields are present on error responses.

- **MCP Tool**: An HTTP-callable endpoint (`POST /mcp/<tool_name>`) that accepts a flat JSON body with tool-specific input parameters and returns a `QueryResult`. The flat JSON structure (no JSON-RPC envelope) is intentional: full MCP protocol framing (tool discovery manifest, JSON-RPC 2.0 envelope) can be added as a separate `GET /mcp` manifest endpoint and wrapper layer later without changing existing endpoint schemas.

- **Golden Fixture**: A self-contained, credential-free set of synthetic provider responses representing the reference 3-repo estate, used to reproduce the first `DEPENDS_ON` edge in any environment. New fixtures to create for M6: `vcs/bitbucket_dc/` (repo listing, webforms-solution tree and key file contents), `vcs/github/` (landing-page-ui and landing-page-api trees and file contents), `cicd/teamcity/` (build types, VCS roots, parameters), `expected/depends_on_prod.json` (the canonical expected output edge). Existing M4 fixtures that can be reused: `cicd/octopus/deployments_Projects-1_prod.json`, `release_Releases-50.json`, `variables_Projects-1.json`.

- **GitHubActionsProvider**: A CI/CD provider that reads GitHub Actions workflow files at `.github/workflows/*.yml`, detects the `jobs.<job_id>.environment` field (accepting both string form `environment: staging` and object form `environment: {name: staging, url: ...}`), and produces one `PipelineBinding` per job-environment pair. Each job references at most one environment; multiple jobs in the same workflow referencing different environments each produce their own binding.

- **Expected Edge File**: A machine-readable artifact (`tests/fixtures/golden/expected/depends_on_prod.json`) that records the canonical expected output for the golden fixture, used for regression testing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A coding agent discovers which repositories are relevant to a task in a single MCP tool call, with results including confidence, provenance, deployed revision, and unknowns on every response.
- **SC-002**: All five query operations return complete, well-formed responses — the fields `operation`, `env`, `results`, `confidence`, `provenance`, `deployed_refs`, `unknowns`, and `metadata` are always present on every `200` response. `deployed_refs` is an empty object `{}` (never `null`) when no deployment records exist. `unknowns` is an empty array `[]` (never `null`) when nothing is unresolved.
- **SC-003**: A contributor running Python 3.12 on any major operating system (Linux, macOS, Windows) performs a fresh checkout with no external credentials configured, installs dependencies with `pip install -e ".[dev]"`, and runs `pytest tests/` to a green result, including the golden-fixture integration test proving the expected `DEPENDS_ON` edge.
- **SC-004**: The public CI pipeline (GitHub Actions, targeting pushes and pull requests to `main`) runs and reports pass/fail on every pull request without manual intervention or credential configuration.
- **SC-005**: A repository with a `.github/workflows/deploy.yml` containing `environment: staging` on a deployment job produces a `DEPENDS_ON@staging` edge with `provenance=injected` and `confidence=high` when variables are resolved from GitHub Environments `vars.*`. If only unscoped repository variables are available, confidence is `medium`.
- **SC-006**: A fixture containing Octopus variable `LandingPageUrl` defined twice — once with no scope (value: `https://default.example.com`) and once with `Environment=Environments-1` scope (value: `https://d-ui.prod.example.com`) — produces `https://d-ui.prod.example.com` as the resolved value when queried for the environment that maps to `Environments-1`, demonstrating environment scope overriding project default.

## Clarifications

### Session 2026-06-15

- Q: Should the MCP server implement the full official MCP spec (JSON-RPC, tool discovery, SSE/stdio) or simpler HTTP JSON POST endpoints? → A: HTTP JSON POST endpoints now, but designed so that adding full MCP framing (tool discovery manifest, JSON-RPC envelope) is additive and does not require rewriting existing endpoints.
- Q: How should `find_relevant_repos` determine which repos are relevant to a task description? → A: Deterministic structured mode first — keyword match on repo IDs/names seeds the starting set, then BFS expands along `DEPENDS_ON` edges up to a configurable hop limit. When an LLM provider is configured, the LLM acts as a secondary relevance scorer for unmatched or ambiguous candidates. The structured path must always work without LLM.
- Q: How should the server signal failures — HTTP error codes, always-200 with error in body, or a hybrid? → A: HTTP `4xx`/`5xx` for protocol and server errors; `200` with empty results list and an `unknowns` entry explaining the reason for data-level outcomes (no match, graph empty, unresolvable). Agents can distinguish "retry" from "no data exists."

## Assumptions

- M0–M4 are complete and all 68 tests pass; the Kùzu graph store already contains at least one `DEPENDS_ON` edge from the reference fixture estate.
- The synthetic golden fixture covers the reference estate (ASP.NET WebForms + Angular, built in TeamCity, deployed via Octopus, stored in Bitbucket DC + GitHub) and already exists in partial form from M4 test fixtures.
- The MCP server does not need to implement authentication or access control in this phase; that is deferred to a dedicated security hardening milestone after M7. Until then, the server is expected to run in a trusted internal network context only and MUST NOT be exposed to untrusted networks without an external auth layer.
- The Bitbucket Pipelines connector in M7 needs only to pass its conformance suite; full variable resolution for Bitbucket Pipelines deployments is deferred.
- The golden fixture uses anonymized but structurally realistic data; no proprietary or real customer data is included.
- The CI workflow targets the main branch and pull requests against main, running on a standard hosted runner with no self-hosted or private infrastructure.
- The LLM hybrid mode (M9) is not required for any of these milestones; all queries operate in deterministic structured mode. No latency or throughput SLA is defined for v0 — the query layer targets interactive use against small-to-mid estates (tens to hundreds of nodes) and relies on the embedded graph store's native query performance. A formal latency SLA is deferred to a future milestone once scale requirements are validated against a real estate.
- The Kùzu graph schema written by M0–M4 (node types: `Repo`, `Deployable`, `Environment`, `DeployedRef`; edge type: `DEPENDS_ON` with fields `env`, `provenance`, `confidence`, `deployed_ref`, `evidence`, `ambiguous`, `stale`) is the schema the M5 query engine reads against. Any schema changes from M0–M4 are a breaking dependency for M5.
