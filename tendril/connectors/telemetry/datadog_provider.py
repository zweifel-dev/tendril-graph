"""DatadogTelemetryProvider — Datadog APM/Traces/Logs/RUM telemetry (M10).

Implements the TelemetryProvider ABC from tendril/plugins/base.py.
Supports fixture_dir for zero-credential offline testing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from tendril.models.ir import Capabilities, ObservedEdge
from tendril.plugins.base import ProbeRequiredError, TelemetryProvider

log = logging.getLogger(__name__)


class DatadogTelemetryProvider(TelemetryProvider):
    """Datadog telemetry provider — fixture or live mode.

    Constructor args:
        fixture_dir: Path to directory containing Datadog JSON fixtures.
                     When set, all data methods load from local files instead
                     of making live API calls.
        lookback_hours: Hours of historical data to query (FR-014, default 24).
        timeout_seconds: Per-call timeout in seconds (FR-025, default 60).
        max_results: Max results per API call; truncates with metadata (FR-015, default 1000).
    """

    def __init__(
        self,
        fixture_dir: Path | None = None,
        lookback_hours: int = 24,
        timeout_seconds: int = 60,
        max_results: int = 1000,
    ) -> None:
        self._fixture_dir = fixture_dir
        self._probed_envs: dict[str, Capabilities] = {}
        self.lookback_hours = lookback_hours
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.truncated: bool = False

    def id(self) -> str:
        return "datadog"

    # ------------------------------------------------------------------
    # Probe
    # ------------------------------------------------------------------

    def probe(self, env: str) -> Capabilities:
        """Probe available Datadog capabilities for the given environment.

        In fixture mode, loads capabilities_{env}.json.
        Tracks probed envs for ProbeRequiredError enforcement.
        """
        caps: Capabilities
        if self._fixture_dir:
            caps_path = self._fixture_dir / f"capabilities_{env}.json"
            if caps_path.exists():
                caps = json.loads(caps_path.read_bytes())
            else:
                caps = {"apm": False, "logs": False, "traces": False, "rum": False}
        else:
            # Live mode — not implemented in v0 (fixture-only)
            caps = {"apm": False, "logs": False, "traces": False, "rum": False}

        self._probed_envs[env] = caps
        return caps

    def _require_probe(self, env: str) -> Capabilities:
        """Raise ProbeRequiredError if env was not probed."""
        if env not in self._probed_envs:
            raise ProbeRequiredError(
                f"probe('{env}') must be called before any data method for env '{env}'"
            )
        return self._probed_envs[env]

    # ------------------------------------------------------------------
    # Fixture loading helper
    # ------------------------------------------------------------------

    def _load_fixture(self, method: str, env: str) -> list[dict]:
        """Load a fixture file for the given method and environment.

        Returns the 'data' list from the JSON file, or empty list if
        the file does not exist (per C-004). Truncates to max_results
        and sets self.truncated if exceeded (FR-015).
        """
        if not self._fixture_dir:
            return []
        path = self._fixture_dir / f"{method}_{env}.json"
        if not path.exists():
            return []
        raw = json.loads(path.read_bytes())
        data = raw.get("data", [])
        if len(data) > self.max_results:
            log.warning(
                "Truncating %s_%s from %d to %d results (max_results=%d)",
                method, env, len(data), self.max_results, self.max_results,
            )
            self.truncated = True
            data = data[:self.max_results]
        return data

    # ------------------------------------------------------------------
    # Data methods
    # ------------------------------------------------------------------

    def service_dependencies(self, env: str) -> list[ObservedEdge]:
        """APM service map — highest-value single signal."""
        self._require_probe(env)
        entries = self._load_fixture("service_dependencies", env)
        edges: list[ObservedEdge] = []
        for entry in entries:
            edges.append(ObservedEdge(
                from_service=entry.get("from_service", ""),
                to_service=entry.get("to_service", ""),
                env=entry.get("env", env),
                capability="apm",
                sample_count=1,
            ))
        return edges

    def edges_from_traces(self, env: str) -> list[ObservedEdge]:
        """Extract caller->callee pairs from distributed trace spans.

        FR-016: derives edges from spans where span.kind == 'client'
        and either peer.service or out.host is present.
        """
        self._require_probe(env)
        entries = self._load_fixture("edges_from_traces", env)
        edges: list[ObservedEdge] = []
        for entry in entries:
            attrs = entry.get("attributes", {})
            span_kind = attrs.get("span_kind", "")
            if span_kind != "client":
                continue
            from_svc = attrs.get("service", "")
            to_svc = attrs.get("peer_service") or attrs.get("out_host", "")
            if not from_svc or not to_svc:
                continue
            edges.append(ObservedEdge(
                from_service=from_svc,
                to_service=to_svc,
                env=attrs.get("env", env),
                capability="traces",
                sample_count=1,
            ))
        return edges

    def edges_from_logs(self, env: str) -> list[ObservedEdge]:
        """Extract caller->callee pairs from structured JSON log lines.

        FR-016: parses logs with 'service' (caller) and at least one of
        'peer.service', 'http.url', or 'out.host' (callee).
        """
        self._require_probe(env)
        entries = self._load_fixture("edges_from_logs", env)
        edges: list[ObservedEdge] = []
        for entry in entries:
            outer_attrs = entry.get("attributes", {})
            from_svc = outer_attrs.get("service", "")
            inner_attrs = outer_attrs.get("attributes", {})

            # Try peer.service first, then http.url hostname, then out.host
            to_svc = inner_attrs.get("peer.service", "")
            if not to_svc:
                http_url = inner_attrs.get("http.url", "")
                if http_url:
                    to_svc = _extract_hostname_service(http_url)
            if not to_svc:
                to_svc = inner_attrs.get("out.host", "")

            if not from_svc or not to_svc:
                continue
            edges.append(ObservedEdge(
                from_service=from_svc,
                to_service=to_svc,
                env=env,
                capability="logs",
                sample_count=1,
            ))
        return edges

    def edges_from_rum(self, env: str) -> list[ObservedEdge]:
        """Extract browser-to-API edges from RUM resource events."""
        self._require_probe(env)
        entries = self._load_fixture("edges_from_rum", env)
        edges: list[ObservedEdge] = []
        for entry in entries:
            attrs = entry.get("attributes", {})
            from_svc = attrs.get("service", "")
            resource = attrs.get("resource", {})
            url = resource.get("url", "")
            to_svc = _extract_hostname_service(url) if url else ""
            if not from_svc or not to_svc:
                continue
            edges.append(ObservedEdge(
                from_service=from_svc,
                to_service=to_svc,
                env=env,
                capability="rum",
                sample_count=1,
            ))
        return edges


def _extract_hostname_service(url: str) -> str:
    """Extract the service-name-like hostname from a URL.

    e.g. 'https://payment-service.internal/api/v1' -> 'payment-service'
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Take the first segment of the hostname as the service name
        if "." in host:
            return host.split(".")[0]
        return host
    except Exception:
        return ""
