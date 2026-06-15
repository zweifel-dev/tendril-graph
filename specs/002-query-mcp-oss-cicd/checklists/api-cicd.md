# API & CI/CD Requirements Quality Checklist: Query Layer, MCP Server, OSS Hygiene, and CI/CD Breadth (M5–M7)

**Purpose**: Validate that API contract and CI/CD provider requirements are complete, clear, and measurable before and after planning. Living checklist — usable as a pre-planning spec gate and as a post-plan traceability review.
**Created**: 2026-06-15
**Feature**: [spec.md](../spec.md)
**Focus**: API contract quality first (QueryResult schema, error responses, MCP forward-compat, LLM conditional path), then CI/CD provider requirements quality (GitHub Actions, Octopus scoping, Bitbucket Pipelines).

---

## Requirement Completeness — API Contract

- [x] CHK001 - Is the complete field schema for `QueryResult` (field names, types, cardinality, and null/empty semantics for each field) fully specified, beyond the high-level prose description? [Completeness, Spec §Key Entities, Gap]
  > **Resolved**: Key Entities now specifies all top-level QueryResult fields with types, the `deployed_refs` empty-object-not-null rule, the `unknowns` empty-array-not-null rule, and the minimum per-result entry fields (`repo_id`, `confidence`, `provenance`, `deployed_ref`).

- [x] CHK002 - Is the schema for each entry in the `unknowns` list defined — specifically what fields each entry must contain (e.g., reason code, affected repo, suggested action) and which are required vs optional? [Completeness, Gap]
  > **Resolved**: Key Entities defines the Unknowns Entry schema: required `kind` (enum of `unresolved-ref`, `unresolved-secret`, `no-source`, `stale-data`, `ambiguous-match`, `no-match`) and `description`; optional `repo_id`, `token`, `candidates`.

- [x] CHK003 - Is the behavior of the `deployed_refs` map specified for repositories that have no deployment records in the fixture (omit the key, include with null value, include with empty string)? [Completeness, Gap]
  > **Resolved**: Key Entities and SC-002 now specify `deployed_refs` is always an empty object `{}`, never null or absent.

- [x] CHK004 - Is the "configurable hop limit" for `find_relevant_repos` BFS documented with a specified default value in the requirements? [Completeness, Spec §FR-000]
  > **Resolved**: FR-000 now specifies default of 3 hops via the `max_hops` input parameter.

- [x] CHK005 - Are the input parameter schemas (required fields, types, and valid values) defined for all five query endpoints (`POST /mcp/<tool>`)? [Completeness, Gap]
  > **Resolved**: FR-000 specifies `max_hops` and `min_confidence` for `find_relevant_repos`. FR-004 specifies CLI subcommand names and that each subcommand accepts the same parameters as its HTTP counterpart. Full per-operation parameter tables are deferred to the plan; the pattern is established.

- [x] CHK006 - Is the "structured error body" returned on `4xx`/`5xx` responses defined with its required fields? [Completeness, Spec §FR-003]
  > **Resolved**: Key Entities defines the Error Response schema: `error` object with `code` (integer) and `message` (string). FR-003 lists the specific HTTP codes (400, 404, 500, 503) and their triggers.

- [x] CHK007 - Are the conditions under which the LLM-assisted relevance layer activates explicitly specified (e.g., LLM provider registered in config, specific environment variable set)? [Completeness, Spec §FR-000]
  > **Resolved**: FR-000 now specifies activation condition: "when an `LLMProvider` plugin is registered in the plugin registry."

- [x] CHK008 - Is the provenance value assigned to LLM-contributed query results specified (e.g., `llm-judged` or a new provenance tag)? [Completeness, Gap]
  > **Resolved**: FR-000 now specifies `provenance=llm-judged` and `confidence=low` for LLM-contributed results, consistent with PRD FR-25 and the existing provenance taxonomy.

- [x] CHK009 - Are "forward-compatible with full MCP protocol framing" constraints described concretely — is it specified what endpoint design constraints guarantee additive MCP compliance (e.g., no opaque wrappers, response must be JSON-serializable at top level)? [Completeness, Spec §FR-001]
  > **Resolved**: Key Entities (MCP Tool entry) now specifies that the flat JSON structure is intentional, that full MCP framing can be added as a separate manifest endpoint and wrapper layer, and that existing endpoint schemas are not changed by that addition.

---

## Requirement Clarity — API Contract

- [x] CHK010 - Is "weakest link" for the overall `confidence` aggregation rule defined precisely (e.g., if any result is `low`, the response-level confidence is `low`)? [Clarity, Spec §Key Entities]
  > **Resolved**: Key Entities defines the ordering `high > medium > low` with the rule "if any result is `low` the response-level value is `low`."

- [x] CHK011 - Is "most conservative provenance" for the response-level `provenance` field defined with an explicit ordering (e.g., `declared` > `injected` > `observed` > `llm-judged` from most to least conservative)? [Clarity, Spec §Key Entities]
  > **Resolved**: Key Entities now defines the ordering least-to-most trustworthy: `declared > injected > observed > llm-judged`, with the rule "if any result is `llm-judged` the response-level value is `llm-judged`."

- [x] CHK012 - Is "ordered by confidence" in impact analysis results defined as a specific sort order (e.g., descending — `high` first)? [Clarity, Spec §User Story 2]
  > **Resolved**: User Story 2 states "ordered by confidence" — the confidence ordering is now defined in Key Entities (`high > medium > low`), making descending sort unambiguous. No separate spec edit needed; the definition in Key Entities resolves this.

- [x] CHK013 - Is "structured output" for the CLI (FR-004) specified as JSON, and is it documented whether the CLI schema is identical to or a subset of the HTTP endpoint response schema? [Clarity, Spec §FR-004]
  > **Resolved**: FR-004 now explicitly states "JSON output (same schema as the HTTP endpoint response)" and lists the five subcommand names.

---

## Requirement Completeness — CI/CD Providers

- [x] CHK014 - Are the specific YAML file locations and fields that `GitHubActionsProvider` must read defined (e.g., `.github/workflows/*.yml`, `jobs.<name>.environment.name`, `jobs.<name>.environment` as string)? [Completeness, Spec §FR-008]
  > **Resolved**: FR-008 now specifies `.github/workflows/*.yml`, the `jobs.<job_id>.environment` field, both string and object forms, and the one-binding-per-job rule.

- [x] CHK015 - Is the behavior when a GitHub Actions workflow file is present but contains no `environment:` blocks explicitly specified (degrade gracefully, emit warning, produce no pipeline binding)? [Completeness, Spec §Edge Cases]
  > **Resolved**: FR-008 now specifies: produce `PipelineBinding` records with `roles=[build]` and no environment scope, emit a `cicd-profile-note` flag, continue without error.

- [x] CHK016 - Is "correctly represent the chained CI/deploy ownership" (FR-009) defined with specifics — what fields or structure in the output distinguishes build owner from deploy owner? [Completeness, Spec §FR-009]
  > **Resolved**: FR-009 now specifies the CI/CD profile must contain separate `build_owner` and `deploy_owner` fields each with `provider_id`, `confidence`, and `evidence[]`. Variable routing rules are also specified.

- [x] CHK017 - Does the Octopus scope priority specification cover all four scope dimensions (environment, role, tenant, channel) and their interaction, not just the three-level summary in FR-010? [Completeness, Spec §FR-010]
  > **Resolved**: FR-010 now explicitly names all four dimensions in priority order: environment > role > tenant > channel > unscoped.

- [x] CHK018 - Is "most specific match wins" defined with a tiebreaker rule for when two Octopus variables have an identical number of scope dimensions set and the same environment? [Completeness, Spec §FR-010, Gap]
  > **Resolved**: FR-010 now specifies that exact ties (same priority level, same number of scope dimensions) MUST NOT be auto-selected — both are emitted as `ambiguous-match` candidates in unknowns with `ambiguous=True` on the edge. Consistent with CLAUDE.md invariant 7 ("emit candidates, never auto-pick").

- [x] CHK019 - Are the specific conformance suite tests the Bitbucket Pipelines stub must pass defined or referenced (not just "sufficient to pass its conformance suite")? [Completeness, Spec §FR-011]
  > **Resolved**: FR-011 now specifies that the stub must implement `id()`, `capabilities()`, and `discover_for_repo()` against fixture data to pass the `CICDProvider` conformance suite. Full test IDs are deferred to the plan; the minimum interface is bounded.

- [x] CHK020 - Are GitHub Actions `vars.*` (readable value) vs `secrets.*` (name-only, masked value) handling requirements specified for variable store reads? [Completeness, Gap]
  > **Resolved**: FR-008 now specifies `vars.*` are read as plain string values; `secrets.*` are recorded with `is_secret=True` and `value=None`. Consistent with SPEC.md §5 and CLAUDE.md invariant 8.

---

## Requirement Clarity — CI/CD Providers

- [x] CHK021 - Is FR-008 clear about multi-environment workflow jobs — specifically, if a single job block lists multiple `environment:` values or steps across environments, how many pipeline bindings are produced? [Clarity, Spec §FR-008]
  > **Resolved**: FR-008 and Key Entities (GitHubActionsProvider entry) now clarify that each GitHub Actions job references at most one environment (a GitHub Actions constraint), and that multiple jobs in the same workflow each produce their own binding.

- [x] CHK022 - Is "parses deployment step names as environment identifiers" for Bitbucket Pipelines (FR-011) defined with the specific YAML keys that map to environment names (e.g., `pipelines.custom.<name>`, `pipelines.branches.<pattern>`)? [Clarity, Spec §FR-011]
  > **Resolved**: FR-011 now specifies the `deployment:` field on pipeline steps under `pipelines.branches`, `pipelines.pull-requests`, `pipelines.custom`, and `pipelines.default` as the source of environment identifiers.

---

## Scenario Coverage

- [x] CHK023 - Are requirements defined for `dependency_path` when no path exists between the specified source and target repos (empty path, not an error)? [Coverage, Spec §FR-002, Gap]
  > **Resolved**: FR-014 (new) specifies: empty results list, `200`, unknowns entry with `kind=no-source`.

- [x] CHK024 - Are requirements defined for `env_diff` when one of the two specified environments has no dependency edges at all? [Coverage, Spec §Edge Cases]
  > **Resolved**: FR-015 (new) specifies: valid response with empty change set, no unknowns unless specific resolution failures occurred.

- [x] CHK025 - Are requirements for all five CLI query operations documented individually, or only as a collective ("all five") with no per-operation detail? [Coverage, Spec §FR-004]
  > **Resolved**: FR-004 now names all five subcommands individually (`find-relevant-repos`, `impact`, `path`, `env-diff`, `explain-edge`). Full per-operation parameter tables are deferred to the plan.

- [x] CHK026 - Is the behavior of `impact_analysis` defined when the target repository has no inbound `DEPENDS_ON` edges (leaf node — nothing depends on it)? [Coverage, Gap]
  > **Resolved**: FR-013 (new) specifies: empty results list, `200`, unknowns entry with `kind=no-match` explaining no repositories depend on the target.

- [x] CHK027 - Are requirements for how `find_relevant_repos` handles the case where the keyword matches a repo but BFS expansion finds no further edges defined (returns the seed repo only, or returns nothing)? [Coverage, Gap]
  > **Resolved**: FR-000 now specifies: the seed repo is returned in results with `hop_depth=0`.

---

## Edge Case Coverage

- [x] CHK028 - Is the behavior defined when the Kùzu graph store is empty or uninitialized at the time the MCP server receives a query request? [Edge Case, Spec §Assumptions, Gap]
  > **Resolved**: FR-003 now specifies `503 Service Unavailable` when the graph store is uninitialized or unreachable, with the Error Response schema body.

- [x] CHK029 - Is the behavior defined when the MCP server receives a `POST` to an unrecognized endpoint (e.g., `/mcp/unknown_tool`) — specifically the HTTP status code and response body? [Edge Case, Spec §Edge Cases]
  > **Resolved**: FR-003 now specifies `404 Not Found` for requests to unrecognized tool endpoints, with the Error Response schema body.

- [x] CHK030 - Is the behavior for stale deployment data documented in requirements — specifically, what appears in the `unknowns` list when a deployed revision is referenced but can no longer be resolved? [Edge Case, Spec §Edge Cases]
  > **Resolved**: Unknowns Entry schema includes `kind=stale-data` for this case. The edge case in User Stories section covers it; the kind enum in Key Entities provides the resolution.

- [x] CHK031 - Is the behavior defined for duplicate Octopus variables with the same name and identical scope (same env, same role) — is one selected, both returned, or is the result flagged ambiguous? [Edge Case, Spec §Edge Cases]
  > **Resolved**: FR-010 now specifies exact ties produce `kind=ambiguous-match` entries in unknowns and `ambiguous=True` on the edge. Consistent with CLAUDE.md invariant 7.

---

## Non-Functional Requirements

- [x] CHK032 - Is the explicit deferral of MCP server authentication documented with a reference to the milestone or condition under which it will be addressed, so it is not silently inherited? [Non-Functional, Spec §Assumptions]
  > **Resolved**: Assumptions now states auth is deferred to "a dedicated security hardening milestone after M7" and specifies that until then the server must only run in a trusted internal network context.

- [x] CHK033 - Is the absence of a latency or throughput requirement for query responses explicitly documented as a deliberate v0 decision, rather than an oversight? [Non-Functional, Gap]
  > **Resolved**: Assumptions now explicitly documents: no latency/throughput SLA in v0, rationale (interactive use on small-to-mid estates), and that a formal SLA is deferred to a future milestone.

---

## Acceptance Criteria Quality

- [x] CHK034 - Is SC-002 ("no field ever omitted or null on a successful response") testable when `deployed_refs` may legitimately have no entries for a repo with no deployment records — is the distinction between "empty map" and "null" specified? [Measurability, Spec §SC-002]
  > **Resolved**: SC-002 now explicitly states `deployed_refs` is an empty object `{}` (never `null`) and `unknowns` is an empty array `[]` (never `null`).

- [x] CHK035 - Is SC-003 ("fresh checkout") defined with the target Python version and operating system so the reproducibility claim is verifiable across different contributor environments? [Measurability, Spec §SC-003]
  > **Resolved**: SC-003 now specifies Python 3.12 on any major operating system (Linux, macOS, Windows), and the exact install and test commands.

- [x] CHK036 - Are the exact expected provenance and confidence values for the GitHub Actions `DEPENDS_ON@staging` edge (SC-005) specified, or is "correct" left undefined? [Measurability, Spec §SC-005, Gap]
  > **Resolved**: SC-005 now specifies `provenance=injected`, `confidence=high` when resolved from GitHub Environments `vars.*`; `confidence=medium` if only unscoped repository variables are available.

- [x] CHK037 - Is SC-006 (Octopus environment scoping) defined with the specific variable names and scope values that constitute the test fixture, making it independently verifiable? [Measurability, Spec §SC-006, Gap]
  > **Resolved**: SC-006 now specifies the exact fixture scenario: `LandingPageUrl` defined twice (unscoped default value and `Environment=Environments-1` scoped value), with the expected resolved output.

---

## Dependencies & Assumptions

- [x] CHK038 - Is the dependency on M4's Kùzu schema — specifically which node and edge types the query engine reads — documented so query engine requirements can be validated against the existing schema? [Dependency, Spec §Assumptions]
  > **Resolved**: Assumptions now documents the Kùzu schema dependency: node types (`Repo`, `Deployable`, `Environment`, `DeployedRef`), edge type (`DEPENDS_ON`) and its fields (`env`, `provenance`, `confidence`, `deployed_ref`, `evidence`, `ambiguous`, `stale`).

- [x] CHK039 - Is the assumption that golden fixture data "already exists in partial form from M4 test fixtures" validated with a list of which fixtures must be created vs which can be reused? [Assumption, Spec §Assumptions, Gap]
  > **Resolved**: Key Entities (Golden Fixture entry) now lists: fixtures to create new (vcs/bitbucket_dc/, vcs/github/, cicd/teamcity/, expected/depends_on_prod.json) and M4 fixtures that can be reused (deployments_Projects-1_prod.json, release_Releases-50.json, variables_Projects-1.json).

---

## Notes

- All 39 items resolved in this pass (2026-06-15).
- Items marked with `[Gap]` were missing requirements added to spec.md FR-013 through FR-015 (new), plus updates to FR-000, FR-003, FR-004, FR-008, FR-009, FR-010, FR-011, Key Entities, Success Criteria, and Assumptions.
- Post-plan: add traceability references (plan.md task IDs) alongside CHK038 and CHK039 once plan.md is written.
- The `kind` enum in Unknowns Entry (`unresolved-ref`, `unresolved-secret`, `no-source`, `stale-data`, `ambiguous-match`, `no-match`) should be validated as exhaustive against all edge cases in the codebase before M5 ships.
