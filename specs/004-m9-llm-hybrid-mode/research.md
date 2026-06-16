# Research: M9 — LLM Hybrid Mode

*Phase 0 output for `specs/004-m9-llm-hybrid-mode/plan.md`*

---

## Decision 1: LLM Client Library

**Decision**: Use the `openai` Python SDK with a configurable `base_url` parameter.

**Rationale**: The spec states the LLM provider must implement the OpenAI Chat Completions
API format (spec §Assumptions). The `openai` SDK handles this natively and supports
`base_url` overrides, making it compatible with every major self-hosted runtime (Ollama,
vLLM, LM Studio) and cloud gateway (Azure OpenAI, Bedrock Converse via LiteLLM proxy,
direct Anthropic API via compatible gateway). The SDK handles JSON-mode structured output,
configurable timeouts (FR-014), and graceful error surfacing (HTTP 429 is distinct from
other errors).

**Alternatives considered**:
- `httpx` direct — avoids the `openai` dependency but requires re-implementing auth,
  streaming, error-code handling, and timeout semantics. No advantage for v0.
- `litellm` — provides unified multi-provider routing but is a heavy dependency (100+ MB);
  in v0 only one provider type is needed; defer to a future release if multi-provider
  fan-out becomes a requirement.
- `requests` — synchronous but no structured-output support; more boilerplate than `openai`.

**How to apply**: `tendril/connectors/llm/openai_provider.py` constructs `openai.OpenAI(
base_url=cfg.endpoint, api_key=cfg.api_key, timeout=cfg.timeout_seconds)` and calls
`client.chat.completions.create(model=cfg.model, temperature=0, ...)`. The `api_key` field
is never logged or persisted (it is consumed at call time only).

---

## Decision 2: Disk Cache Implementation

**Decision**: Plain JSON files in a flat directory, keyed by SHA-256 of the canonical
(goal, sorted locators) pair. Zero external dependencies.

**Rationale**: v0 LLM pass is sequential (one item at a time), so concurrency is not a
concern. A flat directory of `{sha256}.json` files is the simplest possible persistent
key-value store, requires only `pathlib` and `json` from the stdlib, and is trivially
invalidated by deleting the directory (FR-011). Each file stores the raw LLM response plus
the goal/locators used to generate the key, enabling offline inspection and debugging.

**Cache key construction**:
```python
import hashlib, json

def make_cache_key(goal: str, locators: list[str]) -> str:
    payload = json.dumps(
        {"goal": goal, "locators": sorted(locators)},
        sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()
```

**Alternatives considered**:
- `diskcache` — better for concurrent writes but adds a dependency; overkill for v0
  sequential use.
- `shelve` / `dbm` — stdlib but platform-specific format; harder to inspect manually.
- SQLite — good choice if cache ever needs querying; defer until needed.

**How to apply**: `DiskResponseCache` in `tendril/llm/cache.py` wraps `pathlib.Path`
reads/writes. On init it creates the cache directory if absent. If the directory is
inaccessible, it logs a WARNING and runs without caching (FR-011). Grounding always
re-runs even on cache hits (FR-011 — "cache stores only the raw LLM response").

---

## Decision 3: PII Detection for Residency Gate

**Decision**: Pattern-based detection using `re` (stdlib) — email regex, E.164-ish phone
regex, and a fixed list of conventional personal-identity field names.

**Rationale**: The spec explicitly scopes PII detection to pattern-based matching and
excludes ML-based classification from M9 (spec §Assumptions). The three categories from
FR-005 (email, phone, field names) cover the realistic evidence corpus in CI/CD variable
stores and config files.

**Email pattern**: `r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'` (simplified
RFC 5322; covers >99 % of addresses in config stores)

**Phone pattern**: `r'\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'` (NANP
and common international formats)

**PII field names**: `{"user", "author", "owner", "email", "name", "contact", "username",
"firstname", "lastname", "fullname", "phone", "mobile", "person", "identity"}`

**Evaluation order**: The residency gate runs *after* secret redaction (FR-005). It
evaluates the post-redaction payload — both evidence field values and the goal description
string. If any pattern matches or any field name is in the PII set, the call is blocked
with marker `unresolvable-redacted`.

**Alternatives considered**:
- Microsoft Presidio — ML-based, high accuracy, but large dependency (spaCy, models);
  excluded by spec.
- spaCy NER — same concerns as Presidio.
- AWS Comprehend / cloud PII detection — requires external call, which introduces latency
  and another credential concern; excluded for v0.

**How to apply**: `ResidencyGate` in `tendril/llm/redactor.py` compiles patterns at
construction time. `gate.evaluate(redacted_payload) -> ResidencyGateResult`. A `blocked`
result with `reason="pii-detected"` causes the item to be marked `unresolvable-redacted`
and the LLM call is skipped.

---

## Decision 4: Integration Pattern — LLMJudge Post-Processor

**Decision**: Implement M9 as a `LLMJudge` class (`tendril/llm/judge.py`) that takes a
completed `TraversalResult` and returns an augmented `TraversalResult`. The CLI calls
`judge.run(result, reverse_index)` after `engine.traverse()` when `--mode hybrid` is set.
`TraversalEngine` core is not modified.

**Rationale**: FR-002 requires the structured pass to complete before any LLM call. The
cleanest expression of this requirement is a strict phase boundary: `traverse()` always
runs to completion, then — if hybrid mode is active — `LLMJudge.run()` processes the
`result.unresolved` list. This keeps `TraversalEngine` a pure deterministic component
(Constitution Principle I). The CLI is the natural place to own the mode decision and
dispatch.

**Alternatives considered**:
- Add an `llm_pass` hook inside `TraversalEngine` — modifies core; violates Principle I;
  harder to test in isolation.
- Separate `HybridEngine` class wrapping `TraversalEngine` — adds indirection with no
  benefit; the post-processor pattern is simpler and the CLI already controls flow.
- Always run LLMJudge but short-circuit when no LLM config is present — mixes concerns;
  prefer explicit mode dispatch in CLI.

**How to apply**: `tendril/cli/main.py` `graph build` command: after `engine.traverse()`
completes, if `mode == "hybrid"` and `LLMConfig` is present, construct `LLMJudge(config,
cache, gate)` and call `result = judge.run(result, reverse_index, store)`. The modified
`TraversalResult` (with new edges + updated unknowns) is then persisted to KuzuStore.

---

## Decision 5: Prompt Contract Versioning

**Decision**: Each prompt contract is a Python module in `tendril/llm/contracts/` containing
a `PROMPT_VERSION` string constant, a Pydantic output model, a `build_prompt()` function,
and a `validate_response()` function. Contracts are versioned independently.

**Rationale**: FR-019 requires distinct versioned contracts per decision type. Pydantic
output models provide structured validation of the LLM response JSON; `validate_response()`
raises a typed error on malformed output (missing required fields, unrecognized enum values,
empty reasoning) so the caller can apply the malformed-output edge case uniformly (discard,
stay unknown, log raw response). Contracts are not shared — copying is intentional.

**Contract versions in v0**:
- `AMBIGUOUS_MATCH_V1 = "ambiguous_match/v1"`
- `UNRESOLVED_REF_V1 = "unresolved_ref/v1"`
- `IDENTITY_CLASS_V1 = "identity_class/v1"`

**Alternatives considered**:
- YAML/JSON schema files — externally inspectable but adds a load step; Python modules
  are simpler to test and version-control.
- Single shared prompt template with type parameter — violates FR-019 ("MUST NOT reuse
  the prompt contract of another"); also makes independent versioning harder.

**How to apply**: `LLMJudge` selects the contract based on item type
(`AMBIGUOUS_MATCH` for multi-candidate items, `UNRESOLVED_REF` for single unresolvable
tokens, `IDENTITY_CLASS` for classification tasks) and calls
`contract.build_prompt(item)` → `LLMRequest`, then `contract.validate_response(raw)` →
typed response model.

---

## Decision 6: Evidence Budget Enforcement

**Decision**: Before constructing the LLM request, the `LLMJudge` filters the evidence
list against two configurable limits: `max_evidence_files` (default 20) and
`max_evidence_bytes` (default 50 000). Items whose cumulative evidence exceeds either
limit are marked `budget-exceeded` and skipped — no truncation is attempted.

**Rationale**: FR-017 mandates bounding per-call evidence and treating over-budget items
as unknowns rather than sending truncated (potentially misleading) context. The spec
explicitly states "items exceeding the budget are queued as unknowns rather than causing
oversized requests." No-truncation avoids a class of subtle correctness errors where a
partial evidence set changes the LLM's conclusion.

**Budget measurement**: File count = number of distinct evidence locators with a
`file:` source type. Byte count = total UTF-8 length of all evidence field values
included in the payload (post-redaction).

**How to apply**: `LLMJudge._check_budget(item) -> bool` returns `False` and appends
`budget-exceeded` to the unknowns list if either limit is exceeded.

---

## NEEDS CLARIFICATION — Resolved

All items from Technical Context are resolved above. No unresolved clarifications remain.

| Item | Resolution |
|------|-----------|
| LLM client library | `openai` SDK, configurable `base_url` |
| Cache persistence format | Flat JSON files, SHA-256 key, `pathlib` only |
| PII detection approach | Regex + field-name heuristics, `re` stdlib |
| Integration hook point | `LLMJudge` post-processor in CLI, after `traverse()` |
| Prompt contract format | Pydantic models, versioned Python modules |
| Evidence budget enforcement | Pre-call filter, no truncation, `budget-exceeded` marker |
