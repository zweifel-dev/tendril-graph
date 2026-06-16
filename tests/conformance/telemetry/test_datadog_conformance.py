"""Conformance test suite for DatadogTelemetryProvider (M10).

Extends ConformanceTelemetryProvider with Datadog-specific assertions
covering probe capabilities, service dependency edges, and the
ProbeRequiredError guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tendril.connectors.telemetry.datadog_provider import DatadogTelemetryProvider
from tendril.plugins.base import ProbeRequiredError, TelemetryProvider
from tests.conformance.test_telemetry_provider import ConformanceTelemetryProvider

FIXTURE_DIR = Path("tests/fixtures/conformance/telemetry/datadog")


class TestDatadogConformance(ConformanceTelemetryProvider):
    """Datadog conformance — inherits base telemetry provider tests."""

    def provider(self) -> TelemetryProvider:
        return DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)

    def sample_env(self) -> str:
        return "prod"

    def test_methods_degrade_gracefully(self) -> None:
        """NFR-7 override: Datadog requires probe() before data methods.

        The base conformance test calls data methods without probe first.
        Datadog enforces ProbeRequiredError, so we probe first and then
        confirm all methods return lists.
        """
        p = self.provider()
        env = self.sample_env()
        p.probe(env)
        assert isinstance(p.service_dependencies(env), list)
        assert isinstance(p.edges_from_traces(env), list)
        assert isinstance(p.edges_from_logs(env), list)
        assert isinstance(p.edges_from_rum(env), list)
        assert isinstance(p.service_catalog(), list)
        assert isinstance(p.deploy_events(env), list)

    # ------------------------------------------------------------------
    # Datadog-specific conformance tests
    # ------------------------------------------------------------------

    def test_probe_returns_four_capabilities(self) -> None:
        """Verify probe returns all four Datadog capability keys: apm, logs, traces, rum."""
        caps = self.provider().probe(self.sample_env())
        assert "apm" in caps
        assert "logs" in caps
        assert "traces" in caps
        assert "rum" in caps
        assert len(caps) == 4

    def test_service_dependencies_returns_observed_edges(self) -> None:
        """Probe first, then verify service_dependencies returns ObservedEdge list."""
        p = self.provider()
        p.probe(self.sample_env())
        edges = p.service_dependencies(self.sample_env())
        assert isinstance(edges, list)
        assert len(edges) > 0
        for edge in edges:
            assert edge.from_service
            assert edge.to_service
            assert edge.env

    def test_probe_required_before_data_methods(self) -> None:
        """Calling a data method without a prior probe raises ProbeRequiredError."""
        p = self.provider()
        # Do NOT call probe — go straight to data method
        with pytest.raises(ProbeRequiredError):
            p.service_dependencies(self.sample_env())
