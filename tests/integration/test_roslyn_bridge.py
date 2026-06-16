"""Integration tests for SubprocessBridge resilience and capabilities (T023/T024/T025).

All tests use a mock Python subprocess as the TendrilRoslyn replacement.
No live .NET binary required — the mock server is an inline Python script
spawned via sys.executable.

Tests covered:
  - T023: sequential calls, kill-and-restart, at-most-one-restart contract
  - T024: capabilities degradation when binary is missing
  - T025: timeout enforcement and SubprocessError surface contract
"""

from __future__ import annotations

import logging
import sys
import textwrap

import pytest

from tendril.connectors.intra.roslyn_subprocess import RoslynIntraRepoProvider
from tendril.connectors.intra.subprocess_bridge import SubprocessBridge, SubprocessError
from tendril.models.ir import IntraRepoFacts

# ---------------------------------------------------------------------------
# Mock subprocess scripts
# ---------------------------------------------------------------------------

# Long-running echo server: responds to handshake + any "ping" requests
_ECHO_SERVER = textwrap.dedent("""\
    import sys, json
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method", "")
        if method == "handshake":
            result = {"server_version": "1.0", "compatible": True}
        elif method == "ping":
            result = {"pong": True, "seq": req.get("params", {}).get("seq", 0)}
        else:
            result = {}
        resp = {"id": req.get("id"), "result": result}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
""")

# Single-handshake server: responds to exactly one request (the handshake),
# then exits immediately — any subsequent read will see EOF.
_HANDSHAKE_ONLY_SERVER = textwrap.dedent("""\
    import sys, json
    line = sys.stdin.readline()
    req = json.loads(line)
    resp = {"id": req.get("id"), "result": {"server_version": "1.0", "compatible": True}}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
    sys.exit(0)
""")

# Slow server: responds to handshake, then hangs forever on the next request
# (reads from stdin but never writes a response).
_SLOW_SERVER = textwrap.dedent("""\
    import sys, json, time
    line = sys.stdin.readline()
    req = json.loads(line)
    resp = {"id": req.get("id"), "result": {"server_version": "1.0", "compatible": True}}
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
    sys.stdin.readline()   # reads the second request …
    time.sleep(999999)     # … but never writes a response
""")


def _make_bridge(script: str, default_timeout: float = 5.0) -> SubprocessBridge:
    """Create a SubprocessBridge against an inline Python mock server."""
    return SubprocessBridge(
        command=[sys.executable, "-c", script],
        default_timeout=default_timeout,
        analyze_timeout=default_timeout,
    )


# ---------------------------------------------------------------------------
# T023: SubprocessBridge resilience
# ---------------------------------------------------------------------------

class TestSubprocessBridgeResilience:
    """T023: sequential calls, kill-and-restart, at-most-one-restart contract."""

    def test_sequential_calls_return_correct_results(self) -> None:
        """Three sequential call()s return correct results (FR-M8-002)."""
        bridge = _make_bridge(_ECHO_SERVER)
        try:
            for seq in range(3):
                result = bridge.call("ping", {"seq": seq})
                assert result.get("pong") is True, f"Expected pong on seq={seq}"
                assert result.get("seq") == seq, f"Expected seq={seq}, got {result.get('seq')}"
        finally:
            bridge._close()

    def test_kill_and_restart_succeeds(self) -> None:
        """Killing _proc externally → next call() restarts once and returns result."""
        bridge = _make_bridge(_ECHO_SERVER)
        try:
            # Warm up — ensures subprocess is alive and bridge is initialised
            r0 = bridge.call("ping", {"seq": 0})
            assert r0.get("pong") is True

            # Kill the underlying process directly (not through bridge.call)
            proc = bridge._proc
            assert proc is not None, "Bridge must have a live proc after a successful call"
            proc.kill()
            proc.wait()  # block until confirmed dead

            # Next call() detects dead proc, restarts once, and returns a result
            r1 = bridge.call("ping", {"seq": 1})
            assert r1.get("pong") is True
            assert r1.get("seq") == 1
        finally:
            bridge._close()

    def test_crash_triggers_at_most_one_restart_then_error(self) -> None:
        """Server that exits after handshake → at-most-one restart → SubprocessError.

        The server exits after the handshake, so the first real RPC call gets EOF.
        Bridge restarts once; the new server also exits after handshake → second
        EOF is wrapped as SubprocessError (restarted=False).
        """
        bridge = _make_bridge(_HANDSHAKE_ONLY_SERVER)
        try:
            with pytest.raises(SubprocessError) as exc_info:
                bridge.call("ping", {})
            err = exc_info.value
            assert err.method == "ping", f"Expected method='ping', got {err.method!r}"
        finally:
            bridge._close()


# ---------------------------------------------------------------------------
# T024: Capabilities degradation
# ---------------------------------------------------------------------------

class TestCapabilitiesDegradation:
    """T024: RoslynIntraRepoProvider with missing/broken binary → all-false, no abort."""

    def test_no_binary_returns_all_false(self) -> None:
        """binary_path=None → capabilities() returns all-false without raising."""
        provider = RoslynIntraRepoProvider(binary_path=None)
        caps = provider.capabilities()
        assert caps == {"layer1": False, "layer2": False, "def_use": False}

    def test_no_binary_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """binary_path=None → logs WARNING with event=roslyn-binary-unavailable."""
        provider = RoslynIntraRepoProvider(binary_path=None)
        with caplog.at_level(logging.WARNING):
            provider.capabilities()

        assert any(
            "roslyn-binary-unavailable" in r.getMessage()
            or getattr(r, "event", None) == "roslyn-binary-unavailable"
            for r in caplog.records
        ), (
            f"Expected event=roslyn-binary-unavailable in log records; "
            f"got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_no_binary_analyze_returns_partial_facts(self) -> None:
        """binary_path=None → analyze() returns IntraRepoFacts(partial_analysis=True), no raise."""
        provider = RoslynIntraRepoProvider(binary_path=None)
        facts = provider.analyze("/any/path")
        assert isinstance(facts, IntraRepoFacts)
        assert facts.partial_analysis is True

    def test_bad_binary_analyze_returns_partial_facts(self) -> None:
        """Non-existent binary → analyze() returns IntraRepoFacts without raising."""
        provider = RoslynIntraRepoProvider(binary_path="/nonexistent/TendrilRoslyn")
        facts = provider.analyze("/any/path")
        assert isinstance(facts, IntraRepoFacts)
        assert facts.partial_analysis is True


# ---------------------------------------------------------------------------
# T025: Timeout enforcement
# ---------------------------------------------------------------------------

class TestTimeoutEnforcement:
    """T025: Timeout is enforced; SubprocessError is raised from TimeoutError path."""

    def test_call_raises_subprocess_error_on_timeout(self) -> None:
        """Subprocess that never responds → SubprocessError raised within timeout.

        Uses a 1-second timeout to keep the test fast (two 1s timeouts = ~2s total,
        one for the initial attempt and one for the at-most-one restart attempt).
        """
        bridge = _make_bridge(_SLOW_SERVER, default_timeout=1.0)
        try:
            with pytest.raises(SubprocessError) as exc_info:
                bridge.call("ping", {})
            err = exc_info.value
            assert err.method == "ping", f"Expected method='ping', got {err.method!r}"
        finally:
            bridge._close()
