# Contract: CrossValidator

**Date**: 2026-06-15 | **Spec**: [../spec.md](../spec.md)

## Overview

`CrossValidator` performs three-way reconciliation between the static dependency graph
and runtime telemetry data. It is the orchestrator that connects a `TelemetryProvider`
to the `GraphStore`.

## Interface

```python
class CrossValidator:
    def __init__(
        self,
        store: GraphStore,
        provider: TelemetryProvider,
        reverse_index: ReverseIndex,
        redactor: SecretRedactor | None = None,
    ) -> None: ...

    def reconcile(self, env: str) -> DivergenceReport: ...
```

## reconcile(env) Contract

### Preconditions

- `store` is initialized and may or may not contain static graph edges for `env`.
- `provider` is a valid `TelemetryProvider` instance (live or fixture mode).
- `reverse_index` is populated (built by `TraversalEngine` or loaded from store).

### Postconditions

- Returns a `DivergenceReport` for the given `env`.
- `runtime_only` edges are written to `store` as `DEPENDS_ON` with
  `provenance=observed`. Upsert key: `(from_id, to_id, env, provenance=observed)`.
- Existing static edges are NEVER modified (FR-005).
- `DivergenceReport` is redacted before return (FR-013).

### Behavioral Contract

| Step | Action | On Error |
|------|--------|----------|
| 1 | `provider.probe(env)` → `Capabilities` | Exception → all caps inactive, WARNING logged |
| 2 | For each active capability: call data method | Exception → `DegradationNotice`, continue |
| 3 | Deduplicate `ObservedEdge`s by `(from_service, to_service, env)` | — |
| 4 | Resolve service names → `repo_id` via `ReverseIndex` (FR-023) | Unresolved → `UnknownService` |
| 5 | Fetch static `DEPENDS_ON` edges for `env` from `store` | Empty set → not an error (FR-024) |
| 6 | Compute `confirmed`, `static_only`, `runtime_only` | — |
| 7 | Redact evidence via `SecretRedactor` + PII check | PII items omitted (FR-013) |
| 8 | Write `runtime_only` edges to `store` | Write error → `DegradationNotice`, continue (FR-022) |
| 9 | Log reconcile summary at INFO level (FR-027) | — |
| 10 | Return `DivergenceReport` | — |

### Invariants

- **Idempotent** (FR-020): Running reconcile twice for the same env produces the same
  graph state (upsert, not insert).
- **Non-destructive** (FR-005, FR-017): Static edges are never modified or deleted.
- **Always succeeds** (FR-008): Exit code 0 regardless of API errors or degraded
  capabilities. Errors are captured in `metadata`, not propagated.
- **Deterministic output** (FR-010): Evidence lists sorted by
  `(capability, iso_timestamp, api_path)`.

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| Empty static graph for env | `confirmed=[]`, `static_only=[]`, `runtime_only=[all resolved]` (FR-024) |
| No static graph at all (store empty) | WARNING logged (FR-024), same set logic |
| All capabilities inactive | Empty report, metadata shows all inactive |
| >10,000 resolved edges | WARNING logged (FR-026), processing continues |
| Ambiguous service name match | → `UnknownService` with `reason=ambiguous-match`, NOT written as edge |
| Duplicate edge from APM + logs | Merged, evidence combined, sorted (FR-010) |
