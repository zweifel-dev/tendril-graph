# Developer Quickstart: Production Readiness Implementation

**Date**: 2026-06-17
**Feature**: [spec.md](spec.md) | [plan.md](plan.md)

## Setup

```bash
# Clone and install
git clone <repo> && cd tendril-graph
python -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Verify baseline — all 210 tests must pass
.venv/bin/python -m pytest tests/ -v
```

## Implementation Order

The work is organized into 4 groups with dependencies:

```
Group A: Tier 1 Correctness Fixes (independent, parallelizable)
├── FR-001: Fix _path_matches_env (kuzu_store.py:175)
├── FR-002: Fix LLM to_id (grounding.py:54)
├── FR-003: Fix plugin contract version (tendril-plugin.toml:4)
├── FR-004: Fix template marker detection (traversal.py:339)
└── FR-005: Fix evidence update on re-runs (cross_validate.py:397-408)

Group B: Live Infrastructure (sequential)
├── FR-009: HTTP resilience utility (new: connectors/_http.py)
├── FR-007: Provider credential config (extend: config.py)
└── FR-006: Live API mode (modify: cli/main.py _graph_build())

Group C: Connector Fix (independent)
└── FR-008: BB DC recursive tree (bitbucket_dc.py read_tree)

Group D: Test Coverage (independent)
└── FR-010: MCP server tests (new: tests/test_mcp_server.py)
```

## Verification Commands

```bash
# After each fix — run full suite to check for regressions
.venv/bin/python -m pytest tests/ -v

# After FR-001 — verify env filtering
.venv/bin/python -m pytest tests/ -k "env" -v

# After FR-005 — verify evidence merge
.venv/bin/python -m pytest tests/unit/test_cross_validator.py -v

# After FR-009 — verify HTTP resilience (new tests)
.venv/bin/python -m pytest tests/unit/test_http_resilience.py -v

# After FR-010 — verify MCP server
.venv/bin/python -m pytest tests/test_mcp_server.py -v

# After FR-006 — verify live mode (fixture equivalent)
.venv/bin/python -m pytest tests/integration/test_cli_graph_build.py -v

# Full suite final verification
.venv/bin/python -m pytest tests/ -v --tb=short
```

## Key Files Reference

| File | What Changes | FR |
|---|---|---|
| `tendril/store/kuzu_store.py:175` | `return True` → `return False` | FR-001 |
| `tendril/llm/grounding.py:54` | `entry.deployable_id` → `entry.repo_full_name` | FR-002 |
| `tendril/connectors/telemetry/tendril-plugin.toml:4` | `"0.1.0"` → `"1.0.0-alpha"` | FR-003 |
| `tendril/core/traversal.py:339` | `startswith("{")` → `"{" not in` | FR-004 |
| `tendril/core/cross_validate.py:397-408` | Early return → read-merge-SET | FR-005 |
| `tendril/connectors/_http.py` (new) | Shared resilient HTTP utility | FR-009 |
| `tendril/config.py` | Add VCS/CI/CD config classes | FR-007 |
| `tendril/cli/main.py:189-194` | Remove fixture-dir requirement, add live mode | FR-006 |
| `tendril/connectors/vcs/bitbucket_dc.py:68-83` | `/files/{ref}` → `/files?at={ref}` | FR-008 |
| `tests/test_mcp_server.py` (new) | TestClient tests for all endpoints | FR-010 |
