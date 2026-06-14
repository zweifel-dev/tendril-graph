"""Conformance test suite for IntraRepoProvider implementations (SPEC.md §4.8)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tendril.plugins.base import IntraRepoProvider


class ConformanceIntraRepoProvider(ABC):
    """Abstract conformance suite for intra-repo analysis providers."""

    @abstractmethod
    def provider(self) -> IntraRepoProvider: ...

    def test_id_returns_string(self) -> None:
        pid = self.provider().id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_capabilities_returns_dict(self) -> None:
        caps = self.provider().capabilities()
        assert isinstance(caps, dict)
