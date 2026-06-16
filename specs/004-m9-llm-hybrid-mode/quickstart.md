# Quickstart: M9 — LLM Hybrid Mode Validation

*Phase 1 output for `specs/004-m9-llm-hybrid-mode/plan.md`*

This guide covers runnable validation scenarios that prove M9 works end-to-end.
It does not include full implementation code — see `tasks.md` for that.

---

## Prerequisites

```bash
# Install (editable, with dev dependencies)
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

# The M9 fixture lives at:
#   tests/fixtures/golden/m9-hybrid/
# Run all tests (must all pass before and after M9):
.venv/bin/python -m pytest tests/ -v
```

**LLM config for live integration** (not required for fixture-based tests):

```bash
export TENDRIL_LLM_ENDPOINT="https://api.openai.com/v1"
export TENDRIL_LLM_MODEL="gpt-4o"
export TENDRIL_LLM_API_KEY="sk-..."
```

---

## Scenario 1 — Hybrid mode reduces unknowns (SC-001)

**Goal**: Verify that hybrid mode resolves at least 50 % of the structured-mode unknowns
in the M9 fixture.

```bash
# Step 1: Run structured mode; note how many unknowns are in the output
.venv/bin/tendril graph build \
  --anchor myorg/anchor-repo \
  --fixture-dir tests/fixtures/golden/m9-hybrid \
  --mode structured

# Expected: output lists ≥ 1 unresolved dependency (confirmed by structured_unknowns.json)

# Step 2: Run hybrid mode with mock LLM (used in CI — no live API key needed)
TENDRIL_LLM_ENDPOINT="mock://fixture" \
TENDRIL_LLM_MODEL="mock" \
TENDRIL_LLM_API_KEY="mock" \
.venv/bin/tendril graph build \
  --anchor myorg/anchor-repo \
  --fixture-dir tests/fixtures/golden/m9-hybrid \
  --mode hybrid

# Expected: output lists fewer unknowns; at least one new DEPENDS_ON edge appears
# with provenance=llm-judged and confidence=low
```

**Automated assertion** (integration test):

```bash
.venv/bin/python -m pytest tests/integration/test_hybrid_mode.py::test_sc001_unknowns_reduced -v
```

---

## Scenario 2 — Secret values never reach the LLM (SC-002)

**Goal**: Verify that secret-typed variable values are replaced with `[REDACTED]` before
any LLM request payload is constructed.

```bash
# The M9 fixture includes a variable with is_secret=True in cicd/github_actions/vars_anchor.json
# Run hybrid mode and inspect the captured request log:
.venv/bin/python -m pytest tests/integration/test_hybrid_mode.py::test_sc002_secret_redaction -v

# What the test asserts:
# - LLM mock receives a request payload
# - That payload does not contain the raw secret value (the fixture knows what it is)
# - The payload contains [REDACTED] in place of the secret
```

---

## Scenario 3 — LLM-judged edges carry correct provenance (SC-003)

**Goal**: Verify every LLM-contributed edge carries `provenance=llm-judged` and
`confidence=low`.

```bash
.venv/bin/python -m pytest tests/integration/test_hybrid_mode.py::test_sc003_provenance_labels -v

# After a hybrid build, the test queries the KuzuStore for all edges and asserts:
# 1. Structured-mode edges: provenance unchanged (declared / injected / observed)
# 2. LLM-judged edges: provenance == "llm-judged" AND confidence == "low"
# 3. No LLM-judged edge has confidence above "low"
```

---

## Scenario 4 — Cache prevents duplicate LLM calls on re-run (SC-004)

**Goal**: Verify that two consecutive hybrid builds produce identical results and the
second build issues zero new LLM network requests.

```bash
.venv/bin/python -m pytest tests/integration/test_hybrid_mode.py::test_sc004_cache_hit -v

# Test flow:
# 1. Run hybrid build with mock LLM, record call count (expect N > 0)
# 2. Run hybrid build again with same inputs, record call count (expect 0 — all cache hits)
# 3. Assert edge sets from both runs are identical (provenance, confidence, llm_trace)
# 4. Assert unknowns lists from both runs are identical
```

---

## Scenario 5 — Misconfigured LLM endpoint: build succeeds (SC-005)

**Goal**: Verify that a hybrid-mode build with an unreachable LLM endpoint completes
without error, returning the same results as structured mode, with a warning logged.

```bash
TENDRIL_LLM_ENDPOINT="http://localhost:19999"  # nothing listening
TENDRIL_LLM_MODEL="gpt-4o"
TENDRIL_LLM_API_KEY="sk-test" \
.venv/bin/tendril graph build \
  --anchor myorg/anchor-repo \
  --fixture-dir tests/fixtures/golden/m9-hybrid \
  --mode hybrid
echo "Exit code: $?"

# Expected:
# - Exit code 0
# - Stdout/stderr contains a warning about LLM endpoint being unreachable
# - Edge output is identical to structured-mode output (no LLM-judged edges)
# - All items that would have been processed by LLM remain in unknowns list with llm-error marker
```

**Automated assertion**:

```bash
.venv/bin/python -m pytest tests/integration/test_hybrid_mode.py::test_sc005_endpoint_unreachable -v
```

---

## Scenario 6 — explain_edge surfaces LLM trace (SC-006)

**Goal**: Verify that `explain_edge` for an LLM-judged edge returns the redacted evidence,
LLM reasoning, and grounding result.

```bash
# 1. Run a hybrid build (creates the graph)
.venv/bin/tendril graph build \
  --anchor myorg/anchor-repo \
  --fixture-dir tests/fixtures/golden/m9-hybrid \
  --mode hybrid \
  --db /tmp/tendril-m9-test.db

# 2. Query explain_edge for one of the LLM-judged edges
.venv/bin/tendril query explain-edge \
  --db /tmp/tendril-m9-test.db \
  --from "myorg/anchor-repo" \
  --to "myorg/sidecar-service" \
  --env production

# Expected output includes:
# - "provenance": "llm-judged"
# - "llm_trace": "<trace_id>"
# - "evidence": [...] (includes grounding locator)
# - Contents of the trace (redacted request, LLM reasoning, grounding result)
```

**Automated assertion**:

```bash
.venv/bin/python -m pytest tests/integration/test_hybrid_mode.py::test_sc006_explain_edge_trace -v
```

---

## Scenario 7 — M0–M8 tests unaffected by M9 (SC-007)

**Goal**: Verify that removing LLM config causes zero failures in the existing test suite.

```bash
# Unset all LLM env vars (simulating no config)
unset TENDRIL_LLM_ENDPOINT TENDRIL_LLM_MODEL TENDRIL_LLM_API_KEY

# Run the full existing test suite (137 tests from M0-M8)
.venv/bin/python -m pytest tests/ --ignore=tests/integration/test_hybrid_mode.py -v

# Expected: all 137 tests pass; no LLM-related imports required for passing
```

---

## Expected Test Run (post-M9)

```
tests/conformance/llm/test_llm_provider.py           [conformance, fixture-mode]
tests/integration/test_hybrid_mode.py::test_sc001_*  [integration, mock LLM]
tests/integration/test_hybrid_mode.py::test_sc002_*  [integration, mock LLM]
...
tests/integration/test_hybrid_mode.py::test_sc007_*  [integration, no LLM config]
...existing M0-M8 tests...
```

All tests must pass with `pytest tests/` and zero external credentials or live API calls.
