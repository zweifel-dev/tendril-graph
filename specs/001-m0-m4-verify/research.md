# Research: M0–M4 Verify and Complete

**Phase**: 0 | **Date**: 2026-06-14 | **Plan**: [plan.md](plan.md)

All NEEDS CLARIFICATION items are resolved by direct inspection of the codebase.
No external research required.

---

## Q1 — What is the exact test baseline count?

**Decision**: 38 tests collected and passing.

**Rationale**: Verified via `.venv/bin/python -m pytest tests/ --collect-only -q`.
The system Python cannot collect tests (kuzu not installed there); the venv must
always be used.

**Evidence**: `pytest` output `38 tests collected in 0.06s`. CLAUDE.md baseline
of "38 tests" is confirmed accurate.

---

## Q2 — Do conformance base classes cover `resolve_deployed_ref`?

**Decision**: `resolve_deployed_ref` is NOT currently in `ConformanceCICDProvider`
(`tests/conformance/test_cicd_provider.py`). It exists as a concrete method on
`OctopusProvider` (`tendril/connectors/cicd/octopus.py:409`) but its abstract
declaration in `plugins/base.py` must be verified during implementation.

**Rationale**: The conformance base (`test_cicd_provider.py`) has seven tests
covering `id`, `capabilities`, `discover_for_repo`, `list_pipelines`,
`read_variable_store`, secret masking, and `read_provider_identities`. There is
no `test_resolve_deployed_ref`. SC-002 requires "every abstract method covered";
if `resolve_deployed_ref` is abstract in `CICDProvider` the base must gain this
test. If it is Octopus-specific (not abstract in the ABC), the test lives only in
the Octopus subclass.

**Action**: Read `tendril/plugins/base.py` at the start of Step 3 to confirm.

---

## Q3 — What fixture files does OctopusProvider.resolve_deployed_ref need?

**Decision**: Two new files needed:
1. `tests/fixtures/cicd/octopus/deployments_Projects-1_prod.json` — fixture key
   used by `resolve_deployed_ref("Projects-1", "prod")`.
2. `tests/fixtures/cicd/octopus/release_Releases-50.json` — the release record
   for `ReleaseId: "Releases-50"` (found in the deployments fixture); must contain
   `BuildInformation[0].VcsCommitNumber = "abc123def456"`.

**Rationale**: `OctopusProvider._get_json` constructs `fixture_key` as
`f"deployments_{project_id}_{env}"` and `f"release_{release_id}"`. The existing
`deployments.json` is named without the project/env suffix so it will NOT be
found by `resolve_deployed_ref` under its default fixture_key logic. The existing
fixture `ReleaseId: "Releases-50"` tells us the release fixture filename.

---

## Q4 — How does the GitHub provider load fixture files for `read_file`?

**Decision**: `GitHubProvider._fixture_read_file` constructs the path as:
`fixture_dir / "github" / org / name / "files" / path`. The `sample_file_path`
in the conformance subclass must therefore point to a file that exists at
`tests/fixtures/vcs/github/acme-corp/landing-page-ui/files/{sample_file_path}`.

**Rationale**: Direct code read of `github.py:144–148`:
```python
file_path = (
    self._fixture_dir / self.id() / repo.org / repo.name / "files" / path
)
return file_path.read_bytes()
```
The existing fixture `tests/fixtures/vcs/github/landing-page-ui_files.json`
appears to be a directory listing, not the individual file structure. The
conformance test may need to either (a) create a minimal file under the
`files/` subdirectory, or (b) mock `read_file` just for the conformance test
to return bytes. Prefer (a) to avoid mocking the method under test. A single
small file (`src/index.html`) can be committed.

---

## Q5 — Does the traversal engine currently produce `from_id` and `unknowns` on edges?

**Decision**: Must be verified by reading `tendril/core/traversal.py` and
`tendril/models/graph.py`. The e2e test currently only checks
`e.to_id == "github:acme/landing-page-ui"` and `e.env == "prod"` for filtering;
it never asserts `from_id` or `unknowns`. If the `DependsOn` edge model lacks
these fields, they must be added.

**Rationale**: `DependsOn` is defined in `models/graph.py` (or `models/ir.py`).
Confirming field presence before writing tightened assertions prevents a scenario
where the assertion fix is correct but the model is incomplete.

---

## Q6 — What is the rung 4 `deploy_logs` threading strategy?

**Decision**: Add `deploy_logs: list[str] | None = None` as a keyword parameter
to `Resolver.acquire()`. Do NOT thread it through the traversal engine unless a
later caller needs it. For the unit test, call `acquire()` directly with
pre-fetched log lines. For the integration path, the caller (resolver or traversal)
fetches logs from `provider.read_deploy_logs(run_id)` before calling `acquire`.

**Rationale**: The resolver currently accepts `variable_stores` as a pre-fetched
list; the same pattern applies to deploy logs. This keeps the resolver pure
(no provider references inside `acquire`) and the change is minimal (one new
optional param, one regex helper function).

---

## Q7 — What SHA must `deployed_ref` equal in the tightened e2e test?

**Decision**: `"abc123def456"` — the exact string from the `VcsCommitNumber` in
the inline `OCTOPUS_DEPLOYMENTS` dict in `test_end_to_end.py:105`:
```python
"VcsCommitNumber": "abc123def456",
```
This is also the value specified in the spec's SC-003 and in
`deployments_Projects-1_prod.json` (to be created).

---

## Q8 — Can the Bitbucket DC provider's `read_file` work with existing fixtures?

**Decision**: Must verify the fixture loading logic in
`tendril/connectors/vcs/bitbucket_dc.py`. The existing fixture files are
`webforms-solution_tree.json` and `webforms-solution_files.json`. The `read_file`
method likely loads from a flat `files/` subpath. Check `_fixture_read_file`
implementation before writing the subclass's `sample_file_path`.

---

## Summary of Decisions

| # | Unknown | Resolution |
|---|---------|------------|
| Q1 | Baseline test count | 38, venv required |
| Q2 | `resolve_deployed_ref` in ABC? | Check `plugins/base.py` during Step 3 |
| Q3 | Octopus fixture files needed | 2 new files + 1 task log txt |
| Q4 | GitHub `read_file` fixture path | Needs `files/` subdir with real file |
| Q5 | `from_id` / `unknowns` on edge model | Read `models/graph.py` before Step 5 |
| Q6 | Rung 4 threading | Optional param on `acquire()`, caller fetches |
| Q7 | Exact deployed_ref SHA | `"abc123def456"` |
| Q8 | Bitbucket DC `read_file` fixture | Read `bitbucket_dc.py` before Step 4 |
