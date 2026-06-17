# Data Model: Production Readiness

**Date**: 2026-06-17
**Feature**: [spec.md](spec.md)

## New Entities

### ProviderConfig (one per provider type)

New config dataclasses following the existing `LLMConfig` / `DatadogConfig` pattern in `tendril/config.py`.

| Config Class | Required Fields | Env Vars | TOML Section |
|---|---|---|---|
| `GitHubConfig` | `token: str` OR (`app_id: str`, `install_id: str`, `private_key_path: str`) | `GH_TOKEN` or `GH_APP_ID` + `GH_INSTALL_ID` + `GH_PRIVATE_KEY_PATH` | `[vcs.github]` |
| `BitbucketDCConfig` | `base_url: str`, `token: str` | `BB_BASE_URL`, `BB_TOKEN` | `[vcs.bitbucket_dc]` |
| `TeamCityConfig` | `base_url: str`, `token: str` | `TC_BASE_URL`, `TC_TOKEN` | `[cicd.teamcity]` |
| `OctopusConfig` | `base_url: str`, `api_key: str`, `space: str` | `OCTO_URL`, `OCTO_API_KEY`, `OCTO_SPACE` | `[cicd.octopus]` |

Each config class has:
- `is_complete() -> bool` — returns True if all required fields are non-empty
- `missing_fields() -> list[str]` — lists which fields are unset
- Factory function `load_*_config() -> *Config` following env var > TOML > default resolution

### HTTPConfig

Shared HTTP resilience configuration.

| Field | Type | Default | Env Var | TOML Key |
|---|---|---|---|---|
| `timeout_seconds` | `int` | `30` | `TENDRIL_HTTP_TIMEOUT` | `[http].timeout` |
| `max_retries` | `int` | `3` | `TENDRIL_HTTP_RETRIES` | `[http].retries` |
| `backoff_base` | `float` | `1.0` | — | `[http].backoff_base` |
| `backoff_factor` | `float` | `2.0` | — | `[http].backoff_factor` |

## Modified Entities

### IndexEntry (existing, tendril/core/index.py)

No schema change. The fix is a caller change: `grounding.py` must use `entry.repo_full_name` (already present) instead of `entry.deployable_id` for edge `to_id`.

### DEPENDS_ON edge (existing, Kuzu DDL)

No schema change. The evidence update fix uses existing `evidence` property — the change is operational (read-then-SET instead of skip-on-exists).

### tendril-plugin.toml manifest (existing)

Version field update only: `contract_version` from `"0.1.0"` to `"1.0.0-alpha"` in the Datadog plugin manifest.

## New Modules

### tendril/connectors/_http.py

Shared HTTP utility module providing `resilient_get(url, headers, config) -> HTTPResult`. Used by all VCS and CI/CD connectors, replacing their individual `_get()` implementations.

```
HTTPResult:
  status: int
  body: bytes
  headers: dict[str, str]
  ok: bool
  error: str | None  # set on non-2xx or connection error
```

## State Transitions

### Graph Build Mode Selection

```
CLI invoked
  ├─ --fixture-dir provided → fixture mode (existing behavior, unchanged)
  └─ --fixture-dir NOT provided → live mode (new)
       ├─ Load provider configs from env/TOML
       ├─ For each provider: is_complete()?
       │   ├─ yes → instantiate, optional validate()
       │   └─ no → skip with WARNING, add to degradation_notices
       ├─ Any VCS provider available?
       │   ├─ yes → proceed with traversal
       │   └─ no → ERROR, exit 1, list required credentials
       └─ Traversal runs with available providers (same engine)
```

### Evidence Merge on Re-Run

```
_write_runtime_edge(edge)
  ├─ Edge exists in store?
  │   ├─ no → INSERT new edge (existing behavior)
  │   └─ yes → READ existing evidence
  │         ├─ Merge: existing + new evidence
  │         ├─ Deduplicate by (locator, capability)
  │         ├─ Keep newest timestamp per unique key
  │         └─ SET merged evidence on edge
  └─ Return
```
