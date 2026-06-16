# Spec Review Checklist: M9 — LLM Hybrid Mode

**Purpose**: Formal peer-review gate — validates that the M9 specification is complete, clear, consistent, and measurable before planning begins. Tests the quality of requirements, not the implementation.
**Created**: 2026-06-15
**Updated**: 2026-06-15 (post spec-review walkthrough)
**Feature**: [spec.md](../spec.md)
**Depth**: Formal peer-review gate
**Audience**: Peer reviewer / plan author sign-off

---

## Requirement Completeness

- [x] CHK001 — Are requirements defined for all three mode-activation surfaces (CLI flag, config file, environment variable) including the precedence order between them? [Completeness, Spec §FR-001]
- [x] CHK002 — Is the content and structure of the "goal description" component of the LLM cache key defined precisely, or is it left to implementer interpretation? [Completeness, Spec §FR-011] *(Resolved: canonical format `<DECISION_TYPE>:<primary_identifier>` defined in FR-011)*
- [x] CHK003 — Are the three prompt contract types (AMBIGUOUS_MATCH, UNRESOLVED_REF, IDENTITY_CLASS) each specified with their required input fields and output schema, or only named? [Completeness, Spec §FR-019] *(Resolved: input/output fields specified in FR-019)*
- [x] CHK004 — Are requirements defined for what happens when the response cache directory is inaccessible at build time (read-only filesystem, missing path)? [Completeness, Spec §FR-011] *(Resolved: log warning, proceed without caching, build does not fail — added to FR-011)*
- [x] CHK005 — Are requirements defined for what the LLM judge's read-only lookup tools return on failure (e.g., identity not found, index error), or only for the happy path? [Completeness, Spec §FR-018] *(Resolved: index errors treated as grounding failures → FR-007 path; added to Edge Cases)*
- [x] CHK006 — Is the scenario where the structured pass produces zero unresolved/ambiguous items (nothing for the LLM pass to do) addressed in requirements? [Completeness, Edge Case] *(Resolved: added to Edge Cases — LLM pass exits immediately)*

---

## Requirement Clarity

- [x] CHK007 — Is "PII pattern" defined with specific, enumerable detection criteria, or is it left to implementation interpretation? [Clarity, Spec §FR-005] *(Resolved: email addresses, phone numbers, conventional identity field names enumerated in FR-005)*
- [x] CHK008 — Is the "goal description" in the cache key defined precisely enough to guarantee cache hits are deterministic across different build environments? [Clarity, Spec §FR-011] *(Resolved: see CHK002)*
- [x] CHK009 — Is "sorted set of evidence locators" defined with a canonical sort key (e.g., lexicographic by path:line) to prevent non-deterministic cache misses? [Clarity, Spec §FR-011] *(Resolved: lexicographic sort on `<source_type>:<path_or_key>:<line_or_scope>` defined in FR-011)*
- [x] CHK010 — Is `confidence=low` for LLM-judged edges defined in relation to the existing confidence scale (high / medium / low) established in M0–M4? [Clarity, Spec §FR-008] *(Resolved: FR-008 now explicitly references the three-tier scale and states LLM-judged edges cannot be promoted above `low`)*
- [x] CHK011 — Is "re-resolved" defined precisely enough to determine exactly when a reasoning trace should be replaced versus retained? [Clarity, Spec §FR-015] *(Clear: any subsequent build where the item goes through the LLM pass triggers replacement)*
- [x] CHK012 — Is the `rate-limited` warning class defined with a specific structured log field or format, or is it described only in narrative terms? [Clarity, Spec §FR-014] *(Deferred to planning — skip-reason taxonomy in spec now defines the marker name; log format is an implementation detail)*
- [x] CHK013 — Is the `[REDACTED]` placeholder string specified, or could different implementations choose different strings and break test assertions? [Clarity, Security, Spec §FR-004] *(Resolved: exact string `[REDACTED]` locked in FR-004)*
- [x] CHK014 — Is "exceeds the evidence budget" defined as always skipping the item entirely, or is partial evidence submission permitted? [Clarity, Spec §FR-017] *(Clear: skip entirely, not truncate)*

---

## Requirement Consistency

- [x] CHK015 — Is FR-013 (fallback to structured mode when LLM config absent) consistent with User Story 3, Scenario 2 — do both specify identical fallback outcomes and log behaviour? [Consistency, Spec §FR-013, US-3] *(Consistent)*
- [x] CHK016 — Is the `ambiguous=True` flag in FR-009 defined consistently with the existing meaning of `ambiguous=True` established in M4/M7 structured mode? [Consistency, Spec §FR-009] *(Resolved: FR-009 now cross-references M4/M7 definition)*
- [x] CHK017 — Could a cache hit from a prior build cause a stale reasoning trace to persist after an edge is re-resolved in a new build? Are FR-011 (cache) and FR-015 (trace replacement) consistent with each other? [Consistency, Conflict, Spec §FR-011, FR-015] *(Resolved: FR-011 now explicitly states "grounding always re-runs against the current index, even on cache hits" — no stale trace risk)*
- [x] CHK018 — Are the new provenance values (`llm-judged`, `unresolvable-redacted`, `rate-limited`) consistent with the existing provenance taxonomy (`declared`, `injected`, `observed`) defined in M0–M4? [Consistency, Spec §FR-008] *(Resolved: FR-008 now explicitly registers `llm-judged` as an extension to the existing taxonomy with the same query-contract obligations)*
- [x] CHK019 — Does the spec consistently distinguish between items the LLM pass skips (due to secrets/PII/timeout/rate-limit) and items that remain genuinely unresolvable? [Consistency, Gap] *(Resolved: Skip-Reason Taxonomy table added to Requirements section)*

---

## Acceptance Criteria Quality

- [x] CHK020 — Is SC-001 ("resolve at least half of unknowns") achievable against the current golden fixture, or does it require a new fixture with a known set of unresolved items to be created first? [Measurability, Spec §SC-001] *(Resolved: Assumptions now explicitly states a new M9 test fixture must be created; existing golden fixture is insufficient)*
- [x] CHK021 — Is SC-004 ("zero new LLM requests on second build") objectively verifiable without implementation knowledge — is the cache-hit metric observable from outside the system? [Measurability, Spec §SC-004] *(Acceptable: "as verified by the cache hit log" — the cache hit log is a required observable output per FR-011)*
- [x] CHK022 — Is SC-002 ("zero secret values in any LLM request payload") defined with a specific observation mechanism, or does it presuppose access to internal request logs? [Measurability, Spec §SC-002] *(Clear: "test inspection of the request log" — request logging is a standard test-mode capability)*
- [x] CHK023 — Can SC-006 ("explain_edge returns redacted evidence and LLM reasoning") be verified without knowing the internal storage format of the reasoning trace? [Measurability, Spec §SC-006] *(Clear: explain_edge is a defined query contract)*
- [x] CHK024 — Does SC-007 ("M0–M8 test suite passes unchanged") provide a sufficient isolation guarantee, or should it also include a check that no M9 code paths execute during a structured-mode build? [Acceptance Criteria, Spec §SC-007] *(Sufficient: if no M9 imports are present in the structured path, SC-007 guarantees isolation)*

---

## Scenario Coverage

- [x] CHK025 — Are requirements defined for the processing order when the structured pass produces a mix of `unresolved` and `ambiguous` items — does the LLM pass handle them in a defined sequence? [Coverage] *(Acceptable: sequential processing per Concurrency section; order does not affect correctness)*
- [x] CHK026 — Are requirements defined for what happens if two or more hybrid-mode build processes run concurrently and attempt to write to the same cache directory simultaneously? [Coverage] *(Resolved: Concurrency section states sequential-only in v0; concurrent multi-process cache writes are out of scope)*
- [x] CHK027 — Is the scenario where the reverse index lookup itself fails (index unavailable or returns an error) during the grounding step addressed in requirements? [Coverage, Exception Flow] *(Resolved: added to Edge Cases — treated as grounding failure, no edge written, logged)*
- [x] CHK028 — Is the scenario where hybrid mode is requested but the CLI flag, config, and env var all specify different values addressed — does the precedence rule cover all three simultaneously? [Coverage, Spec §FR-001] *(Clear: FR-001 precedence is total ordering across all three surfaces)*

---

## Edge Case Coverage

- [x] CHK029 — Is the scenario where the LLM config is partially complete (e.g., endpoint set but API key absent) addressed, or does FR-013 only cover fully absent config? [Edge Case, Spec §FR-013] *(Resolved: added to Edge Cases — partial config treated identically to absent config)*
- [x] CHK030 — Does the spec define requirements for the case where the LLM returns a structurally valid response but with a semantically empty candidate (e.g., empty string, null)? [Edge Case, Spec §FR-014] *(Resolved: added to Edge Cases — treated as malformed output)*
- [x] CHK031 — Are requirements defined for redaction of secret values that appear embedded within a non-secret field (e.g., a URL string containing a token)? [Edge Case, Security, Spec §FR-004] *(Resolved: FR-004 now covers embedded occurrences in non-secret fields)*
- [x] CHK032 — Is the case where PII markers appear in the goal description string (not in evidence) addressed by the residency gate requirements? [Edge Case, Security, Spec §FR-005] *(Resolved: FR-005 now explicitly includes the goal description string in the scan scope)*

---

## Non-Functional Requirements

- [x] CHK033 — Are concurrency requirements defined for the LLM pass — must unresolved items be processed sequentially, or may they be parallelised? [Non-Functional] *(Resolved: Concurrency section states sequential-only in v0)*
- [x] CHK034 — Are observability requirements defined beyond "log a warning" — e.g., required log levels, structured log fields, or metrics counters for cache hits/misses/skips? [Non-Functional, Gap] *(Resolved during implementation: log levels are WARNING for skips/errors/gate-blocks, INFO for accepted edges, DEBUG for cache hits. All LLM-related log messages use the `tendril.llm.judge` logger. Skip-reason taxonomy (`budget-exceeded`, `rate-limited`, `llm-error`, `grounding-failed`, `unresolvable-redacted`) is persisted on each unresolved item dict and observable via the returned TraversalResult. No separate metrics counters in v0 — the unresolved list + log output is the observable.)*
- [x] CHK035 — Is the total expected duration impact of the LLM pass on a build bounded in the spec — e.g., a maximum acceptable wall-clock addition? [Non-Functional, Gap] *(Resolved during implementation: wall-clock bound = N_unresolved × timeout_seconds (default 60s). For a typical build with 0–50 unresolved items and sequential processing, the upper bound is 50 × 60 = 3000s; the practical bound is much lower because most items hit the cache after the first build (SC-004). No spec-level wall-clock SLO is added for v0 — the per-call timeout is the operative bound, and sequential processing makes it predictable.)*

---

## Dependencies & Assumptions

- [x] CHK036 — Is the assumption that the reverse index is "fully populated" before the LLM pass validated against the M4 build sequence — what is the behaviour if index population was partial or failed? [Assumption] *(Addressed: partial index = all affected proposals fail grounding → no edges written; documented in Assumptions)*
- [x] CHK037 — Is the dependency on M5's `explain_edge` query path specified with enough detail to determine whether M5 needs any modification to support M9's `llm_trace` field? [Dependency] *(Resolved: Assumptions now notes M5 requires a minor extension to surface `llm_trace`, documented as a dependency touch)*
- [x] CHK038 — Is the assumption that the OpenAI Chat Completions API format covers all intended self-hosted model endpoints explicitly validated, or is it left as an untested assumption? [Assumption] *(Resolved: Assumptions now explicitly marks this as untested and recommends operator validation)*

---

## Deferred / Future Work Traceability

- [x] CHK039 — Is the deferral of retry-with-back-off for 429 responses documented in the spec with a clear rationale, not just in the clarification log? [Deferred, Spec §FR-014] *(Resolved: v0 scope decision added to Assumptions with rationale and future trigger)*
- [x] CHK040 — Is the exclusion of trace audit history (accumulation across builds) documented as an explicit v0 scope decision in the spec body, or does it only appear in the clarification session? [Deferred] *(Resolved: v0 scope decision added to Assumptions)*
- [x] CHK041 — Is the pattern-based PII detection approach documented as a deliberate v0 constraint in the spec, with a note on what conditions would trigger upgrading to a more robust approach? [Deferred] *(Resolved: v0 scope decision added to Assumptions with upgrade trigger)*

---

## Notes

- Check items off as completed: `[x]`
- Add inline findings as sub-bullets under failing items
- CHK034 and CHK035 are intentionally left open — both are deferred to planning and do not block the plan
- All other items resolved. Spec is ready for `/speckit.plan`
