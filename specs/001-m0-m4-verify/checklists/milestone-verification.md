# Milestone Verification Checklist: M0–M4 Core Implementation — Verify and Complete

**Purpose**: Unit tests for the M0–M4 specification — validates that requirements are
complete, clear, consistent, and falsifiable for both pre-planning review and
post-implementation gate evaluation.
**Created**: 2026-06-14
**Updated**: 2026-06-14 (v2 — all items resolved against spec.md v2)
**Feature**: [spec.md](../spec.md)
**Depth**: Full (pre-planning gate + implementation evaluation gate)
**Focus**: Gap closure falsifiability (dedicated category), requirement completeness,
implementation gate readiness

---

## Requirement Completeness

- [x] CHK001 — Is the golden fixture content scope defined — what specific files, repos,
  and CI/CD data records must be present before M0–M4 acceptance testing can begin?
  [Completeness, Gap]
  > **Resolved**: Added prerequisite block to US1 and expanded Assumptions with explicit
  > `ls tests/fixtures/golden/` confirmation step. Structure (repos, cicd subdirs, SHA)
  > referenced in SC-003 and the new Assumptions fixture-format note.

- [x] CHK002 — Are all seven provider ABCs (VCS, CI/CD, Extractor, IntraRepo, Telemetry,
  GraphStore, LLM) individually named in FR-001 and linked to at least one user story or
  success criterion?
  [Completeness, Spec §FR-001]
  > **Resolved**: FR-001 now explicitly lists all seven ABCs by name and notes that
  > IntraRepo, Telemetry, and LLM MAY carry stub implementations in M0–M4 but MUST
  > exist as real interfaces. US2 covers all seven. Inline `*(covered by USx)*` tags
  > added to every FR.

- [x] CHK003 — Is the `Deployable` vs `Repo` distinction addressed — does the spec require
  that deployables are discovered separately from repos (per critique-plan C3), or does it
  silently default to 1:1?
  [Completeness, Gap]
  > **Resolved**: Added FR-013 specifying the v0 default (1:1 Repo:Deployable) and
  > requiring that multi-deployable repos be explicitly flagged for review rather than
  > silently handled either way.

- [x] CHK004 — Is environment name canonicalization in scope for M0–M4 — does the spec
  define how provider-specific env names (GitHub "production", Octopus "Prod", TeamCity
  "prod") are normalized before the resolver joins?
  [Completeness, Gap]
  > **Resolved**: Added FR-014 specifying case-fold + configurable alias table.
  > Unmatched env names fall back to raw name with `confidence=low` and MUST NOT cause
  > a resolution failure (critique-plan C2 fix).

- [x] CHK005 — Does every functional requirement (FR-001 through FR-012) trace to at least
  one user story acceptance scenario or success criterion in the spec?
  [Completeness, Traceability]
  > **Resolved**: Added `*(covered by USx)*` traceability annotations to all FRs
  > (FR-001 through FR-015). FR-013/014/015 (new) are also annotated.

- [x] CHK006 — Is the scope of "all configured repos" in FR-007 (global reverse index)
  defined — what constitutes the configured scope boundary and who sets it?
  [Completeness, Clarity, Spec §FR-007]
  > **Resolved**: FR-007 updated to define scope as "all repos discoverable via the
  > configured provider credentials at build time." This matches PRD §1 (A1: operator
  > grants read access to every org/workspace they want covered).

---

## Requirement Clarity

- [x] CHK007 — Is "high confidence" defined as a specific enum value or tier rather than a
  relative qualifier — does the spec reference a defined confidence scale?
  [Clarity, Spec §US4]
  > **Resolved**: Added "Defined Terms" section at top of spec with the full confidence
  > scale: `{very_high, high, medium, low, very_low}` with descriptions. US4 and SC-003
  > now reference this scale explicitly.

- [x] CHK008 — Is the distinction between `provenance=injected` and `provenance=declared`
  defined with explicit triggering conditions — when does the resolver produce each?
  [Clarity, Spec §US4, FR-009]
  > **Resolved**: Added Provenance Values to "Defined Terms" with explicit triggering:
  > `declared` = verbatim in committed source config; `injected` = resolved via CI/CD
  > variable store or acquisition ladder. `observed` and `llm-judged` noted as M10/M9
  > scope respectively.

- [x] CHK009 — Is "rung 4 parsing" in FR-008 specified with enough detail to distinguish a
  functioning parser from a no-op stub — what must the parser successfully extract?
  [Clarity, Spec §FR-008]
  > **Resolved**: FR-008 now includes an explicit "Rung 4 closed criterion" block:
  > given a log line `KEY=VALUE`, the parser must return an `AcquisitionResult` with
  > `rung='deploy-log'` and the matched value. A stub logging "not implemented" does
  > NOT satisfy this requirement.

- [x] CHK010 — Is "zero external network calls" in SC-001 defined — does the spec specify
  what constitutes an external call (HTTP, DNS lookup, or both)?
  [Clarity, Spec §SC-001, US1]
  > **Resolved**: SC-001 and US1 now define "zero external network calls" as: no HTTP,
  > HTTPS, or DNS resolution to any host outside localhost during the test run.

- [x] CHK011 — Is the `evidence[]` locator format defined — does the spec specify what
  structure a locator must have (e.g., `file:line`, `store:scope:key`) so
  implementations produce compatible evidence entries?
  [Clarity, Spec §FR-006, FR-009]
  > **Resolved**: Added "Evidence Locator Formats" table to Defined Terms specifying
  > four canonical formats: `{filename}:{line}`, `{provider}:{project}:{env}:{key}`,
  > `{provider}:run-{id}`, `{provider}:build-{id}`. FR-006, FR-009, and US4 reference
  > these formats.

---

## Requirement Consistency

- [x] CHK012 — Is there a latent conflict between US1 being Priority P1 ("all tests pass
  from clean checkout") and the Assumption that "golden fixtures may need to be created"
  — if fixtures do not yet exist, can US1 ever pass?
  [Consistency, Conflict, Spec §US1, §Assumptions]
  > **Resolved**: Added explicit **Prerequisite** block to US1: golden fixtures MUST be
  > committed before US1 is evaluable. US1 Scenario 1 now gates on "AND golden fixtures
  > are present." Assumptions updated with `ls tests/fixtures/golden/` confirmation step
  > and "fixture creation is the first task if absent."

- [x] CHK013 — Does FR-008 (rung 5 browser excluded from M0–M4) align with all other spec
  sections — do the edge cases and assumptions consistently treat rung 5 as out of scope?
  [Consistency, Spec §FR-008, §Edge Cases]
  > **Resolved**: Added explicit edge case: "Rung 5 would be the only remaining option →
  > returns `unresolved-no-source`; rung 5 is not attempted in M0–M4 scope." All three
  > locations (FR-008, edge cases, assumptions) now consistently exclude rung 5.

- [x] CHK014 — Is the `DeployedRef` entity defined consistently between the Key Entities
  section and the US4 acceptance scenarios — do attribute names and required fields match?
  [Consistency, Spec §Key Entities, §US4]
  > **Resolved**: Key Entities - DeployedRef updated with `sha` field definition (hex
  > string ≥ 7 chars) and `source` as a locator string. US4 scenario 2 now explicitly
  > states "`deployed_ref` is the `sha` value of the `DeployedRef` entity." Both sections
  > now use identical field names.

- [x] CHK015 — Does the spec's "optimize for recall" mandate (inherited from the
  constitution) align with how the zero-match edge case is handled — is
  `unresolved-no-source` a recall-preserving outcome or does it suppress traversal?
  [Consistency, Spec §Edge Cases, §FR-009]
  > **Resolved**: Zero-match edge case now explicitly states "This behavior preserves
  > recall — traversal is not blocked by any individual unresolved reference." The
  > unresolved ref goes to build-level `unknowns[]`, not onto an edge (since no target
  > exists), clarifying the structural difference from edge-level unknowns.

---

## Acceptance Criteria Quality

- [x] CHK016 — Is the expected deployed SHA value in SC-003 ("deployed_ref matching the
  fixture SHA") a known constant documented in the spec or fixture reference — or must a
  reviewer look it up elsewhere?
  [Measurability, Spec §SC-003]
  > **Resolved**: SC-003 now pins `deployed_ref = "abc123def456"` (from review.md) and
  > names the fixture file: `tests/fixtures/golden/cicd/octopus/deployments_Projects-1_prod.json`.
  > US4 also states the SHA explicitly.

- [x] CHK017 — Is SC-004 ("every gap closed or documented") measurable — does the spec
  enumerate the exact set of gaps from review.md that must be evaluated, or does it defer
  to review.md as an external source?
  [Measurability, Spec §SC-004]
  > **Resolved**: SC-004 now inlines all three gaps from review.md (Gap 1: M1 conformance
  > subclasses; Gap 2: M4-a rung 4 stub; Gap 3: M4-b loose assertions) with specific
  > "closed when" criteria for each. Review.md is no longer needed to determine what
  > constitutes closure.

- [x] CHK018 — Is SC-006 ("secret value does not appear anywhere") defined with an
  explicit enumeration of "anywhere" — graph store, test output, log files, debug
  CLI output, edge evidence fields?
  [Clarity, Measurability, Spec §SC-006]
  > **Resolved**: SC-006 now enumerates five specific surfaces: graph store node/edge
  > properties, pytest stdout/stderr, tendril CLI stdout/stderr, evidence locator strings,
  > and any file written by the build process.

- [x] CHK019 — Is SC-002 ("four connectors have conformance subclasses") measurable —
  does the spec define what minimum coverage a conformance subclass must provide to count
  as present (e.g., all abstract methods exercised)?
  [Measurability, Spec §SC-002]
  > **Resolved**: SC-002 now states the three-part closure criterion explicitly: (a)
  > subclasses exist, (b) tests execute without error, AND (c) every abstract method is
  > exercised. Also captured in US3 as "M1 gap closure criterion." This matches SC-002
  > (covering every method) but now states that (a) or (b) alone is NOT sufficient.

- [x] CHK020 — Is SC-005 (`tendril providers list` output) specific enough — does the spec
  define what fields (id, family, capabilities, contract version) must appear per listed
  provider?
  [Measurability, Spec §SC-005, FR-012]
  > **Resolved**: FR-012 now specifies the four required output fields per provider:
  > `id`, `family`, `contract_version`, capabilities as key:bool pairs. Also requires
  > `--json` flag support. SC-005 references FR-012 for the field list.

---

## Scenario Coverage

- [x] CHK021 — Is the BFS cycle-detection scenario covered — does the spec require that
  edges are still recorded when a previously-expanded repo is encountered again in
  traversal?
  [Coverage, Gap]
  > **Resolved**: Added BFS cycle edge case: "repo not re-expanded; new edges from this
  > path to the already-expanded repo are still recorded; repo node not duplicated;
  > traversal frontier does not re-enqueue the expanded repo."

- [x] CHK022 — Is the multi-environment scenario covered — does the spec address what a
  graph build for `staging` (not only `prod`) should produce, and whether deployed refs
  differ per environment?
  [Coverage, Gap]
  > **Resolved**: Added multi-environment edge case specifying that each environment
  > produces an independent edge set with its own `deployed_ref` from the env-specific
  > deployment fixture.

- [x] CHK023 — Is the partial attribution scenario specified — does the spec define the
  system's behavior when only the build owner (not the deploy owner) is identifiable for
  a given repo?
  [Coverage, Spec §US5, FR-005]
  > **Resolved**: Added US5 Acceptance Scenario 3: deploy owner not identifiable →
  > `CICDProfile` sets `deploy_owner=null`, `deploy_confidence=low`, records
  > `unattributed-deploy` flag. Run continues at reduced confidence. Also reflected
  > in FR-005.

- [x] CHK024 — Is the empty-extraction scenario covered — does the spec define what the
  traversal produces when no consumer references are found in a repo (empty
  `ConsumerRef[]`)?
  [Coverage, Edge Case, Gap]
  > **Resolved**: Added empty-extraction edge case: repo marked expanded with zero
  > outbound edges, no error raised, repo node exists in graph, build output records
  > `consumer_refs=[]`.

---

## Edge Case Coverage

- [x] CHK025 — Does the spec define what "malformed" means for the deployed-ref edge case
  — is it a missing field, an invalid hash format, an empty string, or all three?
  [Clarity, Edge Case, Spec §Edge Cases]
  > **Resolved**: Edge case now defines "malformed" as any of: (a) `sha` field absent,
  > (b) `sha` field is empty string, (c) `sha` not a valid hex string of ≥ 7 characters.
  > All three trigger the same behavior: `deployed_ref=null` + `stale` flag.

- [x] CHK026 — Is the two-repos-same-provider-identity collision case specified with a
  concrete behavior requirement — does the spec state that both candidates must appear in
  evidence with `ambiguous=true` and `confidence=low`?
  [Edge Case, Spec §FR-007, §Edge Cases]
  > **Resolved**: Edge case enhanced with: each candidate produces a `DEPENDS_ON` edge
  > with `ambiguous=true`, `confidence=low` (regardless of identity class), and a
  > `candidates[]` field listing both matched deployables. DependsOn edge entity in
  > Key Entities updated to include `candidates[]` field.

- [x] CHK027 — Is the "conformance subclass missing an abstract method" edge case
  actionable — does the spec require a collection-time error (not a silent pass), and is
  "collection time" defined?
  [Clarity, Edge Case, Spec §Edge Cases]
  > **Resolved**: Edge case now defines "collection time" as the pytest phase where test
  > classes are discovered and instantiated before any test function executes. States
  > that `TypeError` is raised and command exits non-zero. "No tests silently skipped"
  > is explicit.

- [x] CHK028 — Is the behavior defined when the reverse index lookup returns an empty
  result set (no candidate at all) — does the spec require the consumer ref to enter
  `unknowns[]` rather than being silently dropped?
  [Edge Case, Spec §Edge Cases, FR-009]
  > **Resolved**: Zero-match edge case clarified to distinguish build-level `unknowns[]`
  > (where unresolved ConsumerRefs land) from edge-level `unknowns[]`. No edge is created
  > without a target; the evidence for the unresolved reference is preserved in the
  > build-level output.

---

## Non-Functional Requirements

- [x] CHK029 — Is there a determinism requirement for graph builds — does the spec require
  that repeated builds against the same fixtures produce edges in a stable, reproducible
  order?
  [Gap, NFR]
  > **Resolved**: Added FR-015 specifying deterministic edge ordering: sorted by
  > `from_id`, then `to_id`, then `env`. Repeated builds against the same fixtures MUST
  > produce identical output sequences.

- [x] CHK030 — Is there a performance expectation for the test suite — does the spec define
  an acceptable wall-clock duration for `pytest tests/` to complete against fixtures only?
  [Gap, NFR]
  > **Resolved**: Explicitly deferred with scope boundary. Added to Assumptions: "No
  > wall-clock requirement in M0–M4; reasonable target is under 60 seconds; to be
  > established empirically during M6." This is an intentional deferral, not an omission.

---

## Gap Closure Falsifiability

*This category tests whether the spec's gap-closure requirements are precise enough to
produce an unambiguous binary verdict — the primary quality mandate of this checklist.*

- [x] CHK031 — Is the M1 gap closure criterion specific — does the spec define whether
  the gap is closed by (a) test subclasses existing in the file system, (b) those tests
  executing without error, or (c) all abstract methods of the connector ABCs being
  exercised?
  [Falsifiability, Spec §SC-002, §US3]
  > **Resolved**: US3 now has an explicit "M1 gap closure criterion" block stating all
  > three conditions must hold. SC-002 updated to state "(a) or (b) alone is NOT
  > sufficient." The answer is (c) = all three conditions, not just existence or passing.

- [x] CHK032 — Is the M4 rung-4 gap closure criterion actionable — does the spec specify
  what the deploy-log parser must successfully extract from a log entry (key=value
  pattern? specific format?) to confirm the stub is replaced?
  [Falsifiability, Spec §FR-008]
  > **Resolved**: FR-008 now includes a "Rung 4 closed criterion" block with a concrete
  > example: given `LandingPageUrl=https://d-ui.prod.example.com` in a log line, parser
  > returns `AcquisitionResult(rung='deploy-log', value=...)`. Named format: KEY=VALUE.

- [x] CHK033 — Is the M4 "loose assertions" gap closure enumerated — does the spec list
  the exact edge fields (provenance, confidence, deployed_ref, evidence[], unknowns[])
  that the end-to-end test must assert, rather than leaving "tight" undefined?
  [Falsifiability, Spec §US4, §SC-003]
  > **Resolved**: SC-003 now enumerates 8 specific assertions that MUST ALL be made.
  > US4 Scenario 1 lists the same fields with exact expected values. "Asserting only edge
  > existence does NOT satisfy this criterion" stated explicitly in both places.

- [x] CHK034 — Is SC-004 itself falsifiable — is the complete set of review.md gaps
  enumerated directly in the spec so a reviewer can evaluate closure without reading
  review.md as an external dependency?
  [Falsifiability, Spec §SC-004]
  > **Resolved**: SC-004 now inlines all three gaps with their "closed when" criteria
  > (see CHK017). review.md is no longer required to evaluate SC-004 closure. The spec
  > is self-contained for PR review (noted in the header).

- [x] CHK035 — Is the "no assumptions on accuracy" mandate operationalized — does the spec
  require running specific commands (e.g., `pytest`) to verify completion rather than
  trusting prior documentation such as review.md's ✅ markers?
  [Falsifiability, Spec §Assumptions]
  > **Resolved**: Assumptions now includes a per-milestone command table: M0 through M4
  > each have a specific `pytest` command that constitutes verification. review.md ✅
  > markers are not accepted as verification.

- [x] CHK036 — Is there a definition of "milestone complete" — does the spec state when
  M1 or M4 transitions from partially complete to done (all tests pass? zero gap items
  remaining? specific command succeeds?)?
  [Falsifiability, Gap]
  > **Resolved**: Added "Milestone Completion Criteria" section at end of spec. Complete
  > = verification command exits code 0 with zero failures on fixture data only. "Partially
  > complete" is explicitly not a valid completion state. Gap items not closed MUST be
  > documented as deferred with a scope boundary.

---

## Dependencies & Assumptions

- [x] CHK037 — Is the assumption that "conformance base classes already exist" validated
  against a concrete file path (e.g., `tests/conformance/`) rather than inferred from
  review.md, whose accuracy the spec explicitly does not assume?
  [Assumption, Spec §Assumptions]
  > **Resolved**: Assumptions now states that before building conformance subclasses, the
  > plan phase MUST verify existence of `tests/conformance/test_vcs_provider.py` and
  > `tests/conformance/test_cicd_provider.py` and identify the required abstract methods.
  > File paths named explicitly; not derived from review.md.

- [x] CHK038 — Is the golden fixture dependency gated — does the spec specify that
  fixture existence must be confirmed before US4 acceptance testing begins, and how that
  confirmation is performed?
  [Dependency, Spec §Assumptions]
  > **Resolved**: US1 Prerequisite block and Assumptions now both state `ls
  > tests/fixtures/golden/` as the confirmation mechanism. If absent, fixture creation
  > is the first task before any other US4 work proceeds.

- [x] CHK039 — Is the fixture format (JSON structure, field names, nesting) documented as
  a dependency — or left for implementations to discover by reading connector source code?
  [Dependency, Gap]
  > **Resolved**: Assumptions now states that fixture format follows the JSON structure
  > implied by connector implementations and that "the plan phase MUST document the
  > expected fixture schemas before implementation begins." Explicitly deferred to plan
  > phase with a gate.

- [x] CHK040 — Is the "38 tests pass" baseline from CLAUDE.md reconciled with the spec —
  does the spec define what the expected test count is, and what happens if the actual
  count differs on a clean checkout?
  [Assumption, Spec §Assumptions]
  > **Resolved**: Assumptions updated: "38 tests pass" MUST be verified via
  > `pytest tests/ --collect-only` before changes. If actual count differs, that count
  > becomes the new baseline. FR-011 updated to "≥ 38" and SC-001 updated to "≥ 38."

---

## Implementation Gate Readiness

- [x] CHK041 — Are the US4 acceptance scenarios specific enough to write precise test
  assertions without consulting review.md or critique-plan.md — do they name exact field
  names, enum values, and expected data types?
  [Implementation Gate, Spec §US4]
  > **Resolved**: US4 Scenario 1 now specifies: exact `from_id` and `to_id` strings,
  > `env="prod"`, `provenance="injected"` (with reference to Defined Terms),
  > `confidence="high"` (with reference to Defined Terms), `deployed_ref="abc123def456"`,
  > minimum evidence entry count (≥ 3) and what each must reference, and `unknowns=[]`.
  > All values are implementation-testable without consulting external documents.

- [x] CHK042 — Can a PR reviewer determine from this spec alone (without consulting
  review.md, critique-plan.md, or CLAUDE.md) what a passing M0–M4 implementation looks
  like?
  [Implementation Gate, Gap]
  > **Resolved**: Gaps from review.md inlined into SC-004; verification commands moved
  > into Assumptions; fixture SHA pinned in SC-003 and US4; Defined Terms block provides
  > all enum values. Header now states "Self-contained note: All facts cited from
  > review.md are inlined below." A PR reviewer needs only this spec.

---

## Notes

- All 42 items resolved in spec.md v2 (2026-06-14). No items remain open.
- Items marked [x] include the specific spec location and change made.
- Most impactful changes for implementation correctness:
  - CHK007/CHK008/CHK011: Defined Terms block (confidence scale, provenance values,
    evidence locator formats) — resolves the "undefined enum" class of bugs
  - CHK031/CHK032/CHK033: Gap closure criteria are now binary and testable
  - CHK012: US1 P1 conflict resolved by adding a fixture prerequisite gate
  - CHK017/CHK034: SC-004 is now self-contained (no external review.md lookup needed)
- CHK030 (performance NFR) is the only item explicitly deferred to M6 with a boundary.
- Items marked [Gap] that were added to spec: FR-013, FR-014, FR-015, edge cases for
  BFS cycles / multi-env / empty extraction / rung 5 / partial attribution.
