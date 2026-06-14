# Quickstart: M0–M4 Verify and Complete

**Audience**: Contributor implementing the three gap closures

---

## Prerequisites

```bash
cd tendril-graph
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Verify baseline — must be 38 tests, 0 failures
.venv/bin/python -m pytest tests/ --collect-only -q
.venv/bin/python -m pytest tests/ -q
```

If pytest fails with `ModuleNotFoundError: No module named 'kuzu'`, you are
using the system Python. Always use `.venv/bin/python -m pytest`.

---

## Gap 1: Conformance Subclasses (M1)

### 1a. Read the base classes

```bash
cat tests/conformance/test_vcs_provider.py
cat tests/conformance/test_cicd_provider.py
```

Note all abstract fixture methods. Your subclass must implement every one.

### 1b. Check `plugins/base.py` for `resolve_deployed_ref`

```bash
grep -n "resolve_deployed_ref\|abstractmethod" tendril/plugins/base.py
```

If `resolve_deployed_ref` is decorated `@abstractmethod` in `CICDProvider`,
add `test_resolve_deployed_ref_returns_sha` to `ConformanceCICDProvider` first.
If not, add it only in the Octopus subclass.

### 1c. Create fixture files for resolve_deployed_ref

```bash
# See data-model.md §Fixture Schema for exact JSON shapes
# Files to create:
tests/fixtures/cicd/octopus/deployments_Projects-1_prod.json
tests/fixtures/cicd/octopus/release_Releases-50.json
tests/fixtures/cicd/octopus/task_log_ServerTasks-3217.txt
```

### 1d. Check connector fixture loading for `read_file`

```bash
grep -n "_fixture_read_file\|fixture_dir" tendril/connectors/vcs/github.py
grep -n "_fixture_read_file\|fixture_dir" tendril/connectors/vcs/bitbucket_dc.py
```

This tells you the expected `fixture_dir / provider / org / name / "files" / path`
structure. Create the minimum file(s) needed under `files/` for
`sample_file_path` to return bytes.

### 1e. Write subclasses

Create one file per connector (see `plan.md §Step 4` for the pattern):
- `tests/conformance/github/test_github_conformance.py`
- `tests/conformance/bitbucket_dc/test_bitbucket_dc_conformance.py`
- `tests/conformance/teamcity/test_teamcity_conformance.py`
- `tests/conformance/octopus/test_octopus_conformance.py`

Each directory needs an `__init__.py` for pytest discovery.

### 1f. Verify

```bash
.venv/bin/python -m pytest tests/conformance/ -v
```

Expected: all conformance tests pass, no network calls, count > 38.

---

## Gap 2: Rung 4 Implementation (M4-a)

### 2a. Implement

Edit `tendril/core/resolver.py`:

1. Add `deploy_logs: list[str] | None = None` to `Resolver.acquire()` signature.
2. Add helper `_parse_kv_from_logs(lines: list[str], key: str) -> str | None`
   after `_find_in_store`. Use `re.compile(rf'^{re.escape(key)}=(.+)$', re.IGNORECASE)`.
3. Replace the stub comment at line 115 with the rung 4 block (see `plan.md §Step 2`).

### 2b. Write a unit test

In `tests/test_end_to_end.py` or a dedicated file, add:
```python
def test_rung4_parses_kv_from_logs():
    from tendril.core.resolver import Resolver
    from tendril.models.ir import TokenDecl, CICDProfile, CICDProviderEntry
    resolver = Resolver()
    token = TokenDecl(name="LandingPageUrl")
    profile = CICDProfile(repo=ANCHOR, environments=["prod"],
                          providers=[CICDProviderEntry(provider_id="octopus", roles=["deploy"])])
    result = resolver.acquire(
        token=token, repo=ANCHOR, env="prod", profile=profile,
        deploy_logs=["LandingPageUrl=https://d-ui.prod.example.com"],
    )
    assert result.resolved
    assert result.rung == "deploy-log"
    assert result.value == "https://d-ui.prod.example.com"
```

### 2c. Verify

```bash
.venv/bin/python -m pytest tests/ -k "rung4 or deploy_log" -v
```

---

## Gap 3: Tighten E2E Assertions (M4-b)

### 3a. Read current model fields

```bash
grep -n "from_id\|unknowns\|ambiguous\|stale" tendril/models/graph.py tendril/models/ir.py
```

Confirm all SC-003 fields exist on the `DependsOn` edge. Add missing fields with
sensible defaults if absent.

### 3b. Read current traversal output

```bash
grep -n "from_id\|unknowns\|deployed_ref\|confidence\|provenance" tendril/core/traversal.py
```

Confirm that the engine sets `from_id`, `deployed_ref`, `unknowns`, and assigns
`Provenance.INJECTED` (not DECLARED) and `Confidence.HIGH` for the golden path.

### 3c. Tighten assertions

Replace the loose assertions in `test_first_depends_on_edge` with exact-value
assertions. See `plan.md §Step 5` for the complete block.

### 3d. Verify

```bash
.venv/bin/python -m pytest tests/test_end_to_end.py -v
```

---

## Final Check

```bash
# Must pass: M0
.venv/bin/python -m pytest tests/test_m0_acceptance.py -v

# Must pass: M1 (Gap 1)
.venv/bin/python -m pytest tests/conformance/ -v

# Must pass: M2
.venv/bin/python -m pytest tests/ -k attribution -v

# Must pass: M3
.venv/bin/python -m pytest tests/ -k extractor -v

# Must pass: M4 (Gaps 2 and 3)
.venv/bin/python -m pytest tests/test_end_to_end.py -v

# Must pass: full suite, count ≥ 38
.venv/bin/python -m pytest tests/ -v
```

All six commands must exit 0 with zero failures before the branch is mergeable.
