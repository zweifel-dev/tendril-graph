"""Unit tests for DatadogTelemetryProvider (M10).

All tests use fixture files under tests/fixtures/conformance/telemetry/datadog/.
No live API calls are made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tendril.connectors.telemetry.datadog_provider import DatadogTelemetryProvider
from tendril.models.ir import ObservedEdge
from tendril.plugins.base import ProbeRequiredError

FIXTURE_DIR = Path("tests/fixtures/conformance/telemetry/datadog")


class TestDatadogProviderUnit:
    """Unit tests for DatadogTelemetryProvider."""

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def test_id_returns_datadog(self) -> None:
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        assert p.id() == "datadog"

    # ------------------------------------------------------------------
    # Probe — capabilities_prod.json (all active)
    # ------------------------------------------------------------------

    def test_probe_prod_all_active(self) -> None:
        """capabilities_prod.json has apm, logs, traces, rum all True."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        caps = p.probe("prod")
        assert caps["apm"] is True
        assert caps["logs"] is True
        assert caps["traces"] is True
        assert caps["rum"] is True

    # ------------------------------------------------------------------
    # Probe — US2: capabilities_logs_only.json
    # ------------------------------------------------------------------

    def test_probe_logs_only(self) -> None:
        """capabilities_logs_only.json — only logs active (US2 partial degradation)."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        caps = p.probe("logs_only")
        assert caps["logs"] is True
        assert caps["apm"] is False
        assert caps["traces"] is False
        assert caps["rum"] is False

    # ------------------------------------------------------------------
    # Probe — US2: capabilities_none.json
    # ------------------------------------------------------------------

    def test_probe_none_active(self) -> None:
        """capabilities_none.json — all capabilities inactive (US2 full degradation)."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        caps = p.probe("none")
        assert caps["apm"] is False
        assert caps["logs"] is False
        assert caps["traces"] is False
        assert caps["rum"] is False

    # ------------------------------------------------------------------
    # service_dependencies — service_dependencies_prod.json
    # ------------------------------------------------------------------

    def test_service_dependencies_returns_edges(self) -> None:
        """service_dependencies_prod.json has 3 APM edges."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        p.probe("prod")
        edges = p.service_dependencies("prod")
        assert len(edges) == 3
        assert all(isinstance(e, ObservedEdge) for e in edges)
        # Verify capability tag
        assert all(e.capability == "apm" for e in edges)
        # Verify specific pairs
        pairs = {(e.from_service, e.to_service) for e in edges}
        assert ("web-app", "api-gateway") in pairs
        assert ("web-app", "auth-service") in pairs
        assert ("web-app", "analytics-svc") in pairs

    # ------------------------------------------------------------------
    # ProbeRequiredError guard
    # ------------------------------------------------------------------

    def test_probe_required_error(self) -> None:
        """Calling service_dependencies without probe raises ProbeRequiredError."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        with pytest.raises(ProbeRequiredError):
            p.service_dependencies("prod")

    # ------------------------------------------------------------------
    # edges_from_traces — capability="traces", filters span_kind=client (US3)
    # ------------------------------------------------------------------

    def test_edges_from_traces(self) -> None:
        """edges_from_traces_prod.json — filters span_kind=client, extracts caller/callee."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        p.probe("prod")
        edges = p.edges_from_traces("prod")
        assert len(edges) == 2
        assert all(e.capability == "traces" for e in edges)
        pairs = {(e.from_service, e.to_service) for e in edges}
        assert ("web-app", "cache-service") in pairs
        assert ("api-gateway", "auth-service") in pairs

    # ------------------------------------------------------------------
    # edges_from_logs — capability="logs", parses peer.service and http.url (US3)
    # ------------------------------------------------------------------

    def test_edges_from_logs(self) -> None:
        """edges_from_logs_prod.json — parses peer.service and http.url hostname."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        p.probe("prod")
        edges = p.edges_from_logs("prod")
        assert len(edges) == 2
        assert all(e.capability == "logs" for e in edges)
        pairs = {(e.from_service, e.to_service) for e in edges}
        # First entry uses peer.service directly
        assert ("api-gateway", "database-svc") in pairs
        # Second entry extracts hostname from http.url
        assert ("web-app", "notification-svc") in pairs

    # ------------------------------------------------------------------
    # edges_from_rum — capability="rum", extracts browser-to-API pairs (US3)
    # ------------------------------------------------------------------

    def test_edges_from_rum(self) -> None:
        """edges_from_rum_prod.json — extracts browser-to-API pairs from RUM resources."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        p.probe("prod")
        edges = p.edges_from_rum("prod")
        assert len(edges) == 2
        assert all(e.capability == "rum" for e in edges)
        pairs = {(e.from_service, e.to_service) for e in edges}
        assert ("frontend-app", "api-gateway") in pairs
        assert ("frontend-app", "analytics-svc") in pairs

    # ------------------------------------------------------------------
    # Missing fixture → empty list (C-004)
    # ------------------------------------------------------------------

    def test_missing_fixture_returns_empty(self) -> None:
        """Capability active in probe but no fixture file for data method → empty list."""
        p = DatadogTelemetryProvider(fixture_dir=FIXTURE_DIR)
        # Probe prod (all capabilities active)
        p.probe("prod")
        # edges_from_traces for a non-existent env fixture → no fixture file
        # We probe "prod" but manually override probed envs to test missing fixture path.
        # Actually, let's use staging: probe staging, then call edges_from_traces("staging")
        # which has no edges_from_traces_staging.json fixture.
        p.probe("staging")
        edges = p.edges_from_traces("staging")
        assert isinstance(edges, list)
        assert len(edges) == 0

    # ------------------------------------------------------------------
    # T025 complement: DatadogConfig.is_complete / missing_fields
    # ------------------------------------------------------------------

    def test_config_is_complete(self) -> None:
        """T025: DatadogConfig.is_complete() and missing_fields() correctness."""
        from tendril.config import DatadogConfig

        # Fully populated → complete
        full = DatadogConfig(api_key="dd-key", app_key="dd-app", site="datadoghq.com")
        assert full.is_complete() is True
        assert full.missing_fields() == []

        # Missing api_key
        no_api = DatadogConfig(api_key=None, app_key="dd-app", site="datadoghq.com")
        assert no_api.is_complete() is False
        assert "api_key" in no_api.missing_fields()

        # Missing app_key
        no_app = DatadogConfig(api_key="dd-key", app_key=None, site="datadoghq.com")
        assert no_app.is_complete() is False
        assert "app_key" in no_app.missing_fields()

        # Missing site
        no_site = DatadogConfig(api_key="dd-key", app_key="dd-app", site=None)
        assert no_site.is_complete() is False
        assert "site" in no_site.missing_fields()

        # All missing
        empty = DatadogConfig()
        assert empty.is_complete() is False
        missing = empty.missing_fields()
        assert "api_key" in missing
        assert "app_key" in missing
        assert "site" in missing

        # Empty strings treated as falsy
        blank = DatadogConfig(api_key="", app_key="dd-app", site="datadoghq.com")
        assert blank.is_complete() is False
        assert "api_key" in blank.missing_fields()
