# Contract: TelemetryProvider Conformance Surface

**Date**: 2026-06-15 | **Spec**: [../spec.md](../spec.md)

## Overview

The `DatadogTelemetryProvider` MUST pass the `TelemetryProvider` conformance suite at
`tests/conformance/telemetry/`. This document defines the conformance surface — the
set of behaviors that the suite validates.

## ABC Contract (`tendril/plugins/base.py`)

```python
class TelemetryProvider(ABC):
    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def probe(self, env: str) -> Capabilities: ...

    def service_dependencies(self, env: str) -> list[ObservedEdge]: ...
    def edges_from_traces(self, env: str) -> list[ObservedEdge]: ...
    def edges_from_logs(self, env: str) -> list[ObservedEdge]: ...
    def edges_from_rum(self, env: str) -> list[ObservedEdge]: ...
    def service_catalog(self) -> list[ServiceEntity]: ...
    def deploy_events(self, env: str) -> list[dict[str, Any]]: ...
```

## Conformance Requirements

### C-001: Identity

- `id()` MUST return a non-empty string unique among registered providers.
- For Datadog: `"datadog"`.

### C-002: Probe

- `probe(env)` MUST return a dict-like object with keys `apm`, `logs`, `traces`, `rum`,
  each mapping to `bool`.
- `probe()` MUST be called before any data method for a given env. A data method called
  without a prior successful probe for the same env MUST raise `ProbeRequiredError`.
- `probe()` MUST NOT be cached across `reconcile()` calls.
- Failed probes (exception) → capability treated as inactive, WARNING logged.

### C-003: Data Methods

- Each data method MUST return `list[ObservedEdge]`.
- Each `ObservedEdge` MUST have non-empty `from_service`, `to_service`, `env`.
- `capability` field MUST match the method: `apm` for `service_dependencies`, `traces`
  for `edges_from_traces`, `logs` for `edges_from_logs`, `rum` for `edges_from_rum`.
- Data methods for inactive capabilities MUST NOT be called by the reconciler. If called
  directly (e.g., in tests), they MUST return an empty list or raise `NotImplementedError`.

### C-004: Fixture Mode

- Constructor MUST accept optional `fixture_dir: Path | None`.
- When `fixture_dir` is set, all data methods MUST load from local JSON files instead
  of making live API calls.
- File naming: `{method}_{env}.json` (e.g., `service_dependencies_prod.json`).
- Missing fixture file for an active capability → empty list (not an error).

### C-005: Read-Only

- No data method MAY issue any write/mutation call to the Datadog API.
- The conformance suite validates this by checking that no POST/PUT/PATCH/DELETE calls
  are made to write endpoints (fixture mode inherently satisfies this).

### C-006: Error Handling

- API errors (network, timeout, rate limit, unexpected schema) MUST NOT propagate as
  exceptions from data methods during normal reconcile flow.
- Errors MUST be captured and reported as `DegradationNotice` entries in the
  `DivergenceReport.metadata`.
- The provider itself may raise exceptions; the `CrossValidator` catches and records them.

### C-007: Plugin Manifest

- A `tendril-plugin.toml` MUST exist with:
  ```toml
  [plugin]
  id = "datadog"
  family = "telemetry"
  contract_version = "0.1.0"

  [capabilities]
  apm = true
  traces = true
  logs = true
  rum = true
  service_catalog = false
  deploy_events = false
  ```

## Conformance Test Structure

```python
# tests/conformance/telemetry/test_datadog_conformance.py

class TestDatadogConformance(ConformanceTelemetryProvider):
    """Datadog provider conformance against TelemetryProvider contract."""

    def provider(self) -> TelemetryProvider:
        return DatadogTelemetryProvider(
            fixture_dir=Path("tests/fixtures/conformance/telemetry/datadog")
        )

    def sample_env(self) -> str:
        return "prod"
```

The base class `ConformanceTelemetryProvider` validates C-001 through C-006 automatically.
