# Data Model: Roslyn IntraRepoProvider (M8)

**Phase 1 output** | **Date**: 2026-06-15 | **Plan**: [plan.md](plan.md)

---

## Entities

### IntraRepoFacts

Top-level response from `TendrilRoslyn analyze` RPC call. Returned by
`RoslynIntraRepoProvider.analyze(repo_path)`.

```json
{
  "def_use": {
    "<key_name>": ["<relative_path>:<key_or_line>", "..."]
  },
  "value_sets": {
    "<key_name>": [
      {
        "value": "<string>",
        "source": "<relative_path>:<key_or_line>",
        "condition": "<appsettings.prod.json | null>",
        "layer": 1
      }
    ]
  },
  "call_graph": null,
  "partial_analysis": false,
  "truncated": false,
  "skipped_files": []
}
```

**Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `def_use` | `dict[str, list[str]]` | yes | Key → ordered list of source locators (source of truth for def-use chain) |
| `value_sets` | `dict[str, list[ValueSet]]` | yes | Key → all known values with layer/condition metadata |
| `call_graph` | `null` | yes | Always `null` in M8; reserved for future call-graph analysis |
| `partial_analysis` | `bool` | yes | `true` when layer 2 failed; callers MUST treat layer-2 def-use chains as absent |
| `truncated` | `bool` | yes | `true` when response exceeded 10 MB and was truncated to top-N symbols |
| `skipped_files` | `list[SkippedFile]` | yes | Files/projects excluded due to parse/build/language errors |

**Constraints:**
- `partial_analysis: true` → layer-2 entries in `value_sets` MAY be absent or incomplete;
  the traversal engine records `source_analysis: partial` in edge evidence.
- `truncated: true` → response is a subset of all symbols; only the most-referenced appear.
- When `partial_analysis: true`, the `def_use` chains for layer-2 entries are unreliable;
  callers must rely only on layer-1 entries for resolution.

---

### ValueSet

One entry in `IntraRepoFacts.value_sets[key]`. Represents a single known value for a key,
from a single source and layer.

```json
{
  "value": "https://d-ui.prod.example.com",
  "source": "web.config:LandingPageUrl",
  "condition": null,
  "layer": 1
}
```

**Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `value` | `str` | yes | Always a string; non-string JSON values coerced per CHK029 |
| `source` | `str` | yes | `"<relative_path>:<key_or_line>"` — config key name or source line number |
| `condition` | `str | null` | yes | Basename of most-specific config file (e.g., `"appsettings.prod.json"`), or `null` for unconditioned values |
| `layer` | `1 | 2` | yes | `1` = config-file parsing; `2` = C# AST analysis |

**Source locator format** (CHK002):
- Config locator: `"web.config:LandingPageUrl"` — key name from `<add key="..." value="..."/>`
- JSON locator: `"appsettings.json:ConnectionStrings:DefaultConnection"` — colon-separated path
- Source locator: `"src/AppConfig.cs:42"` — relative path + line number (1-indexed)

**Non-string coercion** (CHK029): `8080` → `"8080"`, `true` → `"true"`, `false` → `"false"`,
`null` → `""`, numbers → raw JSON text representation.

---

### ResolvedValue

Return type from `RoslynIntraRepoProvider.resolve_value(key)` when the key is found.
`resolve_value()` always applies the disambiguation tiebreak and returns a single result.

```json
{
  "resolved": true,
  "value": "https://d-ui.prod.example.com",
  "source": "web.config:LandingPageUrl",
  "def_use_chain": ["web.config:LandingPageUrl"],
  "layer": 1
}
```

**Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `resolved` | `true` | yes | Literal `true` for the resolved variant |
| `value` | `str` | yes | The resolved string value |
| `source` | `str` | yes | The winning source locator |
| `def_use_chain` | `list[str]` | yes | Ordered locators from definition to use |
| `layer` | `1 | 2` | yes | Layer that produced the winning value |

**Disambiguation tiebreak** (CHK031/CHK032):
1. Layer 2 over layer 1
2. Most-specific config file (e.g., `appsettings.prod.json` > `appsettings.json`)
3. Alphabetical on source locator (deterministic final tiebreak)

---

### Unresolved

Return type from `resolve_value()` when the key cannot be resolved.

```json
{
  "resolved": false,
  "reason": "not-found",
  "detail": null
}
```

**Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `resolved` | `false` | yes | Literal `false` for the unresolved variant |
| `reason` | `str` (enum) | yes | See Reason enum below |
| `detail` | `str | null` | no | Human-readable context for debugging |

**Reason enum** (CHK018/CHK033):

| Reason | When |
|--------|------|
| `"not-found"` | Key absent from all layers after full analysis |
| `"dynamic-value"` | Key found but value is a runtime expression, not a literal |
| `"is-secret"` | Key matched a redact pattern; value suppressed (CHK006, FR-M8-012) |
| `"build-failed"` | C# compilation failed (layer 2b unavailable) |
| `"parse-error"` | Config file could not be parsed (layer 1 failure for this file) |
| `"nuget-restore-failed"` | NuGet package restore failed (layer 2b unavailable) |
| `"workspace-load-failed"` | MSBuild project/solution load failed (layer 2b unavailable) |

---

### SubprocessError

Python exception raised by `SubprocessBridge.call()` on RPC errors or subprocess failures.

```python
class SubprocessError(Exception):
    method: str           # RPC method name that failed
    message: str          # Human-readable error message
    code: int             # JSON-RPC error code (-32700, -32600, -32601, -32603)
    restarted: bool       # True if bridge successfully restarted before surfacing error
    detail: dict | None   # Optional structured context from C# error response
```

**Lifecycle** (CHK016/CHK037):
- `restarted=False, SubprocessError raised` when: second failure after restart attempt, or
  restart itself failed, or timeout after restart.
- `restarted=True` is NOT raised in M8 — the restarted process re-executes the call. If the
  re-execution also fails, `restarted=False` is used (to avoid confusion). This field is
  reserved for observability (logging) rather than caller branching in M8.

---

### SkippedFile

Entry in `IntraRepoFacts.skipped_files`. Records a file or project excluded from analysis.

```json
{
  "path": "src/LegacyModule/LegacyModule.csproj",
  "reason": "workspace-load-failed"
}
```

**Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `path` | `str` | yes | Relative path to repo root |
| `reason` | `str` | yes | Same enum as `Unresolved.reason` where applicable; `"unsupported-language"` for non-C#/VB projects |

---

## State Transitions

### SubprocessBridge Lifecycle

```
                    __enter__()
      ────────────────────────────────► STARTING
                                             │ _start() + _handshake()
                                             ▼
      IDLE ◄──────────────────────────── READY
       │                                     │
       │ call() → with self._lock            │
       ▼                                     │
     LOCKED ──────────────────────────────── │
       │ _send_recv()                        │
       ▼                                     │
    WAITING_RESPONSE                         │
       │ success                             │
       ├────────────────────────────────────►┘
       │ error/crash
       ▼
    RESTARTING (at-most-once)
       │ success                             │
       ├────────────────────────────────────►┘
       │ failure
       ▼
    ERROR (SubprocessError raised to caller)

      __exit__():  READY/LOCKED/ERROR → CLOSED (stdin EOF → child exits)
```

### IntraRepoFacts Layer States

```
  repo_path received
       │
       ▼
  Layer 1 runs (always)
  web.config + appsettings*.json parsed
       │
       ├── parse error → SkippedFile added; continue
       │
       ▼
  Layer 2a: Syntactic analysis (always attempted)
  SyntaxTree walking for const/field/property
       │
       ├── file unreadable → SkippedFile added; continue
       │
       ▼
  Layer 2b: Semantic analysis (attempted if MSBuild available)
  MSBuildWorkspace + compilation
       │
       ├── NuGet/build/load failure → partial_analysis=true; skipped_files populated
       │                              result returned with layer-1 data only
       │
       ▼
  IntraRepoFacts constructed and serialized
  (truncated=true if >10MB)
```

---

## Validation Rules

1. Every `ValueSet` entry MUST have `layer` ∈ `{1, 2}`.
2. `def_use_chain` locators MUST use format `"<relative_path>:<key_or_line>"` (never absolute).
3. Secret-matched keys (per `tendril.toml [redact_patterns]`) MUST NOT appear in `value_sets`
   or `def_use` — the key name itself is retained but the value is replaced with `Unresolved(reason="is-secret")`.
4. `call_graph` MUST be `null` in all M8 responses.
5. `partial_analysis` and `truncated` MUST be present in every `IntraRepoFacts` response.
6. `SkippedFile.path` MUST be relative to `repo_path` (the `analyze` call's `params.repo_path`).
