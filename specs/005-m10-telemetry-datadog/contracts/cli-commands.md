# Contract: CLI Commands for M10 Telemetry

**Date**: 2026-06-15 | **Spec**: [../spec.md](../spec.md)

## New Command: `tendril telemetry reconcile`

### Synopsis

```
tendril telemetry reconcile --env <env> [--db <path>] [--fixture-dir <path>]
```

### Arguments

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--env` | Yes | — | Environment to reconcile (e.g., `prod`, `staging`). Exit code 1 if omitted. |
| `--db` | No | `:memory:` | Path to Kùzu graph store (must contain a pre-built static graph). |
| `--fixture-dir` | No | None | Path to Datadog fixture directory (for offline testing). |

### Behavior (FR-018)

1. Assumes a static graph already exists in the graph store at `--db`.
2. Loads Datadog configuration (env vars or TOML). If incomplete (FR-007), exits with
   INFO log and code 0 (unless `--fixture-dir` is provided, which bypasses credential
   check).
3. Instantiates `DatadogTelemetryProvider` (with `fixture_dir` if provided).
4. Builds or loads `ReverseIndex` from the graph store.
5. Runs `CrossValidator.reconcile(env)`.
6. Writes `DivergenceReport` to stdout as JSON.
7. Persists `runtime_only` edges to graph store.

### Output

JSON to stdout matching the `DivergenceReport` schema:

```json
{
  "env": "prod",
  "confirmed": [...],
  "static_only": [...],
  "runtime_only": [...],
  "unknowns": [...],
  "capabilities_probed": {"apm": true, "logs": true, "traces": false, "rum": false},
  "metadata": [...],
  "elapsed_seconds": 12.3
}
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (including partial degradation) |
| 1 | Missing `--env` flag (usage error) |

---

## Modified Command: `tendril graph build`

### Change

When Datadog credentials are present and complete (per FR-007), a telemetry reconcile
step runs automatically at the end of `graph build`, after the optional LLM hybrid pass.

### Behavior

1. After static graph is persisted to store:
2. Check `DatadogConfig.is_complete()`.
3. If incomplete → INFO log per FR-007, skip telemetry, build completes normally.
4. If complete → instantiate `DatadogTelemetryProvider`, run
   `CrossValidator.reconcile(env)` for each environment built.
5. Print reconcile summary (counts) to stderr.
6. DivergenceReport is NOT printed to stdout during `graph build` (only during
   standalone `telemetry reconcile`).

### Existing Flags

No new flags added to `graph build`. Telemetry is controlled by credential presence.
`--fixture-dir` already exists and is reused for the Datadog fixture path if a
`telemetry/datadog/` subdirectory exists within it.
