# Implementation Plan: M10 — Telemetry Cross-Validation (Datadog)

**Branch**: `005-m10-telemetry-datadog` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-m10-telemetry-datadog/spec.md`

## Summary

M10 adds three-way static/runtime reconciliation using Datadog telemetry data. A
`DatadogTelemetryProvider` implements the existing `TelemetryProvider` ABC (probing
capabilities per environment, then fetching edges from APM service maps, distributed
traces, structured logs, and RUM). A `CrossValidator` compares runtime-observed edges
against the static graph, producing a `DivergenceReport` with `confirmed`, `static_only`,
and `runtime_only` sets. Runtime-only edges are persisted to the graph store as
`DEPENDS_ON` edges with `provenance=observed` and are queryable through the existing
`QueryEngine` and MCP server. All logic runs against recorded JSON fixtures with no live
credentials required.

## Technical Context

**Language/Version**: Python 3.12+ (same as M0–M9; editable install via `pip install -e ".[dev]"`)

**Primary Dependencies**:
- Existing: `kuzu` (graph store), `pyyaml`, `tomli`/`tomllib` (config), `uvicorn`/`fastapi` (MCP server)
- New: `httpx` (async-capable HTTP client for Datadog REST API calls; used only in live mode, not fixture mode)

**Storage**: Embedded Kùzu graph store via existing `KuzuStore` adapter. Runtime-only edges are written as `DEPENDS_ON` edge rows. No schema changes required — the existing `DEPENDS_ON` edge table already carries `env`, `provenance`, `confidence`, `evidence`, `deployed_ref`, `ambiguous`, `stale`, `llm_trace`.

**Testing**: `pytest` with recorded JSON fixtures. Conformance suite base class `ConformanceTelemetryProvider` already exists at `tests/conformance/test_telemetry_provider.py`. M10 adds Datadog-specific conformance tests and integration tests. All 175 existing tests must continue to pass.

**Target Platform**: Linux server (CLI tool + optional MCP server). Same as M0–M9.

**Project Type**: Library/CLI extension — additive module behind existing plugin contract.

**Performance Goals**: Sequential per-environment reconciliation. No parallelism in v0. Configurable per-call timeout (default 60s). Warning at >10,000 resolved ObservedEdges per reconcile call.

**Constraints**: Zero-credential CI (fixture-only tests). Read-only Datadog API access. Secret redaction before persistence. No retry logic in v0. Configurable lookback window (default 24h).

**Scale/Scope**: Per-environment reconciliation. Linear scaling across environments. Paginated API responses with configurable max results (default 1,000 per method per env).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Plugin-First Architecture — PASS

`DatadogTelemetryProvider` implements the existing `TelemetryProvider` ABC from
`tendril/plugins/base.py`. No core changes required. The provider declares capabilities
via `tendril-plugin.toml`. `CrossValidator` takes a `GraphStore` + `TelemetryProvider`
as constructor args — no global state. The `kind=service-tag` identity type (FR-023) is
a new identity kind added to the reverse index, not a core change.

### II. The Projection Join — PASS

FR-023 specifies a two-step reverse-index lookup for service name → repo_id resolution:
(1) exact match on `kind=service-tag`, (2) hostname-suffix match. No name-matching
shortcut. Ambiguous matches go to `unknowns` with `reason='ambiguous-match'` and
candidates listed. Unresolvable names go to `unknowns` with `reason='no-index-match'`.

### III. Global Index, Anchor Traversal — PASS

M10 consumes the existing global `ReverseIndex` (built by `TraversalEngine` before
reconciliation). Telemetry service names are resolved against the full index, not just
anchor repos. No changes to index scope.

### IV. CI/CD Attribution is Per-Repo — N/A

M10 does not modify CI/CD attribution. It operates after the static graph is built.

### V. Capability Detection and Graceful Degradation — PASS (critical path)

This is the core design of M10. `probe(env)` is mandatory before any data fetch (FR-001,
FR-003). Missing capabilities are skipped with DEBUG log. Missing credentials skip the
entire telemetry pass with INFO log (FR-007). Failed probes are treated as inactive with
WARNING log. API errors mark capabilities as degraded, not failed. Exit code is always 0.

### VI. Evidence-Backed, Confidence-Scored Edges — PASS

Every runtime-only edge carries `provenance=observed`, confidence per FR-004 rules (high
for APM, high/medium for traces/logs based on occurrence count), non-empty evidence with
FR-021 locator format (`datadog:{capability}:{env}:{api_path}@{iso_timestamp}`), and
`deployed_ref` (inherited from static graph or null).

### VII. Honesty and Non-Fabrication — PASS

Unresolvable service names → `unknowns`, not guessed edges. Ambiguous matches →
`unknowns` with candidates, not auto-picked. `static_only` is flagged for review, not
deleted. Partial capability data is honestly labeled in report metadata.

### VIII. Grounded LLM Judgment — N/A

M10 does not use LLM judgment. All edges come from observed Datadog telemetry data,
resolved against the deterministic reverse index.

### IX. Read-Only and Secret-Redacting — PASS (critical path)

FR-011: no write calls to Datadog API. FR-013: sensitive values redacted before
persistence using SecretRedactor + ResidencyGate PII patterns from M9. DD_API_KEY and
DD_APP_KEY never stored in evidence, logs, or graph edges.

### X. Deployed-Ref Accuracy — PASS

FR-004: `deployed_ref` on runtime-only edges is inherited from the static graph's
`DEPLOYED_AS` record for the same repo+env. If absent (repo not in static graph),
`deployed_ref` is null — honest, not fabricated.

### Constitution Gate Result: **ALL GATES PASS**

No violations. No complexity tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/005-m10-telemetry-datadog/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
tendril/
├── connectors/
│   └── telemetry/
│       ├── __init__.py
│       └── datadog_provider.py      # DatadogTelemetryProvider implementation
├── core/
│   └── cross_validate.py            # CrossValidator + DivergenceReport
├── models/
│   ├── ir.py                        # ObservedEdge already defined; add Capabilities type if needed
│   └── graph.py                     # DependsOn already defined; no changes
├── plugins/
│   └── base.py                      # TelemetryProvider ABC already defined; no changes
├── cli/
│   └── main.py                      # Add `tendril telemetry reconcile --env` subcommand
│                                    # + integration into `graph build` when DD creds present
└── config.py                        # Add DatadogConfig + load_datadog_config()

tests/
├── conformance/
│   └── telemetry/
│       └── test_datadog_conformance.py   # Datadog conformance suite
├── fixtures/
│   └── conformance/
│       └── telemetry/
│           └── datadog/
│               ├── service_dependencies_prod.json
│               ├── edges_from_traces_prod.json
│               ├── edges_from_logs_prod.json
│               ├── edges_from_rum_prod.json
│               └── capabilities_prod.json
├── integration/
│   └── test_telemetry_reconcile.py       # End-to-end reconcile integration tests
└── unit/
    ├── test_datadog_provider.py          # Unit tests for provider
    └── test_cross_validator.py           # Unit tests for CrossValidator
```

**Structure Decision**: Single-project layout following existing convention. New code
lives under `tendril/connectors/telemetry/` (provider) and `tendril/core/` (cross-validator).
No new top-level packages. Fixtures follow the established `tests/fixtures/conformance/{type}/{name}/`
pattern.

## Complexity Tracking

> No constitution violations to justify. All gates pass cleanly.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *None*    | —          | —                                   |
