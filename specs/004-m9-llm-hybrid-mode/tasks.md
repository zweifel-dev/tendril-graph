# Tasks: M9 — LLM Hybrid Mode

**Input**: Design documents from `/specs/004-m9-llm-hybrid-mode/`

**Prerequisites**: plan.md ✓ | spec.md ✓ | research.md ✓ | data-model.md ✓ | contracts/ ✓ | quickstart.md ✓

**Tests**: Included — spec.md mandates independent test criteria per user story and conformance
gates for providers (Constitution §Testing).

**Organization**: Tasks are grouped by user story to enable independent implementation and
testing of each story. US2 precedes US1 in phase ordering because the redactor is a
structural prerequisite for the LLM judge.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package directories, dependencies, and stubs

- [X] T001 Create package directories: `tendril/llm/`, `tendril/llm/contracts/`, `tendril/connectors/llm/` (mkdir only)
- [X] T002 Add `openai` to `pyproject.toml` main dependencies (version constraint `>=1.0`)
- [X] T003 [P] Create `__init__.py` stubs for `tendril/llm/__init__.py`, `tendril/llm/contracts/__init__.py`, `tendril/connectors/llm/__init__.py`

**Checkpoint**: Package structure in place; `pip install -e .` succeeds with `openai` importable

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core model changes and shared infrastructure that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Extend `Unresolved.reason` enum in `tendril/models/ir.py` — add five new string literals: `"llm-error"`, `"rate-limited"`, `"budget-exceeded"`, `"grounding-failed"`, `"unresolvable-redacted"` (alongside existing values; no removals)
- [X] T005 Add `llm_trace: str | None = None` field to `DependsOn` dataclass in `tendril/models/graph.py` — nullable; default None; present only on `provenance=llm-judged` edges
- [X] T006 [P] Implement `LLMConfig` dataclass and resolution logic in `tendril/config.py` — fields: `endpoint`, `model`, `api_key`, `timeout_seconds` (default 60), `max_evidence_files` (default 20), `max_evidence_bytes` (default 50000), `cache_path` (default `~/.tendril/llm-cache/`); resolve from env vars (`TENDRIL_LLM_ENDPOINT`, `TENDRIL_LLM_MODEL`, `TENDRIL_LLM_API_KEY`, `TENDRIL_LLM_TIMEOUT`, `TENDRIL_LLM_CACHE_PATH`) > `[llm]` TOML section > defaults; `is_complete()` returns True iff endpoint + model + api_key are all non-None and non-empty
- [X] T007 [P] Create `PromptContract` ABC in `tendril/llm/contracts/base.py` — abstract methods: `contract_version() -> str`, `build_prompt(item) -> LLMRequest`, `validate_response(raw: dict) -> PromptResponse`; `validate_response` raises `MalformedResponseError` (new exception) if any required field is absent/empty/invalid; include `MalformedResponseError` dataclass with `raw_response: dict` and `reason: str` fields
- [X] T008 [P] Implement `DiskResponseCache` in `tendril/llm/cache.py` — `make_cache_key(goal: str, locators: list[str]) -> str` using `hashlib.sha256(json.dumps({"goal": goal, "locators": sorted(locators)}, sort_keys=True, separators=(",",":")).encode()).hexdigest()`; `get(goal, locators) -> dict | None`; `put(goal, locators, raw_response, contract_version)` — writes `{sha256}.json` file; if cache dir is inaccessible logs WARNING and operates as no-op (FR-011); `DiskCacheEntry` dataclass with fields: `cache_key`, `goal`, `locators`, `raw_response`, `created_at`, `contract_version`
- [X] T009 [P] Implement `OpenAICompatibleProvider` in `tendril/connectors/llm/openai_provider.py` — implements `LLMProvider` ABC from `tendril/plugins/base.py`; constructor takes `LLMConfig`; `complete(req: LLMRequest) -> LLMResponse` — builds `openai.OpenAI(base_url=cfg.endpoint, api_key=cfg.api_key, timeout=cfg.timeout_seconds)`; calls `client.chat.completions.create(model=cfg.model, temperature=0, ...)`; on timeout raises with `LLMErrorKind.TIMEOUT`; on HTTP 429 raises with `LLMErrorKind.RATE_LIMITED`; on other errors raises with `LLMErrorKind.ENDPOINT_ERROR`; define `LLMErrorKind` enum in this file
- [X] T010 Create conformance fixture at `tests/fixtures/conformance/llm/complete_responses.json` — JSON dict with three entries keyed by contract version (`"ambiguous_match/v1"`, `"unresolved_ref/v1"`, `"identity_class/v1"`); each entry is a valid canned LLM response dict that passes the respective contract's `validate_response()`

**Checkpoint**: Foundation ready; `ir.py`, `graph.py`, `config.py` extensions in place; LLMConfig, cache, and provider implementable; conformance fixture exists

---

## Phase 3: User Story 2 — Secret Safety and Data Residency (Priority: P1)

**Goal**: Guarantee that no secret value or PII reaches the LLM — the LLM call is blocked
or redacted before the request payload is constructed (FR-004, FR-005, SC-002)

**Independent Test**: Inject a `is_secret=True` variable into the evidence set; verify the
mock LLM receives `[REDACTED]` in place of the value, and verify that evidence containing
an email address causes the call to be blocked entirely (quickstart.md Scenario 2)

**Dependency note**: US2 components (T011–T012) are structural prerequisites for US1
(LLMJudge); implement US2 before US1

- [X] T011 [US2] Implement `SecretRedactor` in `tendril/llm/redactor.py` — `redact(evidence: list[Evidence], known_secrets: set[str]) -> list[Evidence]`: (1) for each evidence item where the source key matches `is_secret_key()` from `config.py`, replace value with `"[REDACTED]"`; (2) for all evidence items (including non-secret), scan the value string and replace any occurrence of a known secret value with `"[REDACTED]"` (handles secrets embedded in URL strings per FR-004); return redacted copy without mutating input
- [X] T012 [US2] Implement `ResidencyGate` in `tendril/llm/redactor.py` — `evaluate(post_redacted_evidence: list[Evidence], goal: str) -> ResidencyGateResult`: scan all evidence field values AND the goal string for: email pattern `r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'`, phone pattern `r'\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'`, and field names in `{"user","author","owner","email","name","contact","username","firstname","lastname","fullname","phone","mobile","person","identity"}` (case-insensitive key match); if any triggers, return `ResidencyGateResult(allowed=False, reason_code="pii-detected", trigger=<matched field or pattern name>)`; otherwise return `ResidencyGateResult(allowed=True, reason_code=None, trigger=None)`; define `ResidencyGateResult` dataclass in same file
- [X] T013 [P] [US2] Add `test_secret_redactor_replaces_secret_values()` and `test_secret_redactor_replaces_embedded_secrets()` in `tests/conformance/llm/test_redactor.py` — verify no secret value appears in any redacted evidence item; verify values embedded inside URL strings are also replaced
- [X] T014 [P] [US2] Add `test_residency_gate_blocks_email()`, `test_residency_gate_blocks_phone()`, `test_residency_gate_blocks_pii_field_name()`, and `test_residency_gate_allows_clean()` in `tests/conformance/llm/test_redactor.py` — verify gate returns `allowed=False` on PII patterns and `allowed=True` on clean post-redacted evidence

**Checkpoint**: SecretRedactor and ResidencyGate pass all four conformance tests; T013 and T014 green

---

## Phase 4: User Story 1 — Reduce Unknowns Without Sacrificing Accuracy (Priority: P1) 🎯 MVP

**Goal**: The LLM pass runs after the structured pass, processes unresolved/ambiguous items
(using grounded proposals only), and reduces the unknown set — without inventing edges
(FR-002, FR-003, FR-006–009, SC-001)

**Independent Test**: Run hybrid mode against M9 fixture with a mock LLMProvider; verify
the unknowns list is shorter than structured mode and at least one new `DEPENDS_ON` edge
appears with `provenance=llm-judged` and `confidence=low` (quickstart.md Scenario 1)

- [X] T015 [P] [US1] Implement `AmbiguousMatchContract` in `tendril/llm/contracts/ambiguous_match.py` — `PROMPT_VERSION = "ambiguous_match/v1"`; `build_prompt(item: LLMJudgeItem) -> LLMRequest` assembles request with `goal = f"AMBIGUOUS_MATCH:{item.consumer_ref_id}"`, candidate list, redacted evidence within budget, and `contract_version`; `validate_response(raw: dict) -> AmbiguousMatchResponse` — validates `decision` ∈ `{"keep-ambiguous","ground-to-candidate"}`, `candidate_id` present and in candidate list when `decision=="ground-to-candidate"`, `reasoning` non-empty; raises `MalformedResponseError` on any violation; define `AmbiguousMatchResponse` Pydantic model
- [X] T016 [P] [US1] Implement `UnresolvedRefContract` in `tendril/llm/contracts/unresolved_ref.py` — `PROMPT_VERSION = "unresolved_ref/v1"`; `build_prompt(item)` with `goal = f"UNRESOLVED_REF:{item.consumer_ref_id}"`; `validate_response(raw)` — validates `proposed_value` key exists (null is valid), `reasoning` non-empty, `proposed_value` not empty string; raises `MalformedResponseError` on violation; define `UnresolvedRefResponse` Pydantic model
- [X] T017 [P] [US1] Implement `IdentityClassContract` in `tendril/llm/contracts/identity_class.py` — `PROMPT_VERSION = "identity_class/v1"`; `build_prompt(item)` with `goal = f"IDENTITY_CLASS:{item.consumer_ref_id}"`; `validate_response(raw)` — validates `class` key ∈ `{"url","package","artifact","unknown"}`, `reasoning` non-empty; note JSON field is `class` but Python model attribute is `class_`; raises `MalformedResponseError` on violation; define `IdentityClassResponse` Pydantic model
- [X] T018 [US1] Implement `GroundingStep` in `tendril/llm/grounding.py` — `ground(proposed_value: str, reverse_index: ReverseIndex, env: str) -> GroundingResult`: calls `reverse_index.lookup(proposed_value, env)`; if found returns `GroundingResult(found=True, matched_identity=..., index_locator=..., error=None)`; if not found returns `GroundingResult(found=False, matched_identity=None, index_locator=None, error=None)`; if index lookup raises any exception returns `GroundingResult(found=False, ..., error=str(exc))`; never raises; define `GroundingResult` dataclass
- [X] T019 [US1] Implement `LLMJudge` class in `tendril/llm/judge.py` with `run(result: TraversalResult, reverse_index: ReverseIndex, provider: LLMProvider, config: LLMConfig) -> TraversalResult` — for each item in `result.unresolved`: (1) skip if `reason == "is-secret"` (mark `unresolved-secret`, already set); (2) check evidence budget (`_check_budget(item, config) -> bool`); (3) collect known_secrets from item evidence; (4) call `SecretRedactor.redact()`; (5) call `ResidencyGate.evaluate()`; (6) select contract by `item.decision_type`; (7) build goal + locators; (8) check cache (`DiskResponseCache.get()`); (9) if cache miss: call `provider.complete()` catching `LLMErrorKind.RATE_LIMITED` → mark `rate-limited`, `LLMErrorKind.*` → mark `llm-error`; (10) `cache.put()` on success; (11) `contract.validate_response()` catching `MalformedResponseError` → mark `llm-error`, log raw; (12) if `proposed_value is None` → item stays unknown; (13) call `GroundingStep.ground()`; (14) if `grounding_result.found`: write `DependsOn` edge with `provenance=LLM_JUDGED`, `confidence=LOW`, `llm_trace=trace_id`, `evidence=original_evidence+[grounding_locator]`; remove item from unknowns; else mark `grounding-failed`; (15) for `AMBIGUOUS_MATCH` with `decision=="keep-ambiguous"`: keep `ambiguous=True` on both candidate edges, record trace; `_check_budget()` returns False (marks `budget-exceeded`) if file count > `config.max_evidence_files` or byte count > `config.max_evidence_bytes`; structured-mode edges are never touched (FR-016)
- [X] T020 [US1] Wire `--mode hybrid` in `tendril/cli/main.py` — add `"hybrid"` to the `--mode` enum choices (alongside `"structured"`); after `engine.traverse()` completes, if `mode == "hybrid"`: load `LLMConfig` from config; if `not config.is_complete()`: log WARNING `"Hybrid mode requested but LLM configuration is incomplete (missing: {fields}); falling back to structured mode."` and skip LLM pass; else construct `OpenAICompatibleProvider(config)`, `DiskResponseCache(config.cache_path)`, `LLMJudge(cache, SecretRedactor(), ResidencyGate())`, call `result = judge.run(result, reverse_index, provider, config)`; persist augmented result to KuzuStore as before
- [X] T021 [US1] Create M9 test fixture at `tests/fixtures/golden/m9-hybrid/` — `vcs/repos.json` (2 repos: `myorg/anchor-repo` as anchor, `myorg/sidecar-service` as target); `vcs/anchor-repo_tree.json` + `anchor-repo_files.json` (include source file referencing `ENV_SIDECAR_URL` env var); `vcs/sidecar-service_tree.json` + `sidecar-service_files.json`; `cicd/github_actions/vars_anchor.json` (include one variable `SIDECAR_URL` with `is_secret=false` and value `https://sidecar.internal`, and one `SECRET_TOKEN` with `is_secret=true`); `expected/structured_unknowns.json` (list of items that remain unresolved in structured mode — at least one, covering ≥20% of dependencies); `expected/hybrid_edges.json` (expected edges after LLM pass with `provenance=llm-judged`)
- [X] T022 [US1] Add LLM provider conformance test in `tests/conformance/llm/test_llm_provider.py` — load canned fixture from `tests/fixtures/conformance/llm/complete_responses.json`; for each of the three contracts: instantiate contract, call `build_prompt()` with a synthetic `LLMJudgeItem`, call `validate_response()` with canned fixture response, assert typed response model returned without error; also assert `MalformedResponseError` is raised for a canned malformed response (missing `reasoning` field)
- [X] T023 [US1] Add integration test `test_sc001_unknowns_reduced()` in `tests/integration/test_hybrid_mode.py` — create a `MockLLMProvider` returning fixture responses (from `complete_responses.json`) for each unresolved item; run structured mode against `tests/fixtures/golden/m9-hybrid/`; record unknowns count; run hybrid mode with `MockLLMProvider`; assert unknowns count decreased; assert at least one new `DependsOn` edge exists with `provenance="llm-judged"`, `confidence="low"`, `llm_trace` not None, `evidence` non-empty

**Checkpoint**: Core hybrid pipeline works end-to-end; SC-001 integration test passes with mock LLM

---

## Phase 5: User Story 3 — Configurable LLM Provider (Priority: P2)

**Goal**: Hybrid mode is fully BYOK — any OpenAI-compatible endpoint can be configured via
CLI, config file, or env var; missing or broken config degrades gracefully to structured
mode (FR-001, FR-012, FR-013, FR-014, SC-005)

**Independent Test**: Run hybrid mode with an unreachable endpoint (`localhost:19999`);
verify exit code 0, warning in log, and output identical to structured mode (quickstart.md Scenario 5)

- [X] T024 [P] [US3] Implement and test the `--mode` precedence chain (CLI > config > env > default) in `tendril/cli/main.py` — add reading `[graph] mode` from `tendril.toml` and `TENDRIL_GRAPH_MODE` env var; document precedence in a single `_resolve_mode(cli_flag, config, env) -> str` helper
- [X] T025 [P] [US3] Add integration test `test_sc005_endpoint_unreachable()` in `tests/integration/test_hybrid_mode.py` — patch `OpenAICompatibleProvider.complete()` to raise a connection error; run hybrid build; assert exit code 0, assert WARNING logged containing `"unreachable"` or `"error"`, assert resulting edge set equals structured-mode edge set, assert all would-be LLM items are in unknowns with reason `"llm-error"`
- [X] T026 [P] [US3] Add integration test `test_no_llm_config_falls_back_to_structured()` in `tests/integration/test_hybrid_mode.py` — run `tendril graph build --mode hybrid` with all `TENDRIL_LLM_*` env vars unset and no `[llm]` toml section; assert WARNING logged containing `"incomplete"`, assert results identical to structured mode, assert exit code 0

**Checkpoint**: Configurable provider + graceful degradation verified; SC-005 and no-config fallback tests green

---

## Phase 6: User Story 4 — Transparent Provenance and Confidence (Priority: P2)

**Goal**: Every LLM-judged edge carries `provenance=llm-judged`, `confidence=low`, and
an `llm_trace` reference; structured edges are unaffected (FR-008, FR-015, FR-016, SC-003)

**Independent Test**: Query all edges after a hybrid build; assert zero LLM-judged edges have
confidence above `low`; assert all structured edges have their original provenance unchanged

- [X] T027 [P] [US4] Add integration test `test_sc003_provenance_labels()` in `tests/integration/test_hybrid_mode.py` — run hybrid build with mock LLM; query KuzuStore for all `DependsOn` edges; assert every edge with `provenance="llm-judged"` has `confidence="low"` and `llm_trace` not None; assert every structured edge retains its original provenance/confidence (unchanged from what structured-only build produces)
- [X] T028 [P] [US4] Implement `ReasoningTrace` serialization in `tendril/llm/judge.py` — after an edge is written (accepted, rejected, or ambiguous-kept), write a `ReasoningTrace` JSON file at `{cache_path}/traces/{trace_id}.json` with fields: `trace_id`, `decision_type`, `contract_version`, `redacted_request` (no secret values), `raw_response`, `grounding_result` (serialised), `disposition` (`"accepted"` | `"rejected"` | `"ambiguous-kept"` | `"malformed"` | `"grounding-failed"`), `created_at`; set `DependsOn.llm_trace = trace_id` on accepted edges; on re-resolution overwrite existing trace file at same path

**Checkpoint**: Provenance labels and trace files verified; SC-003 test green

---

## Phase 7: User Story 5 — Reproducible Results Across Re-Runs (Priority: P2)

**Goal**: Two consecutive hybrid builds against the same fixture produce identical edge sets
and identical unknowns lists; the second build issues zero new LLM requests (FR-010,
FR-011, SC-004)

**Independent Test**: Run hybrid build twice; compare edge sets and unknowns; assert second
build's LLM call count is zero via mock call counter (quickstart.md Scenario 4)

- [X] T029 [P] [US5] Add integration test `test_sc004_cache_hit()` in `tests/integration/test_hybrid_mode.py` — run hybrid build with a call-counting mock LLM; record `call_count_1`; run again with same fixture and same cache dir; record `call_count_2`; assert `call_count_2 == 0`; assert edge sets from both runs are identical (same edges, same provenance, same confidence, same llm_trace IDs); assert unknowns lists are identical
- [X] T030 [P] [US5] Add deterministic output ordering assertion in `tests/integration/test_hybrid_mode.py` — `test_deterministic_ordering()`: run the hybrid build twice; sort edges and unknowns by a deterministic key (e.g., `(from_repo, to_repo, env)`) and assert the sorted lists are byte-for-byte identical between runs

**Checkpoint**: Cache hit and deterministic ordering verified; SC-004 test green

---

## Phase 8: User Story 6 — Explainability of LLM-Judged Edges (Priority: P3)

**Goal**: `explain_edge` query returns the LLM reasoning trace, grounding result, and
provenance chain for any LLM-judged edge (FR-020, SC-006)

**Independent Test**: Run hybrid build; call `explain_edge` for an LLM-judged edge; verify
response includes `llm_trace`, redacted evidence, LLM reasoning string, and grounding
result (quickstart.md Scenario 6)

- [X] T031 [US6] Extend `QueryEngine.explain_edge()` in `tendril/query/engine.py` — after fetching the edge, if `edge.llm_trace` is not None: load the `ReasoningTrace` JSON from `{cache_path}/traces/{edge.llm_trace}.json`; include `llm_trace` field in the `QueryResult.metadata` dict with sub-fields: `trace_id`, `decision_type`, `contract_version`, `redacted_request`, `raw_response`, `grounding_result`, `disposition`; if trace file is missing log WARNING and include `{"error": "trace-file-missing"}` in metadata; structured edges (llm_trace=None) are unaffected
- [X] T032 [US6] Add integration test `test_sc006_explain_edge_trace()` in `tests/integration/test_hybrid_mode.py` — run hybrid build with mock LLM; call `QueryEngine.explain_edge()` for an LLM-judged edge; assert response `metadata["llm_trace"]` is present and non-None; assert `metadata["llm_trace"]["redacted_request"]` does not contain any known secret value; assert `metadata["llm_trace"]["raw_response"]` is the canned fixture response; assert `metadata["llm_trace"]["grounding_result"]["found"] == True`

**Checkpoint**: explain_edge returns LLM trace for judged edges; SC-006 test green

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Secret redaction integration test, M0–M8 regression guard, architecture doc,
and final full-suite verification

- [X] T033 Add integration test `test_sc002_secret_redaction()` in `tests/integration/test_hybrid_mode.py` — use the M9 fixture which includes `SECRET_TOKEN` with `is_secret=true`; run hybrid build with a request-capturing mock LLM; inspect the captured request payload; assert the raw value of `SECRET_TOKEN` does not appear anywhere in the request payload; assert `"[REDACTED]"` appears in its place
- [X] T034 [P] Add integration test `test_sc007_m0m8_unaffected()` in `tests/integration/test_hybrid_mode.py` — run the full test suite against the golden fixture (M0–M8 fixture, not M9 fixture) with all `TENDRIL_LLM_*` env vars unset; assert exit code 0; assert no import of `tendril.llm` is required for any M0–M8 test to pass (verify by importing test modules without LLM deps available in a patched sys.modules)
- [X] T035 [P] Update `docs/architecture.md` Mermaid diagram to add the LLM hybrid mode layer — add `LLMJudge` as a post-processor node after `TraversalEngine`, with edges to `SecretRedactor → ResidencyGate → PromptContract → OpenAICompatibleProvider → GroundingStep → KuzuStore`; label the LLM path as `optional / hybrid mode only`
- [X] T036 Run `python -m pytest tests/ -v` and verify all tests pass (137 existing + new M9 tests); fix any failures before marking this task complete

**Checkpoint**: Full test suite green; M9 implementation complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US2 (Phase 3)**: Depends on Foundational — **BLOCKS US1 (LLMJudge requires redactor)**
- **US1 (Phase 4)**: Depends on Foundational + US2 — core MVP
- **US3 (Phase 5)**: Depends on Foundational + US1 (tests use LLMJudge infrastructure)
- **US4 (Phase 6)**: Depends on US1 (provenance labels written by LLMJudge)
- **US5 (Phase 7)**: Depends on US1 (cache used inside LLMJudge)
- **US6 (Phase 8)**: Depends on US1 (llm_trace written by LLMJudge) + US4 (trace serialisation)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **US2 (P1)**: After Foundational — **prerequisite for US1**
- **US1 (P1)**: After Foundational + US2 — core delivery
- **US3 (P2)**: After US1 — validates provider configurability end-to-end
- **US4 (P2)**: After US1 — validates provenance labels written by judge
- **US5 (P2)**: After US1 — validates cache integration
- **US6 (P3)**: After US1 + US4 — validates explain_edge extension

### Within Each User Story

- Models/dataclasses before services that use them
- Contracts before LLMJudge (judge selects and uses contracts)
- GroundingStep before LLMJudge (judge calls grounding)
- LLMJudge before CLI wiring (CLI constructs LLMJudge)
- Fixture before integration tests (tests reference fixture paths)

### Parallel Opportunities

- T003, T006, T007, T008, T009 (Phase 2): all touch different files — run in parallel
- T013, T014 (US2 conformance tests): different test functions — run in parallel
- T015, T016, T017 (Phase 4 contracts): different files — run in parallel
- T023 through T036 integration tests: different test functions — run in parallel once LLMJudge is implemented
- T024, T025, T026 (US3): different test functions — run in parallel

---

## Parallel Example: Phase 2 (Foundational)

```bash
# These five tasks touch different files and can run simultaneously:
Task T006: "Implement LLMConfig in tendril/config.py"
Task T007: "Create PromptContract ABC in tendril/llm/contracts/base.py"
Task T008: "Implement DiskResponseCache in tendril/llm/cache.py"
Task T009: "Implement OpenAICompatibleProvider in tendril/connectors/llm/openai_provider.py"
Task T010: "Create conformance fixture at tests/fixtures/conformance/llm/complete_responses.json"
```

## Parallel Example: Phase 4 (US1 — Prompt Contracts)

```bash
# Three contracts in three files — no dependencies between them:
Task T015: "Implement AmbiguousMatchContract in tendril/llm/contracts/ambiguous_match.py"
Task T016: "Implement UnresolvedRefContract in tendril/llm/contracts/unresolved_ref.py"
Task T017: "Implement IdentityClassContract in tendril/llm/contracts/identity_class.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only — the safety-first slice)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all)
3. Complete Phase 3: US2 (secret safety — required before US1)
4. Complete Phase 4: US1 (core hybrid pipeline — delivers SC-001)
5. **STOP and VALIDATE**: Run `pytest tests/integration/test_hybrid_mode.py::test_sc001_unknowns_reduced`
6. **STOP and VALIDATE**: Run `pytest tests/integration/test_hybrid_mode.py::test_sc002_secret_redaction`

### Incremental Delivery

1. Setup + Foundational + US2 + US1 → Core hybrid pipeline (MVP, SC-001 + SC-002)
2. Add US3 → Verified BYOK + graceful degradation (SC-005)
3. Add US4 → Provenance guarantees tested (SC-003)
4. Add US5 → Reproducibility verified (SC-004)
5. Add US6 → Explainability (SC-006)
6. Polish → Full suite green, SC-007 confirmed

---

## Notes

- `[P]` tasks touch different files — no file-level conflicts when run in parallel
- `[Story]` label maps each task to its spec.md user story for traceability
- Tests use fixture-based mocking — zero live LLM API calls required in CI
- `MockLLMProvider` (used in integration tests) should return entries from
  `tests/fixtures/conformance/llm/complete_responses.json` keyed by contract version
- The M9 fixture (`tests/fixtures/golden/m9-hybrid/`) must contain at least one token
  that is genuinely unresolvable in structured mode — this is what SC-001 tests against
- Secret `SECRET_TOKEN` in the M9 fixture must have a known raw value embedded in the
  fixture for T033 to assert its absence from the captured LLM request
- Never modify `TraversalEngine` core — the `LLMJudge` post-processor pattern is the
  only correct integration point (Constitution Principle I)
- All LLM calls must use `temperature=0` — enforced in `OpenAICompatibleProvider.complete()`
