# Implementation Plan: M9 — LLM Hybrid Mode

**Branch**: `004-m9-llm-hybrid-mode` | **Date**: 2026-06-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-m9-llm-hybrid-mode/spec.md`

---

## Summary

M9 adds an optional LLM-assisted post-processing pass that runs after the M0–M8 structured
analysis pass and attempts to resolve items the structured pass could not. It is purely
additive: structured mode remains the default and is fully independent of M9. Every LLM
proposal is grounded against the existing reverse index before an edge is written.

The mechanism is a `LLMJudge` post-processor (`tendril/llm/judge.py`) that consumes a
completed `TraversalResult` without touching `TraversalEngine` core, an OpenAI-compatible
HTTP client (`tendril/connectors/llm/openai_provider.py`), a disk-based response cache
keyed on (goal, sorted evidence locators), and a redaction + residency gate that blocks
secret values and PII before any LLM request is constructed.

---

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**:
- `openai` SDK — OpenAI Chat Completions client with `base_url` override for self-hosted
  endpoints (Ollama, vLLM, LM Studio, Azure, Bedrock); handles timeout + structured output
- stdlib only for all other M9 modules: `hashlib`, `json`, `re`, `pathlib`, `logging`

**Storage**:
- Disk-based LLM response cache at a configurable path (default `~/.tendril/llm-cache/`);
  flat directory of `{sha256}.json` files; independent of the graph DB directory
- Existing KuzuStore (no new tables; `DependsOn` gains one nullable `llm_trace` field)

**Testing**: pytest; all tests use fixture-based mock LLM responses — no live LLM calls
required; mock `LLMProvider` returns canned `complete_responses.json` fixture entries

**Target Platform**: Linux/macOS/Windows (Python side); cloud or self-hosted LLM endpoint

**Project Type**: library extension (post-processor + new `LLMProvider` plugin behind
existing ABC) and test fixtures

**Performance Goals**: v0 is sequential (one item at a time); bounded by the configured
per-call timeout (default 60 s); no parallelism target for v0

**Constraints**:
- All LLM calls at temperature = 0 (reproducibility requirement FR-010)
- Evidence budget: ≤ 20 files and ≤ 50 000 bytes per call (configurable, FR-017)
- Secret values never sent to LLM — redacted to `[REDACTED]` before request build (FR-004)
- PII-containing evidence blocks the LLM call entirely (FR-005)
- No retry on HTTP 429 in v0 (FR-014); mark `rate-limited` and continue

**Scale/Scope**: Per-build sequential processing; typical builds have 0–50 unresolved items

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Plugin-First (NON-NEGOTIABLE) | ✅ PASS | `LLMJudge` consumes `LLMProvider` ABC already defined in `plugins/base.py`; OpenAI-compatible provider is a separate plugin; `TraversalEngine` core is untouched |
| II. Projection Join | ✅ PASS | LLM proposals grounded via reverse index lookup (same join logic); no shortcut to name-matching |
| III. Global Index, Anchor Traversal | ✅ PASS | LLM pass runs after the global index is fully built; grounding uses that same index |
| IV. CI/CD Attribution | ✅ PASS | LLM pass runs post-attribution; attribution results are part of the evidence corpus |
| V. Capability Detection (NON-NEGOTIABLE) | ✅ PASS | No LLM config → silent structured-mode fallback (FR-013); endpoint failures → skip item, not build failure (FR-014) |
| VI. Evidence-Backed Edges | ✅ PASS | LLM-judged edges carry `provenance=llm-judged`, `confidence=low`, `evidence[]` (context + grounding locator), `deployed_ref`, `llm_trace` reference |
| VII. Non-Fabrication (NON-NEGOTIABLE) | ✅ PASS | Grounding step mandatory before edge write (FR-006/007); ungrounded → rejected; null/empty/malformed LLM responses → discarded; LLM cannot auto-pick among genuinely ambiguous candidates (FR-009) |
| VIII. Grounded LLM Judgment | ✅ PASS | Core design of M9: LLM proposes, reverse-index grounding validates; structured mode unaffected (FR-016) |
| IX. Read-Only, Secret-Redacting (NON-NEGOTIABLE) | ✅ PASS | Secrets redacted before request build; PII blocks call; LLM judge has read-only lookup tools only (FR-018); no write paths |
| X. Deployed-Ref Accuracy | ✅ PASS | LLM pass inherits `deployed_ref` from structured pass; all LLM-judged edges carry the same deployed ref |

**Post-Phase-1 re-check**: All gates re-verified after contract design — no violations.
The `LLMJudge` post-processor is read-only, secret-redacting, and grounding-mandatory.
The residency gate satisfies FR-005. Prompt contracts are versioned and distinct per type.

---

## Project Structure

### Documentation (this feature)

```text
specs/004-m9-llm-hybrid-mode/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (validation guide)
├── contracts/           # Phase 1 output
│   ├── mode-activation.md           # CLI/config/env activation contract
│   ├── prompt-ambiguous-match.md    # AMBIGUOUS_MATCH prompt contract v1
│   ├── prompt-unresolved-ref.md     # UNRESOLVED_REF prompt contract v1
│   └── prompt-identity-class.md     # IDENTITY_CLASS prompt contract v1
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
# New package: LLM judge and support modules
tendril/llm/
├── __init__.py
├── judge.py             # LLMJudge: post-processor orchestrating the LLM pass
├── redactor.py          # SecretRedactor + ResidencyGate (PII detection)
├── cache.py             # DiskResponseCache: SHA-256-keyed disk cache
├── grounding.py         # GroundingStep: reverse index lookup + result model
└── contracts/
    ├── __init__.py
    ├── base.py              # PromptContract ABC + response validation
    ├── ambiguous_match.py   # AMBIGUOUS_MATCH v1 contract
    ├── unresolved_ref.py    # UNRESOLVED_REF v1 contract
    └── identity_class.py    # IDENTITY_CLASS v1 contract

# New LLM provider plugin
tendril/connectors/llm/
├── __init__.py
└── openai_provider.py   # OpenAICompatibleProvider: LLMProvider ABC implementation

# New test fixtures
tests/fixtures/conformance/llm/
└── complete_responses.json   # Canned LLM responses covering all three decision types

tests/fixtures/golden/m9-hybrid/   # M9-specific fixture (≥ 20 % unresolved structured baseline)
├── vcs/
│   ├── repos.json
│   ├── anchor_tree.json
│   ├── anchor_files.json
│   ├── sidecar_tree.json
│   └── sidecar_files.json
├── cicd/
│   └── github_actions/
│       └── vars_anchor.json     # Contains an unresolvable-secret token
└── expected/
    ├── structured_unknowns.json # Expected unknowns list from structured pass
    └── hybrid_edges.json        # Expected edges after LLM pass

# New test files
tests/conformance/llm/
└── test_llm_provider.py   # LLM provider conformance suite (fixture-mode)

tests/integration/
└── test_hybrid_mode.py    # End-to-end hybrid build with mock LLMProvider

# Modified files (minor extensions only)
tendril/models/ir.py       # Extend Unresolved.reason enum with LLM skip-reason markers
tendril/models/graph.py    # Add llm_trace: str | None to DependsOn
tendril/cli/main.py        # Wire --mode hybrid: call LLMJudge after traverse()
tendril/config.py          # Add [llm] and [llm_cache] config sections
tendril/query/engine.py    # Extend explain_edge() to surface llm_trace field
```

**Structure Decision**: Single-project (Option 1). New `tendril/llm/` package holds all
M9-specific logic. The `LLMJudge` post-processor pattern keeps `TraversalEngine` untouched
(Constitution Principle I). The OpenAI-compatible provider lives in `tendril/connectors/llm/`
alongside existing connector families.

---

## Complexity Tracking

> No constitution violations requiring justification. The `LLMJudge` post-processor is the
> documented "LLM proposes; grounding validates" pattern (SPEC.md §3, Constitution §VIII).
> All provider and tool seams were pre-defined in M0 (`LLMProvider` ABC, `Provenance.LLM_JUDGED`).
