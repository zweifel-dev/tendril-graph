"""Thread-safe tendril-rpc/v1 subprocess client (FR-M8-001/002).

Spawns a child process on first call, keeps it alive for the bridge's
lifetime (one ``tendril graph build`` run), and serializes concurrent
callers via a single threading.Lock.

Wire protocol: newline-delimited JSON-RPC 2.0 subset (no batching) over
stdin/stdout.  Subprocess diagnostics go to stderr (never stdout).
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import uuid
from typing import Any

log = logging.getLogger(__name__)


class SubprocessError(Exception):
    """Raised by SubprocessBridge.call() on RPC errors or process failures.

    Attributes (FR-M8-002 / CHK016):
        method:    RPC method that failed.
        message:   Human-readable error.
        code:      JSON-RPC error code (-32700, -32600, -32601, -32603).
        restarted: True if the bridge attempted a restart before failing.
        detail:    Optional structured context from the C# error.data field.
    """

    def __init__(
        self,
        method: str,
        message: str,
        code: int = -32603,
        restarted: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.message = message
        self.code = code
        self.restarted = restarted
        self.detail = detail


class SubprocessBridge:
    """tendril-rpc/v1 client.  Thread-safe; one request in-flight at a time.

    Subprocess lifetime = instance lifetime.  Use as a context manager:

        with SubprocessBridge(["/path/to/TendrilRoslyn"]) as bridge:
            result = bridge.call("analyze", {"repo_path": "/some/repo"})

    Concurrent callers queue on the internal lock.  The subprocess remains
    single-threaded (one JSON-RPC message at a time).
    """

    def __init__(
        self,
        command: list[str],
        default_timeout: float = 30.0,
        analyze_timeout: float = 120.0,
    ) -> None:
        self._command = command
        self._default_timeout = default_timeout
        self._analyze_timeout = analyze_timeout
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None

    # ── context manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "SubprocessBridge":
        return self

    def __exit__(self, *_: object) -> None:
        """Close the subprocess via stdin EOF (clean shutdown per FR-M8-001)."""
        self._close()

    def _close(self) -> None:
        if self._proc is not None:
            try:
                # stdin EOF signals the C# server to exit its ReadLineAsync loop
                self._proc.stdin.close()  # type: ignore[union-attr]
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
            finally:
                self._proc = None

    # ── subprocess lifetime ───────────────────────────────────────────────────

    def _start(self) -> None:
        """Spawn subprocess and complete handshake.  Caller MUST hold _lock."""
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,  # CRITICAL: unbuffered binary I/O (research.md §1)
        )
        self._handshake()

    def _handshake(self) -> None:
        """Exchange version handshake.  Caller MUST hold _lock."""
        req = {
            "id": "handshake",
            "method": "handshake",
            "params": {"client_version": "1.0"},
        }
        resp = self._send_recv(req, timeout=self._default_timeout)
        result = resp.get("result", {})
        if not result.get("compatible", False):
            self._kill()
            server_version = result.get("server_version", "unknown")
            raise SubprocessError(
                method="handshake",
                message=(
                    f"TendrilRoslyn version mismatch: client=1.0, "
                    f"server={server_version} — update the binary"
                ),
                code=-32600,
                restarted=False,
            )

    def _kill(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc = None

    # ── I/O ──────────────────────────────────────────────────────────────────

    def _send_recv(self, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Write one request line and read one response line.
        Caller MUST hold _lock.
        """
        line = json.dumps(request, separators=(",", ":")) + "\n"
        assert self._proc is not None
        self._proc.stdin.write(line.encode())  # type: ignore[union-attr]
        self._proc.stdin.flush()               # type: ignore[union-attr]
        return self._read_response(timeout)

    def _read_response(self, timeout: float) -> dict[str, Any]:
        """readline() with timeout via a daemon reader thread (research.md §1).

        This is the only portable way to enforce a timeout on a blocking
        readline() from a Popen stdout without asyncio.
        """
        result: list[bytes] = []
        exc: list[Exception] = []

        def _read() -> None:
            try:
                assert self._proc is not None
                result.append(self._proc.stdout.readline())  # type: ignore[union-attr]
            except Exception as e:  # noqa: BLE001
                exc.append(e)

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            # Thread is blocked — kill subprocess to unblock it
            self._kill()
            t.join(timeout=2)
            raise TimeoutError(f"TendrilRoslyn did not respond within {timeout}s")

        if exc:
            raise exc[0]

        raw = result[0] if result else b""
        if not raw:
            raise EOFError("TendrilRoslyn exited unexpectedly (empty stdout)")

        return json.loads(raw.decode("utf-8"))

    # ── public API ────────────────────────────────────────────────────────────

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one RPC call and return the result dict.

        Timeout clock starts when the lock is acquired (FR-M8-002 / CHK015).
        At-most-one restart per error event (FR-M8-002 / CHK037).

        Raises SubprocessError on unrecoverable failure.
        Thread-safe: concurrent callers queue on the internal lock.
        """
        timeout = (
            self._analyze_timeout if method == "analyze" else self._default_timeout
        )
        with self._lock:  # ← clock starts here (FR-M8-002)
            return self._call_locked(method, params, timeout, _restarted=False)

    def _call_locked(
        self,
        method: str,
        params: dict[str, Any],
        timeout: float,
        *,
        _restarted: bool,
    ) -> dict[str, Any]:
        try:
            # Lazy start on first call (or after a previous crash cleared _proc)
            if self._proc is None or self._proc.poll() is not None:
                self._start()

            req = {"id": str(uuid.uuid4()), "method": method, "params": params}
            resp = self._send_recv(req, timeout)

        except (TimeoutError, EOFError, json.JSONDecodeError, OSError, BrokenPipeError) as exc:
            if _restarted:
                # Second failure — do not restart again (CHK037)
                raise SubprocessError(
                    method=method,
                    message=str(exc),
                    code=-32603,
                    restarted=False,
                ) from exc

            # ── at-most-one restart (FR-M8-002 / CHK037) ──────────────────
            log.warning(
                "bridge.restart",
                extra={
                    "event": "bridge.restart",
                    "method": method,
                    "attempt": 1,
                    "binary_path": self._command[0] if self._command else "",
                },
            )
            self._kill()
            try:
                self._start()
                req = {"id": str(uuid.uuid4()), "method": method, "params": params}
                resp = self._send_recv(req, timeout)
            except Exception as exc2:
                raise SubprocessError(
                    method=method,
                    message=str(exc2),
                    code=-32603,
                    restarted=False,
                ) from exc2

        # Surface JSON-RPC error responses as SubprocessError
        if "error" in resp:
            err = resp["error"]
            raise SubprocessError(
                method=method,
                message=err.get("message", "unknown RPC error"),
                code=err.get("code", -32603),
                restarted=_restarted,
                detail=err.get("data"),
            )

        return resp.get("result", {})
