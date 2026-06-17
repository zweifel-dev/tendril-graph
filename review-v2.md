Tendril-Graph: Comprehensive Architecture & Code Review

  Executive Summary

  Tendril-Graph is a well-architected v0 alpha that delivers on its core design promises in fixture/test mode. The plugin contract boundaries are clean, the 7 provider ABCs are correctly implemented, the core BFS traversal +
  acquisition ladder pipeline works end-to-end, and the 210-test suite provides meaningful coverage. The LLM hybrid mode and telemetry cross-validation are more complete than typical v0 implementations.

  However, the system cannot run against a real multi-repo estate today. The graph build CLI command is hard-blocked on live API mode. Several connectors are fixture-only. The README describes a CLI interface that doesn't match
  reality. There are 3 critical bugs in the existing code and significant gaps between what the docs promise and what the code delivers.

  Bottom line for a company founder: The architecture is sound and would not need a rebuild to go production. But this is a working prototype against recorded data, not a deployable tool. Closing the gap to "first real run" requires
  focused work on ~8 specific areas detailed below.

  ---
  I. Critical Issues (Bugs, Security, Spec Violations)

  C1. _path_matches_env always returns True — env filtering is broken

  tendril/store/kuzu_store.py:175

  def _path_matches_env(path_row, env):
      for value in path_row.values():
          if isinstance(value, dict):
              if value.get("env") == env:
                  return True
      return True  # ← always True

  The dependency_path query returns paths from all environments, not just the requested one. Violates Invariant 10 (resolve per environment).

  C2. LLM grounding writes deployable_id instead of repo_full_name to edge.to_id

  tendril/llm/grounding.py:53 → tendril/llm/judge.py:269

  LLM-judged edges use entry.deployable_id (a short slug) as to_id, while all other edges use provider:org/name format. These structurally different IDs cause LLM-contributed edges to be invisible to impact_analysis and
  find_relevant_repos queries — they won't match graph nodes.

  C3. Plugin contract version mismatch — the only existing manifest fails validation

  tendril/connectors/telemetry/tendril-plugin.toml declares contract_version = "0.1.0", but tendril/plugins/base.py declares CONTRACT_VERSION = "1.0.0-alpha". Major version 0 ≠ 1 — the validator rejects this. Any third-party plugin
  would hit the same failure immediately.

  C4. _extract_static_values accepts unresolved templates as static values

  tendril/core/traversal.py:338-340

  A raw value like https://{BaseUrl}/api passes the not startswith("{") filter because it starts with "h". The resolver then treats the template string as a resolved value at rung 1, which will never match the index.

  C5. CrossValidator._write_runtime_edge silently discards updated evidence on re-runs

  tendril/core/cross_validate.py:404-408

  After the first reconcile, subsequent runs find the existing edge and return without updating evidence. Telemetry evidence becomes permanently stale. Violates Invariant 6 (provenance + confidence on every edge) and Invariant 11
  (communicate accuracy).

  ---
  II. Major Gaps

  Architecture Gaps

  ┌───────────────────────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────┬────────────────────┐
  │                                Gap                                │                                              Impact                                               │   Spec Reference   │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ No live API mode — graph build requires --fixture-dir             │ Blocks all real use                                                                               │ README Quickstart  │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ No providers add CLI command                                      │ README shows 6 providers add calls; none exist                                                    │ README §Quickstart │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ No VCS/CI/CD credential configuration                             │ No tendril.toml or env var paths for BB/TC/Octo/GH credentials                                    │ SPEC §4            │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ MCP server is REST, not MCP protocol                              │ Not compatible with Claude Desktop, Cursor, or standard MCP clients                               │ FR-15              │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ No BUILT_BY/DEPLOYED_BY/RESOLVES_VARS_FROM edges written to store │ Only DEPENDS_ON edges persist — the rich provenance graph is modeled but not populated            │ SPEC §2            │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ resolved_via not in Kùzu DDL                                      │ Field exists on Python dataclass but not in schema — incremental invalidation (FR-16) cannot work │ §14                │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ Bitbucket Cloud VCS provider missing                              │ README documents credentials; no implementation exists                                            │ SPEC §5            │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ IaC extractor missing (Helm, k8s, Terraform, Docker)              │ No extraction from infrastructure-as-code files                                                   │ SPEC §6            │
  ├───────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┤
  │ JS/TS extractor is stub-only                                      │ Only parses .env files; no Angular environment.ts, no package.json deps                           │ FR-2               │
  └───────────────────────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────┴────────────────────┘

  Connector Production Gaps

  ┌─────────────────────┬─────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │      Connector      │    Live API?    │                                                 Key Issue                                                 │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ GitHub VCS          │ Yes (basic)     │ No error handling, no rate limiting, no timeout, truncation unchecked                                     │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Bitbucket DC VCS    │ Partial         │ read_tree returns flat root listing, not recursive — misses all nested files                              │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ TeamCity            │ Yes (basic)     │ No pagination on buildTypes; no timeout/error handling                                                    │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Octopus             │ Yes (strongest) │ No pagination; build-info fallback query uses wrong field; rung-3 passes repo.name not Octopus project ID │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ GitHub Actions      │ Fixture-only    │ Live mode cannot read workflow file content — no env detection                                            │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Bitbucket Pipelines │ Fixture-only    │ Returns stub binding only                                                                                 │
  ├─────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Datadog             │ Fixture-only    │ probe() returns all-false in live mode — zero telemetry                                                   │
  └─────────────────────┴─────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  ★ Insight ─────────────────────────────────────
  The Octopus connector is the most production-complete connector — it implements the full 4-dimension variable scoping (env > role > tenant > channel > unscoped) with ambiguity detection. This is the hardest part of the Octopus
  integration and it's done correctly. The remaining Octopus gaps (pagination, build-info fallback) are straightforward fixes.
  ─────────────────────────────────────────────────

  ---
  III. Test Assessment

  210 tests, all passing (verified by agent). Well-structured across conformance/unit/integration layers.

  Well-Covered

  - Core DEPENDS_ON pipeline with SC-003 exact assertions
  - All 5 query operations with field-level checks
  - Secret redaction (multi-layer verification)
  - LLM hybrid mode (cache, degradation, provenance)
  - Telemetry cross-validation (three-way reconciliation)
  - SubprocessBridge resilience

  Critical Test Gaps

  ┌───────────────────────────────────────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────┐
  │                                      Gap                                      │                                       Risk                                        │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ MCP server has ZERO test coverage — no TestClient tests for any endpoint      │ The primary agent interface is untested                                           │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ BFS cycle detection never tested                                              │ Circular deps could loop indefinitely without detection                           │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ ReverseIndex has no unit tests                                                │ URL normalization, www-stripping, multi-candidate returns untested                │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ Resolver rung 3 (preview API) untested                                        │ Broken read_effective_value would pass silently                                   │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ test_reconcile_logs_only_capability tests empty results                       │ The fixture file doesn't exist; assertion trivially passes on empty set           │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ test_sc007_llm_module_not_imported is ineffective                             │ Other tests in the same file already import LLM modules; the test is tautological │
  ├───────────────────────────────────────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
  │ Fixture data duplicated between test_end_to_end.py and test_golden_fixture.py │ Divergence risk — a change in one doesn't propagate to the other                  │
  └───────────────────────────────────────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────┘

  ---
  IV. Documentation Accuracy

  README.md Issues

  - Quickstart commands don't exist: Tendril-Graph init, Tendril-Graph providers add — none implemented
  - Command name: README uses Tendril-Graph (capitalized); actual CLI is tendril (lowercase)
  - Argument mismatches: find-relevant-repos "task" (positional) → actual is --task; impact <repo> → actual is --repo-id; explain-edge <edge-id> → actual is --from-id --to-id --env
  - MCP protocol claim: README says "serve to coding agents" via MCP — the server is REST/HTTP, not the MCP JSON-RPC protocol

  CLAUDE.md Issues

  - States "Package layout: All implementation packages live at the project root as flat top-level packages" — actually everything is under tendril/ as subpackages
  - Claims tendril/ is "a thin shim" — it contains the entire implementation

  review.md

  - States "Package layout: all code lives inside tendril/. Imports use from tendril.X import Y" — this is correct and contradicts CLAUDE.md

  ★ Insight ─────────────────────────────────────
  The documentation hierarchy is sound (PRD → SPEC → architecture.md → review.md), and the spec documents are high-quality. The drift is concentrated in the README quickstart (aspirational) and CLAUDE.md (stale package layout
  description). The SPEC and PRD accurately describe what was built.
  ─────────────────────────────────────────────────

  ---
  V. Invariant Compliance

  ┌─────┬─────────────────────────────────────────────┬─────────┬────────────────────────────────────────────────────────────────────┐
  │  #  │                  Invariant                  │ Status  │                               Notes                                │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 1   │ Plugin-first                                │ Pass    │ All providers behind ABCs; no platform names in core               │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 2   │ Projection join                             │ Pass    │ URL/identity matching, not name matching                           │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 3   │ Index globally, traverse from anchor        │ Partial │ CLI only indexes repo_homepages, not extracted provider identities │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 4   │ CI/CD is per-repo                           │ Pass    │ Attribution runs before resolution                                 │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 5   │ Capability detection + graceful degradation │ Partial │ Connectors degrade, but VCS HTTP errors crash the run              │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 6   │ Provenance + confidence on every edge       │ Pass    │ Enforced by dataclass                                              │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 7   │ Never fabricate                             │ Pass    │ Secrets masked, ambiguous kept, unresolved flagged                 │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 8   │ Read-only and secret-redacting              │ Partial │ Redaction pattern misses *connstr* variants common in .NET         │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 9   │ LLM grounded, never authoritative           │ Pass    │ GroundingStep validates every proposal                             │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 10  │ Resolve at deployed ref                     │ Pass    │ DeployedRefResolver wired end-to-end                               │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 11  │ Communicate accuracy and uncertainty        │ Pass    │ Every QueryResult has unknowns, confidence, provenance             │
  ├─────┼─────────────────────────────────────────────┼─────────┼────────────────────────────────────────────────────────────────────┤
  │ 12  │ Seamed for expansion                        │ Pass    │ All 7 interfaces are real contracts                                │
  └─────┴─────────────────────────────────────────────┴─────────┴────────────────────────────────────────────────────────────────────┘

  ---
  VI. Prioritized Recommendations

  Tier 1: Must Fix (blocks correctness)

  1. Fix _path_matches_env — change return True to return False so env filtering works
  2. Fix LLM grounding to_id — use entry.repo_full_name instead of entry.deployable_id
  3. Fix plugin contract version — align tendril-plugin.toml to "1.0.0-alpha" or update CONTRACT_VERSION
  4. Fix _extract_static_values — check that raw_value contains no {...} substitution markers, not just startswith
  5. Fix _write_runtime_edge — update evidence on existing edges instead of silently returning

  Tier 2: Must Build (blocks real-world use)

  6. Implement live API mode for graph build — wire VCS/CI/CD provider constructors to credentials from tendril.toml / env vars
  7. Add VCS/CI/CD credential config — extend tendril.toml schema and env vars for all provider credentials
  8. Fix Bitbucket DC read_tree — use recursive browse API, not flat /files/{ref}
  9. Add HTTP error handling + timeouts to all _get() methods in VCS and CI/CD connectors
  10. Add MCP server tests using fastapi.testclient.TestClient

  Tier 3: Should Fix (improves quality/trust)

  11. Add tendril-plugin.toml manifests for all in-tree providers
  12. Register in-tree providers as pyproject.toml entry points so providers list actually works
  13. Add BFS cycle detection test and ReverseIndex unit tests
  14. Fix env_diff semantics — compare structural changes (target repos), not confidence strings
  15. Update README quickstart to match actual CLI interface
  16. Fix CLAUDE.md package layout description
  17. Add --verbose / --log-level CLI flag with logging.basicConfig setup
  18. Implement proper MCP JSON-RPC transport (stdio/SSE) for standard MCP client compatibility
  19. Add pagination to TeamCity list_pipelines and Octopus list_pipelines
  20. De-duplicate fixture data between test_end_to_end.py and test_golden_fixture.py

  Tier 4: Future Work (in-spec, planned)

  21. Complete JS/TS extractor (Angular environment.ts, package.json)
  22. Build IaC extractor (Helm, k8s, Terraform, Docker)
  23. Implement Bitbucket Cloud VCS provider
  24. Implement Datadog live API mode
  25. Implement GitHub Actions live workflow parsing
  26. Implement incremental refresh (FR-16)
  27. Write BUILT_BY/DEPLOYED_BY edges to store for richer graph queries
  28. Implement providers add CLI with credential persistence

  ---
  ★ Insight ─────────────────────────────────────
  The honest assessment for someone starting a company with this tool:

  The architecture is correct and production-grade — the plugin boundary, projection join, acquisition ladder, and evidence model are the hard parts and they're done right. You would not need to rebuild.

  The implementation is a working prototype against recorded fixtures. The gap between "all tests pass" and "first real run against your Bitbucket/TeamCity/Octopus estate" is approximately Tier 1 fixes (1 week) + Tier 2 items 6-9 (2-3
   weeks). The Octopus connector is closest to production; GitHub VCS needs error handling; Bitbucket DC needs a read_tree fix; the CLI needs credential wiring.

  The biggest risk is the MCP protocol mismatch — the server is REST, not the MCP JSON-RPC protocol that coding agents (Claude, Cursor) expect. If the goal is to serve coding agents, this needs to be the MCP stdio/SSE transport, not
  FastAPI POST endpoints.
  ─────────────────────────────────────────────────