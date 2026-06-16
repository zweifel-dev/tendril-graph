# Contract: TendrilRoslyn RPC Methods

**Phase 1 output** | **Date**: 2026-06-15

`TendrilRoslyn` is the C# net8.0 binary that implements the `tendril-rpc/v1` server.
This document specifies each RPC method's params and result schemas.

---

## Binary Requirements

- **Target framework**: `net8.0` (minimum supported: `net6.0`)
- **Binary path**: set via `TENDRIL_ROSLYN_BINARY` env var or `intra_repo.roslyn_binary`
  in `tendril.toml` (CHK008/CHK009)
- **Entry point**: `Program.Main()` MUST call `MSBuildLocator.RegisterDefaults()` before
  any workspace types are JIT-loaded (load-order constraint)
- **Stdio**: `Console.OpenStandardInput()` / `Console.OpenStandardOutput()` with explicit
  UTF-8; `AutoFlush = false` + explicit `FlushAsync()` after each response

---

## Method: `handshake`

**Params:**
```json
{"client_version": "1.0"}
```

**Result:**
```json
{"server_version": "1.0", "compatible": true}
```

**Semantics:**
- Must be the first RPC exchange on every new subprocess instance.
- `compatible: false` → bridge closes subprocess, raises `SubprocessError`, returns
  all-false capabilities. Server MUST still send a valid JSON response before closing.
- Protocol version in M8 is `"1.0"`. The `id` field is always preserved for future
  multiplexing (CHK039).

---

## Method: `analyze`

**Params:**
```json
{"repo_path": "<absolute_path_to_repo_root>"}
```

**Result:** `IntraRepoFacts` (see data-model.md)

```json
{
  "def_use": {
    "LandingPageUrl": ["web.config:LandingPageUrl"]
  },
  "value_sets": {
    "LandingPageUrl": [
      {"value": "https://d-ui.prod.example.com", "source": "web.config:LandingPageUrl",
       "condition": null, "layer": 1}
    ]
  },
  "call_graph": null,
  "partial_analysis": false,
  "truncated": false,
  "skipped_files": []
}
```

**Semantics:**
- Layer 1 always runs first (web.config + appsettings*.json).
- Layer 2a (syntactic) always attempted.
- Layer 2b (semantic) attempted if MSBuild is available; failure → `partial_analysis: true`.
- Non-.NET repos: return immediately with empty `IntraRepoFacts` (all empty dicts/arrays,
  `partial_analysis: false`). The Python layer calls `.matches()` first (FR-M8-013).
- Response truncated at 10 MB: top-N most-referenced symbols returned, `truncated: true` set
  (FR-M8-014/CHK034).
- `analyze` has a 120-second timeout on the Python side.
- Partial failure (layer 2b fails) MUST NOT cause a JSON-RPC error response — return the
  partial `IntraRepoFacts` with `partial_analysis: true`.

**Error response** (only on total failure — parse error, invalid repo_path, etc.):
```json
{"id": "...", "error": {"code": -32603, "message": "repo_path does not exist", "data": null}}
```

---

## Method: `resolve_value`

**Params:**
```json
{"repo_path": "<absolute_path>", "key": "<key_name>"}
```

**Result:** `ResolvedValue` or `Unresolved`

```json
// Resolved:
{"resolved": true, "value": "https://svc.prod.example.com",
 "source": "src/AppConfig.cs:42", "def_use_chain": ["src/AppConfig.cs:42"], "layer": 2}

// Unresolved:
{"resolved": false, "reason": "not-found", "detail": null}
```

**Semantics:**
- Returns a single result after disambiguation tiebreak (CHK031/CHK032):
  1. Layer 2 over layer 1
  2. Most-specific config file
  3. Alphabetical tiebreak
- The C# binary sends the winning result; disambiguation MAY also be done in Python
  (the Python layer is the authoritative tiebreak implementation).
- `"dynamic-value"` reason: returned when the key exists but its value is not a compile-time
  literal (e.g., computed from another variable, environment variable, etc.).
- Key existence in any file → NOT `"not-found"`; must use the most appropriate reason.
- `"is-secret"` filtering: done in the Python layer before returning to caller (CHK006).

---

## Stderr Contract

`TendrilRoslyn` MUST write ALL diagnostic output to **stderr**, never stdout.

Stdout MUST contain ONLY newline-terminated JSON RPC messages.

Any non-JSON content on stdout causes `json.JSONDecodeError` in the bridge, triggering a
crash-and-restart. This includes:
- .NET startup messages
- MSBuild diagnostic output
- NuGet restore progress
- Exception stack traces

`TendrilRoslyn.csproj` MUST redirect NuGet/MSBuild diagnostic output to stderr.

---

## Graceful Shutdown

When `stdin.ReadLineAsync()` returns `null` (EOF), the server exits cleanly.
No special "quit" message is needed.
The `SubprocessBridge.__exit__()` sends EOF by closing stdin.
Server exit code: `0` for clean shutdown, nonzero for unrecoverable errors.
