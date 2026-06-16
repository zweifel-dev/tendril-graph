# Feature Specification: M9 — LLM Hybrid Mode

**Feature Branch**: `004-m9-llm-hybrid-mode`

**Created**: 2026-06-15

**Status**: Draft

**Input**: Create detailed spec for M9 of the tendril-graph plan — LLM hybrid mode.

---

## Background & Context

Tendril-Graph's structured analysis (M0–M8) deterministically extracts dependency edges from source code, CI/CD config, and deployment metadata. It is the default and permanent fast path. However, some real-world cases resist deterministic resolution:

- A config token's value cannot be found in any readable store (secret-typed or unreadable variable).
- Two or more provider repos match the same identity value and the system cannot choose without broader reasoning.
- A reference pattern is non-standard and falls outside the extractors' vocabulary.

M9 introduces an **optional LLM-assisted pass** that runs after the structured pass and only addresses what the structured pass could not resolve. The LLM never replaces the structured path; it augments it — and every LLM proposal must be verified against the known graph before it can become an edge.

---

## Clarifications

### Session 2026-06-15

- Q: How does an operator enable hybrid mode? → A: All three surfaces — CLI flag `--mode hybrid`, config file key, and environment variable — with precedence flag > config > env var.
- Q: What is the per-call timeout for LLM requests? → A: 60-second default, configurable per deployment.
- Q: How should LLM rate-limit responses (HTTP 429) be handled? → A: Surface as distinct `rate-limited` warning class, skip item, return structured results — no retry in v0. Retry with exponential back-off is a future consideration.
- Q: Where is the LLM response cache persisted between builds? → A: Separate configurable path, defaulting to `~/.tendril/llm-cache/`; independent of the graph DB directory.
- Q: What is the lifecycle of reasoning traces? → A: Tied to the edge — replaced when the edge is re-resolved; no accumulation across builds.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Reduce Unknowns Without Sacrificing Accuracy (Priority: P1)

A graph consumer (an AI coding agent or a developer) queries the dependency graph and receives results that include "unknowns" — cases where the system couldn't determine whether a dependency exists. With hybrid mode enabled, the system re-examines those unknowns using LLM reasoning, grounded against what is already known in the graph, and resolves some of them into confirmed or tentative edges — reducing the unknown set without inventing edges.

**Why this priority**: The primary value proposition of M9 is coverage improvement. Reducing unknowns is the user-visible outcome.

**Independent Test**: Enable hybrid mode, run a graph build against the golden fixture where at least one dependency is currently unresolved. Verify the number of unknowns decreases and at least one new edge appears — and that edge can be traced back to a grounded LLM proposal.

**Acceptance Scenarios**:

1. **Given** a graph build in structured mode produces an edge marked `ambiguous=True` with two candidate repos, **When** hybrid mode is enabled and the graph build re-runs, **Then** the LLM reasons over the candidates and either (a) confirms both remain genuinely ambiguous and keeps `ambiguous=True`, or (b) grounds one candidate as clearly matching and promotes it — but never silently auto-picks without grounding evidence.

2. **Given** a config token whose value cannot be read from any CI/CD variable store in structured mode, **When** hybrid mode is enabled, **Then** the LLM may propose a candidate identity based on contextual evidence, which is then looked up in the reverse index; if found, the edge is written with `provenance=llm-judged` and `confidence=low`; if not found in the index, the edge is not written and the token remains an unknown.

3. **Given** the LLM returns a candidate that does not exist anywhere in the indexed provider identities, **When** the grounding step runs, **Then** the candidate is rejected, no edge is written, and the unknown remains flagged in the unknowns list.

---

### User Story 2 — Secret Safety and Data Residency (Priority: P1)

An operator enables hybrid mode but is concerned that internal secrets, credentials, or personally identifiable information in the evidence corpus might be sent to an external LLM service. They need a guarantee that this will never happen, and that the system degrades gracefully rather than leaking data.

**Why this priority**: A data-safety failure in M9 would be a hard blocker for any enterprise adoption. This is co-equal with P1 for coverage.

**Independent Test**: Inject a secret-typed variable value into the evidence set (marked `is_secret=True`). Enable hybrid mode with a mock LLM. Verify the LLM mock is called with evidence that does not contain the secret value — the secret is replaced with a placeholder such as `[REDACTED]`.

**Acceptance Scenarios**:

1. **Given** evidence for an unresolved token includes a variable entry with `is_secret=True`, **When** the LLM call is prepared, **Then** the secret value is replaced with `[REDACTED]` before the payload is constructed, and the raw value never appears in any LLM request payload, log, or trace output.

2. **Given** evidence contains a field that matches a PII pattern (e.g., an email address or personal name), **When** the residency gate evaluates the evidence, **Then** the LLM call is blocked entirely, the token remains as an unresolved unknown, and the block is logged with a reason code (`blocked-pii-detected`).

3. **Given** the LLM call is blocked due to PII or secret-redaction policy, **When** the graph build completes, **Then** the overall graph build does not fail — the structured results are returned as-is and the blocked item appears in the unknowns list with an `unresolvable-redacted` marker.

---

### User Story 3 — Configurable LLM Provider (Bring Your Own Key) (Priority: P2)

An operator configures which LLM provider and endpoint the hybrid mode uses. They may want to use a self-hosted model, an internal enterprise gateway, or a cloud provider — and must be able to change this without modifying core code. Operators at security-sensitive organizations need the option to use a locally-hosted model with zero data egress.

**Why this priority**: Vendor lock-in would block the feature for most enterprise targets. BYOK and self-hosted support are load-bearing for adoption.

**Independent Test**: Configure the system to point at a local mock LLM endpoint. Enable hybrid mode. Verify that all LLM calls go to the configured endpoint and that disabling/removing the configuration silently falls back to structured-only mode.

**Acceptance Scenarios**:

1. **Given** a configuration specifying an OpenAI-compatible endpoint, model name, and API key, **When** hybrid mode processes an unresolved item, **Then** the HTTP request is sent to the configured endpoint (not any hardcoded vendor) and uses the configured model.

2. **Given** no LLM configuration is present, **When** a graph build runs with hybrid mode selected, **Then** the system silently falls back to structured mode, a warning is logged that hybrid mode requires LLM configuration, and the graph build completes successfully with structured-only results.

3. **Given** the configured LLM endpoint is unreachable (network error or timeout), **When** a hybrid-mode graph build runs, **Then** the LLM pass is skipped for affected items, a warning is logged with the failure reason, and the structured results are returned without failure.

---

### User Story 4 — Transparent Provenance and Confidence (Priority: P2)

A developer reviewing the dependency graph needs to understand which edges were produced by deterministic structured analysis versus which were inferred by LLM reasoning. They can then apply appropriate skepticism to LLM-judged edges and investigate unknowns that the LLM could not resolve.

**Why this priority**: Without clear provenance labeling, consumers cannot distinguish trusted edges from tentative ones. This directly affects how agents and developers use the graph.

**Independent Test**: Run a hybrid-mode build. Query the resulting graph. Verify that every LLM-contributed edge carries `provenance=llm-judged` and `confidence=low`. Verify that structured edges retain their original provenance and confidence labels unchanged.

**Acceptance Scenarios**:

1. **Given** an edge was resolved by the LLM (not by the structured pass), **When** a consumer queries that edge, **Then** the edge carries `provenance=llm-judged`, `confidence=low`, and an `llm_trace` field pointing to the reasoning log.

2. **Given** an edge was resolved by the structured pass, **When** a consumer queries that edge after a hybrid-mode build, **Then** the edge's provenance and confidence are unchanged from what structured mode would have produced.

3. **Given** the LLM grounds a candidate and confirms it matches a known provider identity, **When** the edge is written, **Then** the evidence list includes both the original contextual evidence and the grounding result (which reverse-index entry matched and why).

---

### User Story 5 — Reproducible Results Across Re-Runs (Priority: P2)

An operator or CI pipeline runs hybrid-mode graph builds repeatedly. They expect the same graph to be produced each time given the same inputs — LLM calls must not introduce randomness or non-determinism into the output.

**Why this priority**: Non-deterministic graphs break diffing, auditing, and agent reliability. This is a hard requirement for CI use.

**Independent Test**: Run a hybrid-mode build twice against the same fixture. Compare the resulting edge sets. Assert they are identical, including edge provenance, confidence, and LLM trace references.

**Acceptance Scenarios**:

1. **Given** a hybrid-mode build runs twice with identical inputs, **When** the results are compared, **Then** the edge sets, provenance labels, confidence values, and unknowns lists are identical between runs.

2. **Given** an LLM call was cached from a previous run, **When** the same question (same goal + same evidence locators) is asked again, **Then** the cached response is returned without issuing a new LLM request, and the result is identical to the previous run.

3. **Given** the LLM cache is cleared, **When** a re-run occurs, **Then** new LLM calls are made, but because the LLM is called at temperature=0, the responses are deterministic at the provider level, and the resulting graph is still identical.

---

### User Story 6 — Explainability of LLM-Judged Edges (Priority: P3)

A developer wants to understand why a specific LLM-judged edge exists. They can retrieve the reasoning trace that the LLM produced when it proposed the candidate, which allows them to verify the inference or decide to override it.

**Why this priority**: Explainability is critical for trust but can be built on top of the core mechanism; reasoning traces are already stored as part of edge evidence.

**Independent Test**: After a hybrid-mode build, call the `explain_edge` query for an LLM-judged edge. Verify the response includes the LLM's reasoning trace, which grounding entry confirmed it, and the provenance chain.

**Acceptance Scenarios**:

1. **Given** an edge with `provenance=llm-judged`, **When** `explain_edge` is called, **Then** the response includes: the structured evidence that prompted the LLM call, the LLM's stated reasoning, the grounding result that confirmed the candidate, and the final confidence/provenance values.

2. **Given** the LLM was called but its candidate failed grounding, **When** the user inspects the unknowns list, **Then** the unknown entry includes the LLM's proposed candidate and a note explaining that the candidate was not found in the provider index.

---

### Edge Cases

- What happens when the LLM is called for an item the structured pass marked `unresolved-secret`? → The call must be blocked since the secret value cannot be included in evidence; the item remains `unresolved-secret`.
- What happens when all unresolved items in a build contain PII-flagged evidence? → All LLM calls are blocked, the build succeeds with the full structured output, and all items remain in the unknowns list.
- What happens when the LLM proposes the same candidate that the structured pass already evaluated as a partial match? → The grounding step runs against the full reverse index; if the proposal is grounded and the match is confirmed, the confidence may be promoted with `provenance=llm-judged`; otherwise the item stays as an unknown.
- What happens when the LLM produces malformed output (not conforming to the expected schema)? → The response is discarded, the item stays as an unknown, and the failure is logged with the raw response for debugging.
- What happens when an LLM call exceeds the configured timeout (default 60 seconds)? → The call is abandoned, the item is treated the same as any other LLM error (FR-014): skipped, logged, returned as an unknown in structured results.
- What happens when the LLM provider returns HTTP 429 (rate limited)? → The item is skipped and logged with warning class `rate-limited` (distinct from general errors); no retry is attempted in v0. Retry with exponential back-off is a future enhancement.
- What happens when the reverse index has not been populated (empty repo scope)? → No grounding is possible; all LLM proposals fail grounding and no LLM-judged edges are written.
- What happens when the number of unresolved items exceeds the evidence budget? → Each call is bounded by the configured maximum file count and byte budget; items that exceed the budget are queued as unknowns rather than causing oversized requests.
- What happens when the LLM reasons that both candidates in an ambiguous match are valid? → `ambiguous=True` is kept on both candidate edges, the LLM reasoning is recorded in the trace, and no auto-pick occurs.
- What happens when the LLM config is partially complete (e.g., endpoint URL set but API key absent)? → Treated identically to fully absent config (FR-013): the system falls back to structured mode, logs a warning indicating which required field is missing, and completes successfully.
- What happens when the LLM returns a structurally valid response containing an empty or null candidate value? → Treated as malformed output: the response is discarded, the item stays as an unknown, and the failure is logged with the raw response.
- What happens when the reverse index lookup itself errors during grounding (e.g., index unavailable or returns an unexpected error)? → The grounding step fails, the candidate is treated as ungrounded (same as not-found per FR-007), no edge is written, and the error is logged. The item remains in the unknowns list.
- What happens when the LLM pass runs and there are zero unresolved or ambiguous items? → The LLM pass exits immediately with no calls made, no cache reads, and no changes to the graph. The build completes normally.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a `hybrid` graph build mode in addition to the existing `structured` mode; `structured` MUST remain the default and must be fully functional with no dependency on M9. Hybrid mode MUST be activatable via three surfaces — CLI flag (`--mode hybrid`), config file key, and environment variable — with precedence order: CLI flag overrides config file, config file overrides environment variable.
- **FR-002**: In hybrid mode, the structured analysis pass MUST run first and to completion before any LLM call is made.
- **FR-003**: The LLM pass MUST only process items that the structured pass marked as `unresolved` or `ambiguous`; it MUST NOT re-process items already resolved by the structured pass.
- **FR-004**: Before any LLM request is constructed, the system MUST redact all evidence fields that are secret-typed, replacing their values with the fixed placeholder string `[REDACTED]`; the original value MUST NOT appear in any LLM request, log, or trace output. Redaction applies to the literal value of a secret field AND to occurrences of that value embedded within non-secret fields (e.g., a secret token appearing inside a URL string in a non-secret evidence field).
- **FR-005**: Before any LLM request is constructed, the system MUST run a residency gate that scans both the evidence fields AND the goal description string for PII markers; if PII is detected in either, the LLM call MUST be blocked and the item MUST remain as an unknown with marker `unresolvable-redacted`. PII markers include at minimum: email addresses (matching standard email format), phone numbers, and field names that conventionally carry personal identity (`user`, `author`, `owner`, `email`, `name`, `contact`). The residency gate runs after secret redaction; it evaluates the post-redaction payload.
- **FR-006**: Every LLM proposal MUST be verified ("grounded") by looking up the proposed value in the provider identity reverse index before any edge is written.
- **FR-007**: If a proposed candidate is not found in the provider identity index after grounding, the candidate MUST be rejected; no edge is written; the item remains in the unknowns list with the failed proposal noted.
- **FR-008**: If a proposed candidate is found in the index after grounding, an edge MUST be written with `provenance=llm-judged` and `confidence=low`. `low` here maps to the lowest tier of the existing three-tier confidence scale (high / medium / low) established in M0–M4; LLM-judged edges MUST NOT be promoted above `low` by the grounding step alone. `llm-judged` is an addition to the existing provenance taxonomy (`declared`, `injected`, `observed`) and carries the same query-contract obligations: every edge with this provenance MUST include evidence, deployed_ref, and an unknowns entry if applicable.
- **FR-009**: For ambiguous matches, the LLM MUST NOT auto-pick among candidates; if the LLM confirms multiple candidates are valid, `ambiguous=True` MUST be kept on all candidate edges and the LLM reasoning MUST be recorded in each edge's trace. `ambiguous=True` here carries the same meaning as defined in M4/M7 structured mode: the system has identified multiple plausible target deployables for a single consumer reference and cannot select one without additional grounding evidence.
- **FR-010**: All LLM calls MUST be made with a deterministic temperature setting (temperature = 0) to ensure reproducibility.
- **FR-011**: The system MUST cache LLM responses keyed on the combination of the goal description and the sorted set of evidence locators, defined as follows:
  - **Goal description**: A canonical string of the form `<DECISION_TYPE>:<primary_identifier>`, where `DECISION_TYPE` is one of `AMBIGUOUS_MATCH`, `UNRESOLVED_REF`, or `IDENTITY_CLASS`, and `primary_identifier` is the consumer reference identifier (for AMBIGUOUS_MATCH and UNRESOLVED_REF) or the identity value being classified (for IDENTITY_CLASS).
  - **Evidence locators**: The set of evidence locator strings for the item, sorted lexicographically by their canonical representation (`<source_type>:<path_or_key>:<line_or_scope>`). All locators MUST be included in sorted order to guarantee a stable cache key across build environments.
  - Subsequent calls with an identical (goal description, sorted evidence locators) pair MUST return the cached LLM response without issuing a new network request.
  - **Grounding always re-runs**: The cache stores only the raw LLM response. The grounding step (FR-006) MUST re-execute against the current state of the reverse index on every build, including on cache hits. A cache hit does not bypass grounding.
  - The cache MUST be persisted to disk at a configurable path (default: `~/.tendril/llm-cache/`) so that responses survive between separate build invocations. Clearing or deleting this directory MUST invalidate all cached responses.
  - If the cache directory is inaccessible (missing, read-only, or corrupt) at build time, the system MUST log a warning and proceed without caching — LLM calls are made and grounded normally, but responses are not persisted. The build MUST NOT fail due to cache unavailability.
- **FR-012**: The LLM provider endpoint, model identifier, and authentication credentials MUST be fully configurable at deployment time; no model vendor or endpoint MUST be hardcoded.
- **FR-013**: If no LLM configuration is present when hybrid mode is requested, the system MUST silently fall back to structured mode, log a warning, and complete the build successfully.
- **FR-014**: If the LLM endpoint is unreachable, returns an error, or does not respond within the configured timeout (default: 60 seconds), the system MUST skip the LLM pass for affected items, log the error with failure reason, and return structured results without failure. The per-call timeout MUST be configurable at deployment time. Rate-limit responses (HTTP 429) MUST be treated as a distinct warning class (`rate-limited`), logged separately from general errors, and handled the same way as other failures — skip item, return structured results — with no retry in v0.
- **FR-015**: Every edge written by the LLM pass MUST carry an `llm_trace` reference linking to the stored reasoning log for that decision. When an edge is re-resolved in a subsequent build, the previous trace MUST be replaced by the new one; traces MUST NOT accumulate across builds.
- **FR-016**: Structured-mode edges MUST be unaffected by the LLM pass; their provenance and confidence MUST NOT change.
- **FR-017**: The evidence submitted per LLM call MUST be bounded by a configurable maximum file count and maximum byte budget; items exceeding the budget are processed as unknowns rather than truncated into oversized requests.
- **FR-018**: The LLM judge MUST have access to read-only lookup tools (identity lookup, provider identity retrieval, consumer reference retrieval) that operate against the live graph data; it MUST NOT have write access to any data store.
- **FR-019**: All decision types MUST use distinct, versioned prompt contracts. A call for one decision type MUST NOT reuse the prompt contract of another. Each contract MUST specify its required inputs and required output fields as follows:
  - **AMBIGUOUS_MATCH**: Input MUST include the consumer reference identifier, the list of candidate identities with their indexed names and associated evidence (redacted), and available contextual evidence within the budget. Output MUST include: `decision` (one of `keep-ambiguous` or `ground-to-candidate`), `candidate_id` (the chosen candidate's identifier — required when decision is `ground-to-candidate`, absent otherwise), and `reasoning` (non-empty string explaining the decision).
  - **UNRESOLVED_REF**: Input MUST include the consumer reference identifier and available contextual evidence (redacted, within budget). Output MUST include: `proposed_value` (the proposed identity value string, or explicitly null if the reference is unresolvable), and `reasoning` (non-empty string).
  - **IDENTITY_CLASS**: Input MUST include the identity value being classified and available contextual evidence (redacted, within budget). Output MUST include: `class` (one of `url`, `package`, `artifact`, or `unknown`), and `reasoning` (non-empty string).
  - Any response that is missing a required output field, contains an unrecognised `decision` or `class` value, or has an empty `reasoning` string MUST be treated as malformed and handled per the malformed-output edge case (discard, item stays as unknown, log raw response).
- **FR-020**: The reasoning trace for each LLM decision MUST be retrievable via the existing `explain_edge` query; no new query endpoint is required.

### Skip-Reason Taxonomy

Items the LLM pass cannot process are returned as unknowns with one of the following markers. These markers are distinct and MUST NOT be conflated:

| Marker | Trigger |
|--------|---------|
| `unresolved-secret` | Structured pass could not resolve because the relevant value is secret-typed; LLM pass does not attempt (secret cannot appear in evidence) |
| `unresolvable-redacted` | Residency gate blocked the LLM call due to PII detected in evidence or goal description |
| `rate-limited` | LLM provider returned HTTP 429; no retry in v0 |
| `llm-error` | LLM endpoint unreachable, returned a non-429 error, timed out, or returned malformed output |
| `budget-exceeded` | Evidence for this item exceeds the configured file count or byte budget; LLM call not attempted |
| `grounding-failed` | LLM returned a valid, non-null candidate but the candidate was not found in (or could not be looked up in) the reverse index |

### Concurrency

In v0, the LLM pass processes unresolved items sequentially (one at a time). Parallel LLM calls and concurrent multi-process cache writes are out of scope for v0.

### Key Entities

- **LLM Provider**: An external or self-hosted service that accepts a structured reasoning request and returns a structured response. Identified by endpoint URL, model name, and authentication credentials.
- **LLM Request**: A bounded, redacted payload containing a goal description, relevant evidence (within the byte budget), available read-only lookup tools, and the expected output schema for the decision type.
- **LLM Response**: A structured payload conforming to one of the defined prompt contracts (AMBIGUOUS_MATCH, UNRESOLVED_REF, IDENTITY_CLASS), containing a proposed candidate and supporting reasoning.
- **Reasoning Trace**: A record of one LLM decision: the redacted request payload, the raw response, the grounding result, and the final edge disposition (accepted / rejected / ambiguous-kept). A trace's lifetime is tied to its edge — when an edge is re-resolved in a subsequent build, its trace is replaced. No historical trace accumulation occurs in v0.
- **Response Cache**: A persistent key-value store mapping (goal description, sorted evidence locators) → LLM response, ensuring reproducibility across re-runs. Stored at a configurable path independent of the graph DB, defaulting to `~/.tendril/llm-cache/`.
- **Residency Gate**: A pre-call filter that inspects evidence for PII markers and blocks the call if detected, logging a reason code.
- **Grounding Step**: The post-LLM verification that looks up the LLM's proposed candidate in the reverse index and either accepts (writes edge) or rejects (keeps unknown) it.
- **Evidence Budget**: A configurable cap on the number of evidence files and total byte size submitted per LLM call, preventing context-window overflow.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a test fixture where at least 20% of dependencies are currently unresolved in structured mode, hybrid mode MUST resolve at least half of those unknowns into edges (accepted or confirmed-ambiguous), as verified by comparing the unknowns list before and after enabling hybrid mode.
- **SC-002**: Zero secret values or PII-marked fields appear in any captured LLM request payload, as verified by test inspection of the request log.
- **SC-003**: Every LLM-judged edge carries `provenance=llm-judged` and `confidence` is no higher than `low`, as verified by querying the graph after a hybrid build.
- **SC-004**: Two consecutive hybrid-mode builds against the same fixture produce identical edge sets and identical unknowns lists; the second build issues zero new LLM requests, as verified by the cache hit log.
- **SC-005**: A hybrid-mode build with a misconfigured (unreachable) LLM endpoint completes without error, returning the same results as a structured-mode build, with a warning in the log — verifiable by inspecting exit code and log output.
- **SC-006**: The `explain_edge` query for any LLM-judged edge returns a response that includes the redacted evidence payload, the LLM reasoning, and the grounding result — verifiable without any implementation knowledge.
- **SC-007**: Removing the LLM configuration entirely causes zero failures in the existing M0–M8 test suite, confirming structured mode is fully independent of M9.

---

## Assumptions

- The reverse index (built in M4) is fully populated before the LLM pass runs; the grounding step depends on it.
- `structured` mode (M0–M8) remains the default and fully functional without M9; M9 is purely additive.
- The LLM provider is assumed to support the OpenAI Chat Completions API format (or a compatible interface); other protocols are out of scope for v0 of M9.
- Self-hosted LLM support requires only that the endpoint implement the same Chat Completions API format; no additional adapter is needed.
- PII detection for the residency gate is pattern-based (e.g., email regex, known-marker field names); machine-learning-based PII classification is out of scope for M9.
- The evidence budget per call (maximum file count and maximum byte size) is configurable at deployment time; default values are 20 files and 50,000 bytes.
- The LLM reasoning trace is stored alongside graph data and is retrievable via the existing `explain_edge` query (M5); no new query endpoint is needed for M9.
- M9 depends on M4 (reverse index + BFS traversal) and M5 (`explain_edge` query path); it does not depend on M10.
- The existing M0–M8 test suite must continue to pass unchanged after M9 is introduced; new M9-specific tests are additive.
- Configuration of the LLM provider and the hybrid mode activation flag are managed via CLI flag, config file, or environment variable (precedence: CLI > config > env var); browser-based configuration UI is out of scope.
- The LLM response cache is stored at a configurable path separate from the graph DB, defaulting to `~/.tendril/llm-cache/`; it persists across build invocations and is invalidated by deleting the directory.
- SC-001 requires a dedicated M9 test fixture containing at least one dependency that is verifiably unresolvable in structured mode; the existing golden fixture (M6) does not satisfy this requirement and a new fixture must be created as part of M9 implementation.
- **v0 scope decision — retry**: Rate-limit responses (HTTP 429) are skipped without retry in v0. Retry with exponential back-off is deferred to a future release; it should be reconsidered when hybrid mode is used in high-throughput CI environments.
- **v0 scope decision — trace history**: Reasoning traces are replaced on edge re-resolution; no audit history is accumulated. Historical trace accumulation is deferred to a future release if audit requirements emerge.
- **v0 scope decision — PII detection**: PII detection uses pattern-based matching (email regex, known field-name heuristics). Machine-learning-based PII classification is deliberately excluded from v0; it should be reconsidered if the pattern-based approach produces significant false negatives in production evidence corpora.
- The M5 `explain_edge` query will require a minor extension to surface the `llm_trace` field alongside existing edge fields; this is a dependency touch, not a breaking change to the M5 contract.
- The OpenAI Chat Completions API compatibility of self-hosted endpoints (e.g., Ollama, vLLM, LM Studio) is assumed but has not been formally validated; operators using self-hosted models should verify endpoint compatibility before enabling hybrid mode in production.
