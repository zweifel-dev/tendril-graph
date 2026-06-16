# Contract: SubprocessBridge

**Phase 1 output** | **Date**: 2026-06-15

`SubprocessBridge` is the thread-safe `tendril-rpc/v1` client. It manages the lifetime of
the `TendrilRoslyn` subprocess and serializes concurrent callers.

---

## Interface

```python
# tendril/connectors/intra/subprocess_bridge.py

class SubprocessError(Exception):
    """Raised by SubprocessBridge.call() on RPC errors or subprocess failures."""
    method: str           # RPC method that failed
    message: str          # Human-readable error
    code: int             # JSON-RPC error code
    restarted: bool       # True if bridge restarted before surfacing this error
    detail: dict | None   # Structured context from C# error.data, if any


class SubprocessBridge:
    """
    Thread-safe tendril-rpc/v1 subprocess client.
    One request in-flight at a time; concurrent callers queue on the internal lock.
    Subprocess lifetime = instance lifetime.
    """

    def __init__(
        self,
        command: list[str],
        default_timeout: float = 30.0,    # per FR-M8-002
        analyze_timeout: float = 120.0,   # per FR-M8-002b
    ) -> None: ...

    def __enter__(self) -> "SubprocessBridge": ...

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Close subprocess via stdin EOF. Blocks up to 5s, then kills."""
        ...

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Send one RPC call and return the result dict.

        - Clock starts when the lock is acquired (not from queue enqueue time).
        - Timeout: 120s for method="analyze", 30s for all other methods.
        - At-most-one restart per error event.
        - Raises SubprocessError on failure.
        - Thread-safe: multiple threads may call concurrently; calls are serialized.
        """
        ...
```

---

## Protocol Invariants

- Subprocess is started lazily on first `call()` and shared across all callers.
- `__exit__` sends stdin EOF; the subprocess exits cleanly when `ReadLineAsync` returns null.
- `call()` holds `self._lock` for the full write+read cycle — never released between them.
- Timeout clock starts at lock acquisition (FR-M8-002 / CHK015).
- At-most-one restart per error: on crash, the bridge kills and restarts once. If the
  restarted process also fails, `SubprocessError` is raised immediately (CHK037).
- On restart, queued callers block on the lock until restart completes. If restart fails,
  all queued callers receive `SubprocessError(restarted=False)` (CHK037).
- Logging:
  - WARNING on restart: `event="bridge.restart"`, `method`, `attempt`, `binary_path`
  - DEBUG per request cycle: method name; key names excluded if secret-matching (CHK036)

---

## Wire Protocol (`tendril-rpc/v1`)

Newline-delimited JSON over stdin/stdout. One message per line; no embedded newlines.
JSON-RPC 2.0 subset: no batching, no notifications.

**Request** (Python → C#):
```json
{"id": "<uuid-v4>", "method": "<name>", "params": {...}}
```

**Success response** (C# → Python):
```json
{"id": "<uuid-v4>", "result": {...}}
```

**Error response** (C# → Python):
```json
{"id": "<uuid-v4>", "error": {"code": -32603, "message": "...", "data": {...}}}
```

**Handshake** (first exchange on every new subprocess):
```json
// Request:  {"id": "handshake", "method": "handshake", "params": {"client_version": "1.0"}}
// Response: {"id": "handshake", "result": {"server_version": "1.0", "compatible": true}}
```

If `compatible: false`: bridge closes subprocess, raises `SubprocessError`, sets
`capabilities()` to all-false with a clear version-mismatch message (CHK010/CHK028).

**Error codes**:
- `-32700` Parse error
- `-32600` Invalid request / version incompatible
- `-32601` Method not found
- `-32603` Internal error (build failure, OOM, etc.)

---

## Subprocess Configuration

Binary path resolution order (CHK008):
1. `TENDRIL_ROSLYN_BINARY` environment variable (highest priority)
2. `intra_repo.roslyn_binary` in `tendril.toml`
3. No PATH search — explicit path required for reproducibility

If binary is not found:
- Log at WARNING: `event="roslyn-binary-unavailable"` (CHK026 / FR-M8-010)
- `capabilities()` returns all-false
- Do NOT raise; do NOT fail the run (Principle V — NON-NEGOTIABLE)
