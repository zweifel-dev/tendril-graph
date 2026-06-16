# Data Model: M9 — LLM Hybrid Mode

*Phase 1 output for `specs/004-m9-llm-hybrid-mode/plan.md`*

---

## New Entities

### `LLMConfig` (config.py extension)

Configuration for the LLM provider, resolved from env > toml > defaults (same precedence
as existing config). Stored in `[llm]` TOML section.

| Field | Type | Default | Source | Notes |
|-------|------|---------|--------|-------|
| `endpoint` | `str \| None` | `None` | `TENDRIL_LLM_ENDPOINT` / `[llm] endpoint` | No default; absent → fallback to structured |
| `model` | `str \| None` | `None` | `TENDRIL_LLM_MODEL` / `[llm] model` | No default; absent → fallback |
| `api_key` | `str \| None` | `None` | `TENDRIL_LLM_API_KEY` / `[llm] api_key` | Never logged or persisted |
| `timeout_seconds` | `int` | `60` | `TENDRIL_LLM_TIMEOUT` / `[llm] timeout_seconds` | Per-call timeout (FR-014) |
| `max_evidence_files` | `int` | `20` | `[llm] max_evidence_files` | Evidence budget file cap (FR-017) |
| `max_evidence_bytes` | `int` | `50000` | `[llm] max_evidence_bytes` | Evidence budget byte cap (FR-017) |
| `cache_path` | `str` | `~/.tendril/llm-cache/` | `TENDRIL_LLM_CACHE_PATH` / `[llm_cache] path` | Independent of graph DB |

**Validation**: `is_complete() -> bool` — returns `True` iff `endpoint`, `model`, and
`api_key` are all non-None. Incomplete config triggers structured-mode fallback (FR-013).

---

### `ReasoningTrace` (new dataclass in `tendril/llm/judge.py`)

A record of one LLM decision, stored as the `llm_trace` value on a `DependsOn` edge.
Serialised to JSON and stored at `{cache_path}/traces/{trace_id}.json`. The `llm_trace`
field on the edge holds the `trace_id` string (not the full trace inline, to keep edge
size manageable).

| Field | Type | Notes |
|-------|------|-------|
| `trace_id` | `str` | UUID4; used as filename and as the `llm_trace` edge field |
| `decision_type` | `str` | `AMBIGUOUS_MATCH`, `UNRESOLVED_REF`, or `IDENTITY_CLASS` |
| `contract_version` | `str` | e.g., `ambiguous_match/v1` |
| `redacted_request` | `dict` | Full LLM request payload after redaction (no secrets) |
| `raw_response` | `dict` | Raw LLM response (may be malformed; stored for debugging) |
| `grounding_result` | `GroundingResult` | Serialised grounding step outcome |
| `disposition` | `str` | `accepted`, `rejected`, `ambiguous-kept`, `malformed`, `grounding-failed` |
| `created_at` | `str` | ISO-8601 UTC timestamp |

**Lifecycle**: Replaced when the edge is re-resolved in a subsequent build; no accumulation
(FR-015). Old trace file is overwritten at the same `trace_id`-derived path.

---

### `DiskCacheEntry` (new dataclass in `tendril/llm/cache.py`)

One persisted cache entry: `{cache_path}/{sha256}.json`.

| Field | Type | Notes |
|-------|------|-------|
| `cache_key` | `str` | SHA-256 of `{"goal": ..., "locators": sorted([...])}` |
| `goal` | `str` | Canonical goal description (for debugging) |
| `locators` | `list[str]` | Sorted evidence locator strings |
| `raw_response` | `dict` | Verbatim LLM response (grounding always re-runs) |
| `created_at` | `str` | ISO-8601 UTC timestamp |
| `contract_version` | `str` | The contract version string at time of caching |

**Cache key formula**:
```python
payload = json.dumps({"goal": goal, "locators": sorted(locators)},
                     sort_keys=True, separators=(",", ":"))
sha256 = hashlib.sha256(payload.encode()).hexdigest()
```

---

### `ResidencyGateResult` (new dataclass in `tendril/llm/redactor.py`)

Result of the pre-call PII/residency check.

| Field | Type | Notes |
|-------|------|-------|
| `allowed` | `bool` | `True` if call may proceed |
| `reason_code` | `str \| None` | `None` if allowed; otherwise `"pii-detected"` |
| `trigger` | `str \| None` | Which pattern or field name triggered the block |

---

### `GroundingResult` (new dataclass in `tendril/llm/grounding.py`)

Result of looking up the LLM's proposed candidate in the reverse index.

| Field | Type | Notes |
|-------|------|-------|
| `found` | `bool` | `True` if candidate exists in the reverse index |
| `matched_identity` | `str \| None` | The canonical identity value that matched |
| `index_locator` | `str \| None` | Evidence locator for the matched index entry |
| `error` | `str \| None` | Set if the index lookup itself raised an error (not "not found") |

---

### `LLMJudgeItem` (new dataclass in `tendril/llm/judge.py`)

One item queued for LLM processing. Derived from entries in `TraversalResult.unresolved`.

| Field | Type | Notes |
|-------|------|-------|
| `item_id` | `str` | `{repo_key}:{token_name}:{env}` |
| `decision_type` | `str` | `AMBIGUOUS_MATCH`, `UNRESOLVED_REF`, or `IDENTITY_CLASS` |
| `consumer_ref_id` | `str` | The consumer reference identifier |
| `candidates` | `list[str]` | Non-empty for `AMBIGUOUS_MATCH`; empty for others |
| `evidence` | `list[Evidence]` | Evidence corpus from structured pass (pre-redaction) |
| `goal` | `str` | Canonical goal string (`{DECISION_TYPE}:{primary_identifier}`) |
| `deployed_ref` | `str` | Deployed SHA/branch from structured pass |
| `skip_reason` | `str \| None` | Set to a skip-reason marker if item must be skipped |

---

### Prompt Contract Output Models (Pydantic, `tendril/llm/contracts/`)

#### `AmbiguousMatchResponse` (ambiguous_match.py)

| Field | Type | Constraints |
|-------|------|-------------|
| `decision` | `Literal["keep-ambiguous", "ground-to-candidate"]` | Required |
| `candidate_id` | `str \| None` | Required when `decision == "ground-to-candidate"`; absent otherwise |
| `reasoning` | `str` | Non-empty string required |

**Malformed if**: missing `decision`, unrecognised `decision` value, empty `reasoning`,
or `candidate_id` absent when decision is `ground-to-candidate`.

#### `UnresolvedRefResponse` (unresolved_ref.py)

| Field | Type | Constraints |
|-------|------|-------------|
| `proposed_value` | `str \| None` | `None` if reference is unresolvable |
| `reasoning` | `str` | Non-empty string required |

**Malformed if**: missing `proposed_value` key, or empty `reasoning`.

#### `IdentityClassResponse` (identity_class.py)

| Field | Type | Constraints |
|-------|------|-------------|
| `class_` | `Literal["url", "package", "artifact", "unknown"]` | Required; field name `class` in JSON |
| `reasoning` | `str` | Non-empty string required |

**Malformed if**: missing `class`, unrecognised `class` value, or empty `reasoning`.

---

## Modified Entities

### `Unresolved.reason` (ir.py) — new enum values

Current values: `not-found`, `dynamic-value`, `is-secret`, `build-failed`, `parse-error`,
`nuget-restore-failed`, `workspace-load-failed`.

M9 adds (LLM skip-reason taxonomy from spec):

| New Value | Trigger |
|-----------|---------|
| `llm-error` | LLM endpoint unreachable, returned non-429 error, timed out, or returned malformed output |
| `rate-limited` | LLM provider returned HTTP 429; no retry in v0 |
| `budget-exceeded` | Evidence exceeds `max_evidence_files` or `max_evidence_bytes`; LLM call not attempted |
| `grounding-failed` | LLM returned valid non-null candidate but not found in (or could not be looked up in) the reverse index |
| `unresolvable-redacted` | Residency gate blocked the LLM call due to PII detected in evidence or goal description |

Note: `is-secret` (existing) continues to handle `unresolved-secret` items; the LLM pass
does not attempt these (spec §Skip-Reason Taxonomy).

---

### `DependsOn` (graph.py) — new field

| New Field | Type | Default | Notes |
|-----------|------|---------|-------|
| `llm_trace` | `str \| None` | `None` | UUID4 reference to `ReasoningTrace`; present only on `provenance=llm-judged` edges; replaces previous trace on re-resolution |

No other `DependsOn` fields are modified. Structured-mode edges retain `llm_trace=None`.

---

## State Transitions

### Item Lifecycle (LLM pass)

```text
TraversalResult.unresolved
      │
      ├─ reason == is-secret ──────────────────────────────────► stays unresolved-secret
      │
      ├─ evidence budget exceeded ─────────────────────────────► stays budget-exceeded
      │
      ├─ residency gate blocks ────────────────────────────────► stays unresolvable-redacted
      │
      ├─ LLM call fails (timeout / non-429 error / malformed) ─► stays llm-error
      │
      ├─ LLM call returns HTTP 429 ────────────────────────────► stays rate-limited
      │
      ├─ LLM returns null proposed_value ─────────────────────► stays unresolved (no-candidate)
      │
      ├─ LLM returns candidate ─► grounding lookup
      │                                  │
      │                      ┌───────────┴──────────────┐
      │                      │ found                    │ not found / index error
      │                      ▼                          ▼
      │            write DependsOn edge         stays grounding-failed
      │            provenance=llm-judged
      │            confidence=low
      │            llm_trace=<trace_id>
      │
      └─ AMBIGUOUS_MATCH decision == keep-ambiguous ──────────► stays ambiguous=True (both candidates)
         (LLM reasoning recorded in trace; no edge auto-picked)
```

---

## Validation Rules

1. An LLM-judged edge MUST have `llm_trace != None`.
2. `llm_trace` MUST reference a trace file that exists at `{cache_path}/traces/{trace_id}.json`.
3. `confidence` on an LLM-judged edge MUST be `low` (cannot be promoted by grounding alone).
4. `provenance` on an LLM-judged edge MUST be `llm-judged`.
5. `evidence[]` on an LLM-judged edge MUST be non-empty and MUST include at least one locator
   from the grounding result.
6. A `ReasoningTrace` with `disposition=accepted` MUST have a non-None `grounding_result.matched_identity`.
7. Secret-typed values MUST NOT appear in `ReasoningTrace.redacted_request`.
