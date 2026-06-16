# Data Model: M10 — Telemetry Cross-Validation (Datadog)

**Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

## Entities

### Capabilities (existing, extended)

Per-environment probe result returned by `TelemetryProvider.probe(env)`.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `apm` | `bool` | APM service map available | Required |
| `logs` | `bool` | Log search available | Required |
| `traces` | `bool` | Distributed trace search available | Required |
| `rum` | `bool` | RUM event search available | Required |

**Location**: Already defined as a dict return type in `TelemetryProvider.probe()`. M10
formalizes this as a `@dataclass` in `tendril/models/ir.py` (or keeps it as
`dict[str, bool]` if the existing convention is followed).

**State transitions**: None — immutable result of a single probe call. Not cached across
`reconcile()` calls (FR-003).

---

### ObservedEdge (existing)

A runtime-witnessed service-to-service call, pre-resolution (uses Datadog service names,
not graph `repo_id`s).

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `from_service` | `str` | Datadog service name (caller) | Non-empty |
| `to_service` | `str` | Datadog service name (callee) | Non-empty |
| `env` | `str` | Environment tag | Non-empty |
| `capability` | `str` | Signal source: `apm`, `traces`, `logs`, `rum` | Must be one of the 4 |
| `last_seen` | `str` | ISO 8601 timestamp of last observation | Optional |
| `sample_count` | `int` | Number of observations for this pair | Default 0 |

**Location**: `tendril/models/ir.py` (lines 176–182, already defined).

**Note**: `ObservedEdge` is the pre-resolution form. After identity resolution (FR-023),
edges are converted to `ResolvedObservedEdge` for set operations.

---

### ResolvedObservedEdge (new)

An `ObservedEdge` after service name resolution to graph `repo_id`s. Used internally
by `CrossValidator` for set operations.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `from_id` | `str` | Resolved graph `repo_id` (caller) | Non-empty |
| `to_id` | `str` | Resolved graph `repo_id` (callee) | Non-empty |
| `env` | `str` | Environment | Non-empty |
| `evidence` | `list[Evidence]` | Accumulated evidence from all contributing signals | Non-empty |
| `confidence` | `Confidence` | Per FR-004 rules | Required |
| `deployed_ref` | `str \| None` | Inherited from static graph DEPLOYED_AS, or null | Optional |

**Deduplication key**: `(from_id, to_id, env)` — edges from multiple signals with the
same key are merged; evidence lists are concatenated and sorted by
`(capability, iso_timestamp, api_path)` per FR-010.

**Confidence assignment** (FR-004):
- APM service map: always `Confidence.HIGH`
- Traces/Logs: `Confidence.HIGH` if `sample_count > 1`, else `Confidence.MEDIUM`
- RUM: `Confidence.HIGH` (aggregated browser traffic)
- Merged edge: highest confidence among contributing signals

---

### DivergenceReport (new)

Result of reconciliation for one environment. The primary output of `CrossValidator.reconcile()`.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `env` | `str` | Environment reconciled | Non-empty |
| `confirmed` | `list[ConfirmedEdge]` | Edges in both static and runtime | May be empty |
| `static_only` | `list[StaticOnlyEdge]` | Static edges with no observed traffic | May be empty |
| `runtime_only` | `list[RuntimeOnlyEdge]` | Observed edges not in static graph | May be empty |
| `unknowns` | `list[UnknownService]` | Unresolvable service names | May be empty |
| `capabilities_probed` | `dict[str, bool]` | Capability → active status | Required |
| `metadata` | `list[DegradationNotice]` | Signal degradation notices | May be empty |
| `elapsed_seconds` | `float` | Total reconcile wall time | Required |

**Serialization**: JSON via `to_dict()` method. Must pass through `SecretRedactor` before
serialization (FR-013). Used for stdout output, MCP response, and disk write.

---

### ConfirmedEdge (new, informational)

An edge present in both the static graph and runtime telemetry. Not modified in the
graph store (FR-002, FR-005).

| Field | Type | Description |
|-------|------|-------------|
| `from_id` | `str` | Graph repo_id (caller) |
| `to_id` | `str` | Graph repo_id (callee) |
| `env` | `str` | Environment |
| `static_provenance` | `str` | Original provenance from static graph |
| `static_confidence` | `str` | Original confidence from static graph |
| `runtime_capabilities` | `list[str]` | Which signals confirmed this edge |

---

### StaticOnlyEdge (new, informational)

A static graph edge with no corresponding runtime traffic. Surfaced in the report
(FR-017) but never deleted or modified.

| Field | Type | Description |
|-------|------|-------------|
| `from_id` | `str` | Graph repo_id (caller) |
| `to_id` | `str` | Graph repo_id (callee) |
| `env` | `str` | Environment |
| `provenance` | `str` | Original provenance |
| `confidence` | `str` | Original confidence |

---

### RuntimeOnlyEdge (new)

An observed edge not present in the static graph. Written to the graph store as a
`DEPENDS_ON` edge with `provenance=observed` (FR-004).

| Field | Type | Description |
|-------|------|-------------|
| `from_id` | `str` | Graph repo_id (caller) |
| `to_id` | `str` | Graph repo_id (callee) |
| `env` | `str` | Environment |
| `confidence` | `str` | Per FR-004 rules |
| `evidence` | `list[Evidence]` | Formatted per FR-021 |
| `deployed_ref` | `str \| None` | Inherited from DEPLOYED_AS or null |

**Graph store upsert key**: `(from_id, to_id, env, provenance=observed)` per FR-020.

---

### UnknownService (new)

A Datadog service name that could not be resolved to a graph `repo_id`.

| Field | Type | Description |
|-------|------|-------------|
| `service` | `str` | Datadog service name |
| `env` | `str` | Environment |
| `capability` | `str` | Signal source that reported this service |
| `reason` | `str` | `no-index-match` or `ambiguous-match` |
| `candidates` | `list[str] \| None` | Populated only for `ambiguous-match` |

---

### DegradationNotice (new)

Metadata about a signal source that could not fully contribute to reconciliation.

| Field | Type | Description |
|-------|------|-------------|
| `capability` | `str` | `apm`, `traces`, `logs`, or `rum` |
| `reason` | `str` | One of: `inactive`, `rate-limited`, `error`, `schema-error`, `truncated`, `store-write-error` |
| `message` | `str` | Human-readable description |

---

### DatadogConfig (new)

Configuration for the Datadog provider, loaded from env vars / TOML.

| Field | Type | Default | Source |
|-------|------|---------|--------|
| `api_key` | `str \| None` | None | `DD_API_KEY` env var or `[telemetry.datadog] api_key` |
| `app_key` | `str \| None` | None | `DD_APP_KEY` env var or `[telemetry.datadog] app_key` |
| `site` | `str \| None` | None | `DD_SITE` env var or `[telemetry.datadog] site` |
| `timeout_seconds` | `int` | 60 | `TENDRIL_DD_TIMEOUT_SECONDS` or config key |
| `lookback_hours` | `int` | 24 | `TENDRIL_DD_LOOKBACK_HOURS` or config key |
| `max_results` | `int` | 1000 | `TENDRIL_DD_MAX_RESULTS` or config key |

**Completeness check** (`is_complete() -> bool`): All of `api_key`, `app_key`, and `site`
must be present and non-empty. Incomplete → telemetry skipped (FR-007).

---

### IdentityClass.SERVICE_TAG (new enum value)

Added to the existing `IdentityClass` enum in `tendril/models/ir.py`.

| Value | Normalization | Confidence | Description |
|-------|--------------|------------|-------------|
| `SERVICE_TAG = "service-tag"` | `value.strip()` (preserve case) | `HIGH` | Explicit Datadog service name ↔ repo mapping |

---

## Relationships

```text
DatadogTelemetryProvider
    ├── probe(env) → Capabilities
    ├── service_dependencies(env) → list[ObservedEdge]
    ├── edges_from_traces(env) → list[ObservedEdge]
    ├── edges_from_logs(env) → list[ObservedEdge]
    └── edges_from_rum(env) → list[ObservedEdge]

CrossValidator(store, provider, reverse_index)
    └── reconcile(env) → DivergenceReport
        ├── ObservedEdge → (resolve) → ResolvedObservedEdge
        ├── ResolvedObservedEdge × StaticEdge → ConfirmedEdge
        ├── StaticEdge − ResolvedObservedEdge → StaticOnlyEdge
        ├── ResolvedObservedEdge − StaticEdge → RuntimeOnlyEdge → DEPENDS_ON (graph store)
        └── Unresolved ObservedEdge → UnknownService
```

## Evidence Format (FR-021)

```text
datadog:{capability}:{env}:{api_path}@{iso_timestamp}
```

Examples:
- `datadog:apm:prod:/api/v1/service_dependencies@2026-06-15T10:30:00Z`
- `datadog:traces:prod:/api/v2/spans/events/search@2026-06-15T10:30:05Z`
- `datadog:logs:prod:/api/v2/logs/events/search@2026-06-15T10:30:10Z`
- `datadog:rum:prod:/api/v2/rum/events/search@2026-06-15T10:30:15Z`
