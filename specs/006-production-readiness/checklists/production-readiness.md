# Production Readiness Checklist: Critical Fixes and Live API Mode

**Purpose**: Validate that Tier 1 (correctness) and Tier 2 (live infrastructure) requirements are complete, clear, and buildable — author self-review before implementation
**Created**: 2026-06-16
**Feature**: [spec.md](../spec.md)
**Scope**: FR-001 through FR-010 (P1 + P2 user stories only)

## Requirement Completeness

- [x] CHK001 - Is the definition of "belongs to environment" specified for edges that span environments (e.g., from_id is prod-scoped but to_id is unscoped)? [Gap, Spec §FR-001]
  - **Resolved**: FR-001 now specifies that every DEPENDS_ON edge carries an explicit `env` property and filtering is by exact match. Primary filtering is at Cypher level (`WHERE r.env = $env`); `_path_matches_env` is a secondary safety net. No edge "spans" environments — each edge has one `env`.
- [x] CHK002 - Are requirements defined for what happens when `repo_full_name` is unavailable on an LLM entry (e.g., LLM proposes a repo not in the index)? [Gap, Spec §FR-002]
  - **Resolved**: FR-002 now clarifies that ungrounded proposals (no index match) are already handled by existing `grounding-failed` logic. FR-002 only applies when grounding succeeds — the fix is using the correct field from a successful match.
- [x] CHK003 - Is the target contract version value specified (what the manifests should be aligned TO), or only that they must "align"? [Completeness, Spec §FR-003]
  - **Resolved**: FR-003 now explicitly states the target is `"1.0.0-alpha"` and explains the major-version validation rule.
- [x] CHK004 - Are the specific template marker patterns to detect enumerated beyond `{...}` (e.g., `$(Var)`, `#{...}`, `%{...}`)? [Completeness, Spec §FR-004]
  - **Resolved**: FR-004 now specifies the general-case regex (`\{[^}]+\}`) and explicitly states platform-specific syntaxes are extractor responsibility, out of scope for this core fix.
- [x] CHK005 - Is the evidence merge strategy defined for re-runs — does new evidence replace old, append to it, or merge by deduplication? [Gap, Spec §FR-005]
  - **Resolved**: FR-005 now specifies **accumulate-and-deduplicate** strategy: append new evidence, deduplicate by `(locator, capability)` tuple, retain newest timestamp per unique item.
- [x] CHK006 - Are requirements defined for how live-mode providers are discovered and instantiated (automatic from available credentials, or user-specified)? [Gap, Spec §FR-006]
  - **Resolved**: FR-006 now specifies automatic discovery based on credential availability, with provider dependency chain (VCS required, CI/CD needs VCS, telemetry independent).
- [x] CHK007 - Are credential validation requirements specified — can the system check if credentials are valid before running a full graph build? [Gap, Spec §FR-007]
  - **Resolved**: FR-007 now includes lightweight validation call (SHOULD) on initialization; failure skips the provider with a WARNING. Empty/whitespace values treated as "not configured."
- [x] CHK008 - Are requirements specified for file types excluded from recursive tree retrieval (symlinks, submodules, binary files)? [Gap, Spec §FR-008]
  - **Resolved**: FR-008 now states all entries reported by the API are returned; content-type filtering is extractor responsibility. Also added 10,000-file warning threshold.
- [x] CHK009 - Are default values specified for configurable timeout durations, retry counts, and backoff strategy? [Gap, Spec §FR-009]
  - **Resolved**: FR-009 now specifies 30s timeout, 3 retries, exponential backoff (1s, 2s, 4s), Retry-After header respected, config via env vars/TOML.
- [x] CHK010 - Are requirements defined for what the MCP server must guarantee (response shape contracts, error body schemas) independent of test count? [Completeness, Spec §FR-010]
  - **Resolved**: FR-010 now specifies JSON response contracts (Pydantic schemas for success, structured error bodies for all error codes) as the requirement, with tests as validation method.

## Requirement Clarity

- [x] CHK011 - Is "graceful degradation" quantified for each degradation scenario — what does the user see, what gets logged, what edges get flagged? [Clarity, Spec §US-3 Scenario 2]
  - **Resolved**: US-3 scenarios now specify: WARNING log naming provider and reason, exit code 0, `metadata.degradation_notices` in output. All-missing-VCS case is a separate scenario with non-zero exit code.
- [x] CHK012 - Is "configurable timeouts" clarified — configurable via CLI flags, config file, environment variables, or all three? [Clarity, Spec §FR-009]
  - **Resolved**: FR-009 now specifies env vars (`TENDRIL_HTTP_TIMEOUT`, `TENDRIL_HTTP_RETRIES`) > `tendril.toml` `[http]` section > built-in defaults. Explicitly: no CLI flags.
- [x] CHK013 - Is the meaning of "aligned" in FR-003 unambiguous — does it mean identical strings, or semver-compatible? [Clarity, Spec §FR-003]
  - **Resolved**: FR-003 now states the target string (`"1.0.0-alpha"`) and explains the validation rule: major-version match (first segment before `.`).
- [x] CHK014 - Is "rate-limit retry" defined with specific behavior — exponential backoff, fixed delay, respect Retry-After header, or all? [Clarity, Spec §US-7 Scenario 4]
  - **Resolved**: US-7 scenario 3 now specifies: respect `Retry-After` when present, exponential backoff (1s, 2s, 4s) when absent, max 3 retries. FR-009 mirrors this.
- [x] CHK015 - Is "updated evidence" in FR-005 distinguished from "replaced evidence" — does the old evidence history survive or is it overwritten? [Clarity, Spec §FR-005]
  - **Resolved**: FR-005 now specifies accumulate-and-deduplicate. No evidence history is lost — only exact duplicates are collapsed. Addressed jointly with CHK005.
- [x] CHK016 - Is "at least one DEPENDS_ON edge" in SC-003 sufficient to declare success, or should the criterion specify expected edge count relative to estate size? [Clarity, Spec §SC-003]
  - **Resolved**: SC-003 split into SC-003a (automated, fixture) and SC-003b (manual, live). SC-003b retains "at least one" with rationale: proves pipeline works e2e; completeness validated by subsequent queries.

## Requirement Consistency

- [x] CHK017 - Does FR-001's "return False when no node matches" align with US-1 Scenario 1's "at least one node has env == prod" — are these the same filtering rule? [Consistency, Spec §FR-001 vs §US-1]
  - **Resolved**: Yes, they describe the same rule from different perspectives. FR-001 now clarifies the two-tier model: primary Cypher-level filtering (exact match on `env` property) and secondary `_path_matches_env` safety net. The US-1 scenario describes the user-visible behavior; FR-001 describes the mechanism. No conflict.
- [x] CHK018 - Does FR-007 (credential config for "all supported providers" including Datadog) conflict with the Assumption that "Datadog live API mode is out of scope"? [Conflict, Spec §FR-007 vs Assumptions]
  - **Resolved**: No conflict. Credential configuration and live API mode are different concerns. Assumptions now explicitly state: "Datadog credential configuration (FR-007) IS in scope for consistency — the credential loading already exists in `config.py` and only needs verification, not new implementation."
- [x] CHK019 - Are pagination requirements in FR-011 (Tier 3, out of checklist scope) a dependency for FR-009's error handling — can resilience work without pagination? [Consistency, Spec §FR-009 vs §FR-011]
  - **Resolved**: They are independent. FR-009 now explicitly states it "applies to all HTTP requests including those made during paginated fetches (FR-011)." Resilience wraps individual HTTP calls; pagination is a higher-level loop. No dependency.
- [x] CHK020 - Does US-7 Scenario 2 (pagination) belong under FR-009 (resilience) or FR-011 (pagination) — is the requirement split consistent with how it will be built? [Consistency, Spec §US-7 vs §FR-009/FR-011]
  - **Resolved**: Pagination scenario removed from US-7. US-7 now focuses on error resilience only, with a cross-reference note: "Pagination of large result sets is covered by FR-011 (Tier 3)."

## Acceptance Criteria Quality

- [x] CHK021 - Can SC-001 ("zero cross-environment leakage") be measured with the current test fixtures, or are new multi-environment fixtures needed? [Measurability, Spec §SC-001]
  - **Resolved**: SC-001 now states: "New test fixtures with edges in both 'prod' and 'staging' environments are required to validate this criterion."
- [x] CHK022 - Is SC-003 ("completes against live APIs") testable in CI where no live credentials exist — is there a fixture-mode equivalent acceptance criterion? [Measurability, Spec §SC-003]
  - **Resolved**: Split into SC-003a (automated, fixture-based, CI-testable) and SC-003b (manual, live APIs, first-deployment acceptance).
- [x] CHK023 - Is SC-004 ("graceful degradation") defined with specific observable outcomes (log messages, exit code, output format) that can be asserted? [Measurability, Spec §SC-004]
  - **Resolved**: SC-004 now specifies: exit code 0, WARNING log lines for each degraded provider, JSON output includes `metadata.degradation_notices` array.
- [x] CHK024 - Is SC-008 ("at least 3 directory levels") a sufficient depth to catch the recursive browse bug, or should the fixture include more realistic nesting? [Measurability, Spec §SC-008]
  - **Resolved**: SC-008 now includes rationale: "sufficient to distinguish flat listing from recursive traversal." 3 levels proves recursion works (root → child → grandchild); the current bug returns only root.
- [x] CHK025 - Does SC-010 ("210 tests pass") need updating if new tests are added as part of this work — is the baseline number dynamic or fixed? [Measurability, Spec §SC-010]
  - **Resolved**: SC-010 changed from "210 tests" to "all existing tests at the start of this work" — dynamic baseline.

## Scenario Coverage

- [x] CHK026 - Are requirements defined for partial credential configurations (e.g., VCS credentials present but CI/CD credentials missing) — which providers can function independently? [Coverage, Spec §US-3]
  - **Resolved**: FR-006 now defines the provider dependency chain: VCS required for any build; CI/CD requires VCS; telemetry independent. Partial configs are handled by auto-discovery with per-provider skip.
- [x] CHK027 - Are requirements specified for what happens when live API mode encounters a repo that was previously indexed from fixtures — merge, replace, or error? [Coverage, Gap]
  - **Resolved**: Added to Assumptions: "Live mode starts from a clean graph store. Behavior when encountering repos previously indexed from fixtures is not defined — out of scope for v0."
- [x] CHK028 - Are recovery requirements defined for interrupted graph builds (e.g., network failure mid-traversal) — resume, restart, or partial result? [Coverage, Gap, Recovery Flow]
  - **Resolved**: Added to both Edge Cases and Assumptions: "Partial results are acceptable for v0. The graph store is transactional — committed edges survive, uncommitted edges are lost. No resume mechanism is provided."
- [x] CHK029 - Are requirements defined for concurrent reconciliation runs — can two `tendril telemetry reconcile` runs race on evidence updates? [Coverage, Spec §FR-005]
  - **Resolved**: Added to Assumptions: "Concurrent reconciliation runs are not supported. Kuzu is an embedded (single-process) store. This is documented but not enforced."
- [x] CHK030 - Are requirements specified for how the system behaves when ALL provider credentials are missing in live mode — error immediately or proceed with empty graph? [Coverage, Spec §US-3]
  - **Resolved**: US-3 Scenario 4 added: "Given ALL VCS provider credentials are missing, system exits immediately with non-zero exit code and error message referencing `.env.example`." FR-006 mirrors this.

## Edge Case Coverage

- [x] CHK031 - Is behavior defined when Bitbucket DC recursive tree exceeds API response limits (very large repos with 10,000+ files)? [Edge Case, Spec §FR-008]
  - **Resolved**: FR-008 now specifies pagination of the recursive API and a WARNING log at 10,000+ files. Edge Cases section also documents this.
- [x] CHK032 - Is behavior defined when a template marker is inside a comment or dead code path (e.g., `// old: {BaseUrl}`)? [Edge Case, Spec §FR-004]
  - **Resolved**: Added to Edge Cases: "Template markers inside comments are not a concern — config file parsers strip comments before values reach the extractor." Template detection operates on parsed config values, not raw source.
- [x] CHK033 - Is behavior defined when an LLM-judged edge's target repo is later removed from the graph during a re-build? [Edge Case, Spec §FR-002]
  - **Resolved**: Added to Edge Cases: "Normal lifecycle — each graph build replaces the graph; orphaned edges from prior builds do not persist."
- [x] CHK034 - Is behavior defined when credential environment variables exist but contain empty/whitespace values? [Edge Case, Spec §FR-007]
  - **Resolved**: FR-007 now specifies: "Empty or whitespace-only values in environment variables MUST be treated as 'not configured' (equivalent to the variable being unset)." Also in Edge Cases.
- [x] CHK035 - Is behavior defined for API responses with unexpected content types (HTML error pages instead of JSON)? [Edge Case, Spec §FR-009]
  - **Resolved**: FR-009 now specifies: "On non-JSON response bodies, the response MUST be treated as an error and the connector MUST degrade gracefully." US-7 Scenario 4 and Edge Cases also cover this.

## Dependencies & Assumptions

- [x] CHK036 - Is the assumption that "no new HTTP client libraries are required" validated — can `requests` handle all resilience requirements (retry, backoff, timeout) natively? [Assumption, Spec §Assumptions]
  - **Resolved**: Assumption corrected — connectors use `urllib.request` (stdlib), not `requests`. Updated to: "`urllib.request.urlopen` supports the `timeout` parameter natively. Retry and backoff logic will be implemented as a small utility wrapper around the existing `_get()` methods." No new libraries needed.
- [x] CHK037 - Is the dependency between FR-006 (live mode) and FR-007 (credential config) explicitly sequenced — must FR-007 be complete before FR-006 can be built? [Dependency, Spec §FR-006/FR-007]
  - **Resolved**: FR-006 now includes: "**Build dependency**: FR-007 (credential config) must be complete before FR-006 can be implemented."
- [x] CHK038 - Is the assumption that `.env.example` "already exists or will be created" resolved — does it exist today? [Assumption, Spec §Assumptions]
  - **Resolved**: Verified in codebase — `.env.example` exists at project root with all provider credential placeholders. Assumption updated to: "The `.env.example` file exists at the project root and documents all provider credentials with placeholder values."
- [x] CHK039 - Are the Bitbucket DC API recursive browse endpoints documented or referenced — is the correct API path known? [Dependency, Spec §FR-008]
  - **Resolved**: FR-008 now references the API: "The fix MUST use the recursive browse API (`/browse?at={ref}` with recursive traversal or equivalent)." Current code uses `/files/{ref}` (flat); the fix needs `/browse` or equivalent recursive endpoint.
- [x] CHK040 - Is the relationship between this spec and the deferred MCP protocol spec documented — are there shared requirements that could conflict? [Dependency, Spec §Assumptions]
  - **Resolved**: Assumptions now state: "The shared surface between this spec and the future MCP protocol spec is limited to the five endpoint names and their request/response schemas (defined by QueryEngine and Pydantic models), which are unchanged by a transport swap — no conflict risk."

## Notes

- This checklist covers Tier 1 (FR-001–FR-005) and Tier 2 (FR-006–FR-010) only
- Tier 3 items (FR-011–FR-015) are excluded per scope selection
- Items are ordered by requirement quality dimension, not by priority tier
- **All 40 items resolved** — spec updated with recommendations on 2026-06-16
- Key spec changes: FR corrections grounded against codebase (urllib not requests, .env.example exists, contract version is 1.0.0-alpha), SC-003 split into automated/manual, evidence merge strategy defined, graceful degradation quantified, provider dependency chain specified
