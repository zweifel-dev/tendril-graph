# Contract: Mode Activation (M9 — Hybrid Mode)

**Version**: `mode-activation/v1` | **Date**: 2026-06-15

---

## Overview

This contract defines the three activation surfaces for hybrid mode (FR-001) and the
precedence rules between them.

---

## Activation Surfaces

### 1. CLI Flag (highest precedence)

```
tendril graph build --mode hybrid --anchor <repo> --fixture-dir <dir>
```

**Accepted values**: `structured` (default), `hybrid`

If `--mode hybrid` is present, hybrid mode is active regardless of config file or
environment variable.

If `--mode structured` is present, structured mode is forced regardless of config file or
environment variable.

If `--mode` is absent, the effective mode is resolved from config file → env var → default.

---

### 2. Config File (`tendril.toml`)

```toml
[graph]
mode = "hybrid"   # or "structured"
```

Applies when `--mode` is absent. Overrides the environment variable.

---

### 3. Environment Variable (lowest precedence)

```
TENDRIL_GRAPH_MODE=hybrid
```

Applies when both `--mode` is absent and `[graph] mode` is not set in `tendril.toml`.

**Accepted values**: `structured`, `hybrid` (case-insensitive)

---

## Precedence Order

```
CLI flag (--mode)
    overrides
        config file ([graph] mode)
            overrides
                environment variable (TENDRIL_GRAPH_MODE)
                    overrides
                        default: structured
```

---

## Fallback Behaviour

If `mode` resolves to `hybrid` but no complete LLM configuration is present (FR-013):

1. A WARNING is logged: `"Hybrid mode requested but LLM configuration is incomplete
   (missing: {field_names}); falling back to structured mode."`
2. The build proceeds in structured mode.
3. Exit code is 0 (not an error).

"Complete" LLM config requires all three fields: `endpoint`, `model`, `api_key`. If any
is absent or empty, the config is treated as fully absent.

---

## LLM Configuration

Hybrid mode requires the `[llm]` config section (or env vars):

```toml
[llm]
endpoint = "https://api.openai.com/v1"   # or self-hosted base URL
model    = "gpt-4o"
api_key  = "sk-..."                       # use env var for secrets
timeout_seconds      = 60                 # optional, default 60
max_evidence_files   = 20                 # optional, default 20
max_evidence_bytes   = 50000             # optional, default 50000

[llm_cache]
path = "~/.tendril/llm-cache/"           # optional, default ~/.tendril/llm-cache/
```

Environment variable equivalents:

| Config key | Env var |
|-----------|---------|
| `[llm] endpoint` | `TENDRIL_LLM_ENDPOINT` |
| `[llm] model` | `TENDRIL_LLM_MODEL` |
| `[llm] api_key` | `TENDRIL_LLM_API_KEY` |
| `[llm] timeout_seconds` | `TENDRIL_LLM_TIMEOUT` |
| `[llm_cache] path` | `TENDRIL_LLM_CACHE_PATH` |
