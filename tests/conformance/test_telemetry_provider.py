"""Conformance test suite for TelemetryProvider implementations (SPEC.md §4.5)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tendril.plugins.base import TelemetryProvider


class ConformanceTelemetryProvider(ABC):
    """Abstract conformance suite for telemetry providers."""

    @abstractmethod
    def provider(self) -> TelemetryProvider: ...

    @abstractmethod
    def sample_env(self) -> str: ...

    def test_id_returns_string(self) -> None:
        pid = self.provider().id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_probe_returns_capabilities(self) -> None:
        caps = self.provider().probe(self.sample_env())
        assert isinstance(caps, dict)

    def test_methods_degrade_gracefully(self) -> None:
        """NFR-7: missing capabilities degrade, never crash."""
        p = self.provider()
        env = self.sample_env()
        assert isinstance(p.service_dependencies(env), list)
        assert isinstance(p.edges_from_traces(env), list)
        assert isinstance(p.edges_from_logs(env), list)
        assert isinstance(p.edges_from_rum(env), list)
        assert isinstance(p.service_catalog(), list)
        assert isinstance(p.deploy_events(env), list)
