# Spec Review Checklist: Roslyn IntraRepoProvider (M8)

**Purpose**: Author self-review of requirements quality before `/speckit.plan` — validates completeness, clarity, consistency, and measurability of the spec. Full coverage: subprocess/protocol contracts AND analysis output contracts.
**Created**: 2026-06-15
**Feature**: [spec.md](../spec.md)
**Scope**: Q1=Both risk areas, Q2=Author pre-plan
**Status**: All gaps resolved ✅

---

## Requirement Completeness

- [x] CHK001 - Is the exact JSON schema for `tendril-rpc/v1` request and response messages specified, including all required vs optional fields and their types? [Completeness, Gap]
  > **Resolved**: Full wire protocol section added to spec. JSON-RPC 2.0 subset: request `{id, method, params}`, success `{id, result}`, error `{id, error: {code, message, data}}`. Handshake defined. Error codes enumerated. `id` preserved for future multiplexing.

- [x] CHK002 - Is the format of a `def_use_chain` entry formally defined with all possible source locator patterns? [Completeness, Spec §Key Entities]
  > **Resolved**: Format is `"<relative_path>:<key_or_line>"`. Config locators use key name (`"web.config:LandingPageUrl"`); source locators use line number (`"src/AppConfig.cs:42"`). Always relative to repo root.

- [x] CHK003 - Is the `IntraRepoFacts` structure fully specified with all required fields — including whether `call_graph` is required or optional in M8? [Completeness, Spec §Key Entities]
  > **Resolved**: Full JSON schema added to Key Entities. `call_graph` is always `null` in M8. Added `partial_analysis`, `truncated`, `skipped_files` fields.

- [x] CHK004 - Is the `ValueSet` structure specified with its "condition" field format for multi-env keys? [Completeness, Spec §Key Entities]
  > **Resolved**: `condition` is the basename of the most specific config file (e.g., `"appsettings.prod.json"`), or `null` for unconditioned values. Full example added to Key Entities.

- [x] CHK005 - Is the `partial_analysis: true` flag defined with a precise consumer contract? [Completeness, Spec §FR-M8-004]
  > **Resolved**: When `partial_analysis: true`, callers MUST treat layer-2 def-use chains as absent. Traversal engine records `source_analysis: partial` in edge evidence and continues without aborting.

- [x] CHK006 - Are the exact secret redaction patterns documented (e.g., glob syntax, case sensitivity, configurable list location)? [Completeness, Spec §FR-M8-012]
  > **Resolved**: FR-M8-012 updated with explicit defaults: `*password*`, `*secret*`, `*token*`, `*apikey*`, `*api_key*`, `*connectionstring*`. Case-insensitive glob. Configurable in `tendril.toml` `[redact_patterns]`.

- [x] CHK007 - Is the subprocess shutdown/teardown lifecycle specified? [Completeness, Gap]
  > **Resolved**: Subprocess lifetime = `SubprocessBridge` instance lifetime. Teardown via stdin EOF (clean exit signal). Context manager interface required (`with SubprocessBridge(...) as bridge`). Documented in FR-M8-001 and Key Entities.

- [x] CHK008 - Is the path configuration mechanism for the `TendrilRoslyn` binary specified? [Completeness, Gap]
  > **Resolved**: `TENDRIL_ROSLYN_BINARY` env var (highest priority) or `intra_repo.roslyn_binary` in `tendril.toml`. PATH is NOT searched by default (explicit path required for reproducibility).

- [x] CHK009 - Is the required .NET target framework version for `TendrilRoslyn` specified? [Completeness, Gap]
  > **Resolved**: Targets `net8.0`; minimum supported `net6.0`. Documented in Key Entities (`TendrilRoslyn` entry) and Assumptions.

- [x] CHK010 - Are version compatibility requirements between `TendrilRoslyn` and the Python `SubprocessBridge` documented? [Completeness, Gap]
  > **Resolved**: Handshake protocol defined in Wire Protocol section. Version `"1.0"` in M8. Incompatible version → bridge closes subprocess, surfaces `SubprocessError`, sets `capabilities()` to all-false with clear error message.

---

## Requirement Clarity

- [x] CHK011 - Is the layer 1 / layer 2 boundary observable from `IntraRepoFacts` output? [Clarity, Spec §Overview, FR-M8-004]
  > **Resolved**: Every entry in `value_sets` carries `"layer": 1 | 2`. Callers can always determine which layer produced a result without interpreting the source locator. Documented in Overview, FR-M8-004, and Key Entities.

- [x] CHK012 - Is the precedence rule defined when the same key exists in both layers with different values? [Clarity, Gap]
  > **Resolved**: Layer 2 takes precedence (C# source overrides config-file defaults at runtime). Both values preserved in `value_sets` with their `layer` field. `resolve_value()` returns layer-2 result as primary. Documented in Overview and FR-M8-005.

- [x] CHK013 - Is "syntactic analysis" vs "semantic analysis" in layer 2 clearly delineated? [Clarity, Spec §Assumptions]
  > **Resolved**: Syntactic analysis (no build: `const` declarations, field initializers, property defaults) runs first and always succeeds. Semantic analysis (compiled workspace: cross-file def-use, constant folding) upgrades it when available. If semantic fails, syntactic results are preserved. Documented in Overview, FR-M8-004, and Assumptions.

- [x] CHK014 - Is "falls back gracefully" in FR-M8-004 defined with a specific observable output? [Clarity, Spec §FR-M8-004]
  > **Resolved**: Layer 2 failure → returns `IntraRepoFacts` with `partial_analysis: true`, layer-1 results only, `call_graph: null`, `skipped_files` populated. Specified in FR-M8-004.

- [x] CHK015 - Is the 30-second per-call timeout defined to clarify when the clock starts? [Clarity, Spec §FR-M8-002]
  > **Resolved**: Clock starts when the lock is acquired (request sent), not from queue enqueue time. Documented in FR-M8-002 and confirmed consistent with the edge case added in speckit.clarify.

- [x] CHK016 - Is `SubprocessError` fully specified with its required attributes? [Clarity, Gap]
  > **Resolved**: Full definition added to Key Entities: `method`, `message`, `code` (JSON-RPC), `restarted: bool`, `detail: dict | None`.

- [x] CHK017 - Is "keeps it alive across multiple calls" clarified with a definition of session lifetime? [Clarity, Spec §FR-M8-001]
  > **Resolved**: Session = `SubprocessBridge` instance lifetime = one `tendril graph build` run. One bridge instance is created per run and shared across all .NET repos. Documented in FR-M8-003 and Assumptions.

- [x] CHK018 - Is `reason="dynamic-value"` defined as part of the `Unresolved` type contract? [Clarity, Spec §Edge Cases]
  > **Resolved**: `Unresolved` has a typed `reason` field. All M8 values defined: `"not-found"`, `"dynamic-value"`, `"is-secret"`, `"build-failed"`, `"parse-error"`, `"nuget-restore-failed"`, `"workspace-load-failed"`. JSON schema added to Key Entities.

---

## Requirement Consistency

- [x] CHK019 - Is timeout semantics consistent between SC-M8-005 and FR-M8-002/002b? [Consistency, Spec §FR-M8-002, SC-M8-005]
  > **Resolved**: SC-M8-005 updated to explicitly state "30 seconds of the lock being acquired" / "120 seconds of the lock being acquired", matching FR-M8-002's clock-start definition.

- [x] CHK020 - Is the degradation behavior consistent between FR-M8-010 (missing binary) and FR-M8-002b (analyze timeout)? [Consistency, Spec §FR-M8-002b, FR-M8-010]
  > **Resolved**: Both paths record `evidence=["intra-repo-provider:degraded", "<reason>"]` on affected edges. Both result in acquisition-ladder fallback. Documented in FR-M8-002b.

- [x] CHK021 - Are the fixture-mode conformance requirements consistent with the two-layer architecture? [Consistency, Spec §FR-M8-008]
  > **Resolved**: FR-M8-008 updated to specify that the fixture (`tests/fixtures/conformance/intra/roslyn/analyze_result.json`) MUST cover both layer-1 and layer-2 entries to fully exercise the two-layer contract.

- [x] CHK022 - Is secret redaction consistent between FR-M8-012 and the project-wide redaction rules? [Consistency, Spec §FR-M8-012, Assumptions]
  > **Resolved**: Both `SubprocessBridge` and traversal engine use `tendril.toml` `[redact_patterns]` as the single source of truth. Documented in FR-M8-012 and Assumptions.

---

## Acceptance Criteria Quality

- [x] CHK023 - Is SC-M8-001 ("100% of cases") measurable against a defined fixture set? [Measurability, Spec §SC-M8-001]
  > **Resolved**: SC-M8-001 rephrased to be bounded: "For 100% of literal-value keys in the M8 golden fixture (`tests/fixtures/conformance/intra/roslyn/`)…"

- [x] CHK024 - Is SC-M8-003 ("All 111 existing tests") fragile with a hard-coded count? [Clarity, Spec §SC-M8-003]
  > **Resolved**: SC-M8-003 rephrased as "all tests passing at the start of M8 development (baseline: 111) continue to pass" — decoupled from a fixed count while retaining the baseline reference for context.

- [x] CHK025 - Is there an acceptance criterion for the C# AST layer (layer 2) specifically? [Gap, Spec §Success Criteria]
  > **Resolved**: SC-M8-007 added: given `AppConfig.cs` with `private const string ServiceUrl = "https://svc.prod.example.com";`, `resolve_value("ServiceUrl")` returns the correct value with `layer=2`.

- [x] CHK026 - Is SC-M8-004 ("warning logged") testable with a specified log level and format? [Measurability, Spec §SC-M8-004]
  > **Resolved**: SC-M8-004 updated to specify WARNING log level and structured field `event="roslyn-binary-unavailable"`, testable via pytest `caplog`.

---

## Scenario Coverage

- [x] CHK027 - Are requirements defined for `analyze()` called on a repo with no .NET files? [Coverage, Gap]
  > **Resolved**: FR-M8-013 added: empty `IntraRepoFacts` returned immediately; traversal engine MUST call `.matches(repo_ir)` before `analyze()`.

- [x] CHK028 - Is the behavior specified when `TendrilRoslyn` binary version mismatches the bridge? [Coverage, Gap]
  > **Resolved**: Covered by the handshake protocol (CHK010). Incompatible version → bridge closes subprocess, sets capabilities to all-false, logs clear version-mismatch error.

- [x] CHK029 - Are requirements defined for non-string values in `appsettings*.json`? [Coverage, Gap]
  > **Resolved**: FR-M8-006 updated: non-string JSON values serialized to string representation (`8080` → `"8080"`, `true` → `"true"`). Included in edge cases.

- [x] CHK030 - Are requirements specified for when layer 2 contradicts layer 1 for the same key? [Coverage, Conflict Resolution, Gap]
  > **Resolved**: Layer 2 takes precedence (CHK012); both values preserved in `value_sets` with respective `layer` fields. Documented in Overview, edge cases, and FR-M8-005.

---

## Edge Case Coverage

- [x] CHK031 - Is the "duplicate key" edge case clear about who is responsible for disambiguation? [Clarity, Spec §Edge Cases]
  > **Resolved**: Analyzer returns all candidates with source locators; `resolve_value()` (in `RoslynIntraRepoProvider`) performs disambiguation using specificity tiebreak: most-specific config file first, layer 2 over layer 1, alphabetical tiebreak. Documented in edge cases and FR-M8-005.

- [x] CHK032 - Is the behavior defined when `resolve_value()` returns a `ValueSet`? [Edge Case, Gap]
  > **Resolved**: `resolve_value()` always applies the tiebreak and returns a single `ResolvedValue` — it never returns a `ValueSet` directly. Callers needing all values call `analyze()` and inspect `value_sets`. Documented in FR-M8-005 and edge cases.

- [x] CHK033 - Are NuGet restore failures distinguished from build compilation failures? [Coverage, Spec §Edge Cases]
  > **Resolved**: Three distinct reasons defined: `"nuget-restore-failed"` (network/package), `"build-failed"` (compilation), `"workspace-load-failed"` (MSBuild project load). Documented in FR-M8-006, `Unresolved` type, and edge cases.

- [x] CHK034 - Is there a defined maximum response size for `IntraRepoFacts`? [Edge Case, Gap]
  > **Resolved**: FR-M8-014 added: responses exceeding 10 MB truncated to top-N most-referenced symbols with `truncated: true` flag. Reflected in `IntraRepoFacts` schema.

---

## Non-Functional Requirements

- [x] CHK035 - Are memory constraints defined for the subprocess? [Non-Functional, Gap]
  > **Resolved**: No hard memory limit in M8 (Roslyn workspace loading is inherently large; any hard limit would be arbitrary). OOM kills the subprocess; bridge treats it as crash-restart. Documented in Assumptions. Operators on constrained hosts use `analyze_timeout_secs` as an indirect bound.

- [x] CHK036 - Are observability requirements specified for bridge logging? [Non-Functional, Gap]
  > **Resolved**: Bridge logs at WARNING on restart with fields: `event="bridge.restart"`, `method`, `attempt`, `binary_path`. Logs at DEBUG per request/response cycle (method name; secret-matching key names excluded). Documented in FR-M8-010 (WARNING on missing binary) and FR-M8-002 (restart logging).

- [x] CHK037 - Is the thread-safety contract specified for queued callers during subprocess restart? [Non-Functional, Spec §FR-M8-001]
  > **Resolved**: Callers queued on the bridge's internal lock block until restart completes. If restart fails, all queued callers receive `SubprocessError(restarted=False)`. At most one restart attempt per error event. Documented in edge cases and FR-M8-001/002.

---

## Dependencies & Assumptions

- [x] CHK038 - Is the assumption that VB.NET `web.config` files are parsed as plain XML validated against the golden fixture? [Assumption, Spec §Assumptions]
  > **Resolved**: Golden fixture already validates XML parsing (it is the M8 acceptance criterion). Assumption confirmed clear and noted in Assumptions section.

- [x] CHK039 - Is the "no multiplexing in M8" constraint documented as an explicit forward-compatibility note? [Assumption, Spec §Assumptions]
  > **Resolved**: Wire Protocol section explicitly states the `id` field is preserved in all messages to enable future multiplexing without a breaking change. M8 behavior (one in-flight at a time) documented without blocking future protocol evolution.

- [x] CHK040 - Is the dependency on M4 clearly scoped with the specific traversal engine entrypoint named? [Dependency, Spec §FR-M8-011, Assumptions]
  > **Resolved**: FR-M8-011 now names the entrypoint: `tendril/core/traversal.py → TraversalEngine._resolve_token()`.

## Notes

- All 40 items resolved. No outstanding gaps.
- Highest-impact resolutions: CHK001 (wire format), CHK003/004 (data schemas), CHK012 (layer precedence), CHK016 (SubprocessError), CHK018 (Unresolved reasons).
- The spec is ready for `/speckit.plan`.
