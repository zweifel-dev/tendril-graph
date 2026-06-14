"""Conformance test suite for LLMProvider implementations (SPEC.md §4.7)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tendril.plugins.base import LLMProvider, LLMRequest


class ConformanceLLMProvider(ABC):
    """Abstract conformance suite for LLM providers."""

    @abstractmethod
    def provider(self) -> LLMProvider: ...

    def test_id_returns_string(self) -> None:
        pid = self.provider().id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_capabilities_returns_dict(self) -> None:
        caps = self.provider().capabilities()
        assert isinstance(caps, dict)
