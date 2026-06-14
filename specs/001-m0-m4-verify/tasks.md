# Tasks: M0–M4 Core Implementation — Verify and Complete

**Input**: Design documents from `specs/001-m0-m4-verify/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ quickstart.md ✅

**Tests**: Included — the spec's success criteria are entirely test-based.

**Organization**: Tasks grouped by user story. US2/US5/US6 are verify-only (already
implemented per CLAUDE.md). Implementation work is in US3 (Gap 1) and US4 (Gaps 2+3).
US1 is the final gate that proves everything passes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable — different files, no dependency on incomplete tasks
- **[Story]**: User story label (US1–US6) for traceability

---

## Phase 1: Setup

**Purpose**: Verify the development environment is ready. No project structure to create
(all 7 plugin ABCs, connectors, and core are already scaffolded per CLAUDE.md).

- [ ] T001 Verify `.venv` is active and `python -m pytest tests/ --collect-only -q` shows 38 tests with zero errors (must use `.venv/bin/python`, system python lacks kuzu)
- [ ] T002 Confirm `tests/conformance/test_vcs_provider.py` and `tests/conformance/test_cicd_provider.py` exist and contain abstract test methods (read both files)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Fixture files required by both US3 conformance tests and the US4 rung 4
test. Must be created before any conformance subclass or resolver change is tested.

**⚠️ CRITICAL**: US3 (T008–T012) and US4 (T015) depend on these fixtures.

- [ ] T003 Inspect `tendril/plugins/base.py` — grep for `resolve_deployed_ref` and `abstractmethod` to determine if `resolve_deployed_ref` is declared `@abstractmethod` on `CICDProvider` (this determines T007 scope)
- [ ] T004 Create `tests/fixtures/cicd/octopus/deployments_Projects-1_prod.json` — Octopus deployments response for `project=Projects-1, env=prod`; must contain `ReleaseId="Releases-50"` and `TaskId="ServerTasks-3217"` (see data-model.md §Fixture Schema)
- [ ] T005 Create `tests/fixtures/cicd/octopus/release_Releases-50.json` — Octopus release record for `Releases-50`; must contain `BuildInformation[0].VcsCommitNumber="abc123def456"` and `Branch="main"` (see data-model.md §Fixture Schema)
- [ ] T006 Create `tests/fixtures/cicd/octopus/task_log_ServerTasks-3217.txt` — plain-text deploy log; must contain line `LandingPageUrl=https://d-ui.prod.example.com` (see data-model.md §Fixture Schema)

**Checkpoint**: All three fixture files committed. US3 and US4 implementation can proceed.

---

## Phase 3: User Story 3 — VCS and CI/CD Connectors Pass Conformance (Priority: P1)

**Goal**: Close Gap 1 (M1). Create concrete conformance subclasses for GitHub, Bitbucket DC,
TeamCity, and Octopus so that `pytest tests/conformance/ -v` passes for all four connectors
using fixture data only. Every abstract method in the respective ABC must be exercised.

**Independent Test**: `.venv/bin/python -m pytest tests/conformance/ -v --no-header`
must complete with zero failures and no network calls.

### Implementation for User Story 3

- [ ] T007 [US3] If T003 confirms `resolve_deployed_ref` is `@abstractmethod` on `CICDProvider`, add `sample_deploy_project()` and `test_resolve_deployed_ref_returns_sha()` abstract methods to `ConformanceCICDProvider` in `tests/conformance/test_cicd_provider.py`; otherwise skip this task
- [ ] T008 [P] [US3] Read `tendril/connectors/vcs/github.py` lines for `_fixture_read_file` and `_fixture_read_tree` to understand path construction; create any missing files under `tests/fixtures/vcs/github/` needed for `sample_file_path` to return bytes
- [ ] T009 [P] [US3] Read `tendril/connectors/vcs/bitbucket_dc.py` for `_fixture_read_file` path construction; create any missing files under `tests/fixtures/vcs/bitbucket_dc/` needed for `sample_file_path`
- [ ] T010 [P] [US3] Create `tests/conformance/github/__init__.py` (empty) and `tests/conformance/github/test_github_conformance.py` — `TestGitHubConformance(ConformanceVCSProvider)` using `GitHubProvider(token="fixture", fixture_dir=Path("tests/fixtures/vcs"))` with `sample_repo` pointing at a repo present in the github fixtures
- [ ] T011 [P] [US3] Create `tests/conformance/bitbucket_dc/__init__.py` (empty) and `tests/conformance/bitbucket_dc/test_bitbucket_dc_conformance.py` — `TestBitbucketDCConformance(ConformanceVCSProvider)` using `BitbucketDCProvider` with fixture_dir pointing at `tests/fixtures/vcs`
- [ ] T012 [US3] Create `tests/conformance/teamcity/__init__.py` (empty) and `tests/conformance/teamcity/test_teamcity_conformance.py` — `TestTeamCityConformance(ConformanceCICDProvider)` using `TeamCityProvider` with fixture_dir pointing at `tests/fixtures/cicd`; `sample_pipeline_or_project` must reference a pipeline present in the teamcity fixtures
- [ ] T013 [US3] Create `tests/conformance/octopus/__init__.py` (empty) and `tests/conformance/octopus/test_octopus_conformance.py` — `TestOctopusConformance(ConformanceCICDProvider)` using `OctopusProvider(base_url="", api_key="", space="Spaces-1", fixture_dir=Path("tests/fixtures/cicd/octopus"))` with `sample_pipeline_or_project="Projects-1"`; add `test_resolve_deployed_ref_returns_sha` that calls `provider().resolve_deployed_ref("Projects-1", "prod")` and asserts `result is not None` and `len(result.sha) >= 7`
- [ ] T014 [US3] Run `.venv/bin/python -m pytest tests/conformance/ -v` and fix any remaining failures; all abstract methods in `ConformanceVCSProvider` and `ConformanceCICDProvider` must be exercised (check coverage of: `list_repos`, `read_tree`, `read_file`, `default_branch`, `read_file_with_explicit_ref` for VCS; `discover_for_repo`, `list_pipelines`, `read_variable_store`, `secret_values_masked`, `read_provider_identities`, and `resolve_deployed_ref` for Octopus)

**Checkpoint**: `pytest tests/conformance/ -v` exits 0, all four connectors pass.

---

## Phase 4: User Story 4 — First Real DEPENDS_ON Edge End-to-End (Priority: P1)

**Goal**: Close Gap 2 (M4-a) and Gap 3 (M4-b). Implement rung 4 of the acquisition
ladder; tighten end-to-end test assertions to exact SC-003 field values.

**Independent Test**: `.venv/bin/python -m pytest tests/test_end_to_end.py -v`
must complete with zero failures, and `test_first_depends_on_edge` must assert all
SC-003 fields at their exact values (not membership in a set).

### Implementation for User Story 4

- [ ] T015 [P] [US4] Read `tendril/models/graph.py` — confirm `DependsOn` has fields: `from_id`, `to_id`, `env`, `provenance`, `confidence`, `deployed_ref`, `evidence`, `unknowns`, `ambiguous`, `candidates`, `stale`; add any missing fields with appropriate defaults (do not change existing fields)
- [ ] T016 [P] [US4] Read `tendril/core/traversal.py` — confirm the traversal engine sets `from_id` on edges, sets `deployed_ref` to the resolved SHA string (not a `DeployedRef` object), sets `provenance=Provenance.INJECTED` for variable-store-resolved values, sets `confidence=Confidence.HIGH` for exact URL matches, and populates `unknowns=[]` when all refs resolve; note any gaps
- [ ] T017 [US4] Implement rung 4 in `tendril/core/resolver.py`: (a) add `deploy_logs: list[str] | None = None` parameter to `Resolver.acquire()`; (b) add `_parse_kv_from_logs(lines: list[str], key: str) -> str | None` helper using `re.compile(rf'^{re.escape(key)}=(.+)$', re.IGNORECASE)` returning first match group; (c) replace the stub comment at line 115 with a rung 4 block that calls the helper and returns `AcquisitionResult(value=result, rung="deploy-log", evidence=[Evidence(source_type="deploy-log", locator=f"deploy-log:{token.name}")], resolved=True)` when a match is found; fall through silently when `deploy_logs` is None/empty
- [ ] T018 [US4] Fix `tendril/core/traversal.py` for any gaps found in T016: ensure `from_id` is set on every edge, `deployed_ref` carries the SHA string, `provenance` is `INJECTED` for variable-store resolutions, `confidence` is `HIGH` for exact host match, and `unknowns` is an empty list when all consumer refs resolved (do not change behavior for non-golden-path cases)
- [ ] T019 [US4] Add `test_rung4_parses_kv_from_logs` to `tests/test_end_to_end.py`: call `resolver.acquire(token=TokenDecl(name="LandingPageUrl"), repo=ANCHOR, env="prod", profile=profile, deploy_logs=["LandingPageUrl=https://d-ui.prod.example.com"])` and assert `result.resolved == True`, `result.rung == "deploy-log"`, `result.value == "https://d-ui.prod.example.com"`
- [ ] T020 [US4] Tighten `test_first_depends_on_edge` in `tests/test_end_to_end.py` to exact SC-003 assertions: `from_id == "bitbucket-dc:acme/webforms-solution"`, `to_id == "github:acme/landing-page-ui"`, `env == "prod"`, `provenance == Provenance.INJECTED`, `confidence == Confidence.HIGH`, `deployed_ref == "abc123def456"`, `len(evidence) >= 3` with locators containing `"home.aspx"` / `"appsettings.prod.json"` / `"octopus"`, `unknowns == []`
- [ ] T021 [US4] Run `.venv/bin/python -m pytest tests/test_end_to_end.py -v` and fix any remaining failures until all tests in that file pass with zero errors

**Checkpoint**: `pytest tests/test_end_to_end.py -v` exits 0 with SC-003 exact assertions passing.

---

## Phase 5: User Story 2 — Plugin ABCs Exist (Priority: P1, Verify-Only)

**Goal**: Confirm all seven ABCs are real contracts discoverable without modifying core.
Already implemented per CLAUDE.md. This phase is verification only.

**Independent Test**: `pytest tests/test_m0_acceptance.py -v` passes.

- [ ] T022 [US2] Run `.venv/bin/python -m pytest tests/test_m0_acceptance.py -v` and confirm all ABCs are importable and their method signatures match the spec; report any failures as regressions

---

## Phase 6: User Story 5 — Attribution (Priority: P2, Verify-Only)

**Goal**: Confirm attribution engine produces correct `CICDProfile` for the fixture estate.
Marked complete in review.md. This phase is verification only.

**Independent Test**: `pytest tests/ -k attribution -v` passes.

- [ ] T023 [US5] Run `.venv/bin/python -m pytest tests/ -k attribution -v` and confirm all attribution tests pass; if any fail, fix the attribution engine or its tests before proceeding

---

## Phase 7: User Story 6 — Extractors (Priority: P2, Verify-Only)

**Goal**: Confirm composition and .NET extractors produce `ConsumerRef` and `TokenDecl`
with correct evidence format. Marked complete in review.md. Verification only.

**Independent Test**: `pytest tests/ -k extractor -v` passes.

- [ ] T024 [US6] Run `.venv/bin/python -m pytest tests/ -k extractor -v` and confirm all extractor tests pass; verify `ConsumerRef.evidence` uses `{filename}:{line}` format; fix any failures

---

## Phase 8: User Story 1 — Full Suite Gate (Priority: P1)

**Goal**: Clean-checkout install-and-test passes with count ≥ 38 and zero external
network calls. This is the final gate: it passes only after US2–US6 are verified and
US3/US4 gaps are closed.

**Independent Test**: The sequence below completes with exit code 0, zero failures,
count ≥ 38.

- [ ] T025 [US1] Run `.venv/bin/python -m pytest tests/test_m0_acceptance.py -v` (M0 gate)
- [ ] T026 [US1] Run `.venv/bin/python -m pytest tests/conformance/ -v` (M1 gate — Gap 1 closed)
- [ ] T027 [US1] Run `.venv/bin/python -m pytest tests/ -k attribution -v` (M2 gate)
- [ ] T028 [US1] Run `.venv/bin/python -m pytest tests/ -k extractor -v` (M3 gate)
- [ ] T029 [US1] Run `.venv/bin/python -m pytest tests/test_end_to_end.py -v` (M4 gate — Gaps 2+3 closed)
- [ ] T030 [US1] Run `.venv/bin/python -m pytest tests/ -v` — confirm total collected ≥ 38, zero failures, zero errors; record actual count as the new baseline in CLAUDE.md if it exceeds 38
- [ ] T031 [US1] Verify CLI: `.venv/bin/tendril --help` outputs usage listing `providers`, `graph`, `query`, and `serve` as subcommands

**Checkpoint**: Branch is mergeable. All six milestone gates pass.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [ ] T032 [P] Verify all new evidence locators in tests follow the exact formats defined in spec.md §Defined Terms — Evidence Locator Formats (`{filename}:{line}`, `{provider}:{project}:{env}:{key}`, `{provider}:run-{id}`)
- [ ] T033 [P] Verify no test file contains `pytest.skip` or `xfail` that silently hides a required abstract method test
- [ ] T034 Update `CLAUDE.md` baseline comment if actual test count (from T030) exceeds 38

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)           → no dependencies
Phase 2 (Foundational)    → depends on Phase 1
Phase 3 (US3)             → depends on Phase 2 (fixtures)
Phase 4 (US4)             → depends on Phase 2 (fixtures)
Phase 5 (US2 verify)      → independent of Phase 3/4
Phase 6 (US5 verify)      → independent of Phase 3/4
Phase 7 (US6 verify)      → independent of Phase 3/4
Phase 8 (US1 gate)        → depends on Phase 3, 4, 5, 6, 7 all complete
Final (Polish)            → depends on Phase 8
```

### User Story Dependencies

- **US3 (P1)**: Depends on Foundational (Phase 2). Independent of US4.
- **US4 (P1)**: Depends on Foundational (Phase 2). Independent of US3.
- **US2/US5/US6 (verify)**: Independent — can run at any time after Phase 1.
- **US1 (gate)**: Depends on ALL other user stories complete.

### Parallel Opportunities Within US3

```bash
# T008, T009, T010, T011 can run simultaneously (different fixture dirs):
Task: "Inspect github.py fixture loading and prepare github fixtures" (T008)
Task: "Inspect bitbucket_dc.py fixture loading and prepare fixtures" (T009)
Task: "Create github conformance subclass" (T010)
Task: "Create bitbucket_dc conformance subclass" (T011)
# T012 (teamcity) and T013 (octopus) depend on T003/T007 completing first
```

### Parallel Opportunities Within US4

```bash
# T015 and T016 can run simultaneously (different files):
Task: "Read models/graph.py and verify/add missing DependsOn fields" (T015)
Task: "Read core/traversal.py and identify exact-value gaps" (T016)
# T017 (rung 4) and T018 (traversal fix) can run simultaneously after T016
# T019, T020 depend on T017 and T018
```

---

## Implementation Strategy

### MVP: Close Gap 3 First (fastest validation)

1. Complete Phase 1 (T001–T002, ~5 min)
2. Run T020: tighten e2e assertions → test FAILS
3. Run T016: read traversal.py to find gaps
4. Fix traversal (T018) → run T021 → e2e passes
5. **Validate**: `pytest tests/test_end_to_end.py -v` exits 0

This proves the engine produces exact SC-003 values before investing in conformance work.

### Full Delivery Order

1. Phase 1 (verify baseline)
2. Phase 2 (create 3 fixture files)
3. Phase 3 (US3) + Phase 5/6/7 in parallel
4. Phase 4 (US4)
5. Phase 8 (US1 gate)
6. Final phase

---

## Notes

- `[P]` = different files, no dependency on incomplete tasks — safe to run in parallel
- All `pytest` invocations must use `.venv/bin/python -m pytest`, never system python
- Each conformance subclass file must NOT import from or modify any core file
- Rung 4 in resolver.py: the `rung` field value must be exactly `"deploy-log"` (string, not enum)
- Tightened e2e assertions must use `==` not `in (...)` — loose membership checks do not satisfy SC-003
- If traversal.py needs fixing for exact values, verify the fix does not alter behavior on non-fixture paths
