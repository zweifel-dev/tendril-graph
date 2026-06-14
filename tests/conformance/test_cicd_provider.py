"""Conformance test suite for CICDProvider implementations (SPEC.md §4.3)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from tendril.plugins.base import CICDProvider
from tendril.models.ir import RepoRef, FileEntry


class ConformanceCICDProvider(ABC):
    """Abstract conformance suite for CI/CD providers."""

    @abstractmethod
    def provider(self) -> CICDProvider: ...

    @abstractmethod
    def sample_repo(self) -> RepoRef: ...

    @abstractmethod
    def sample_repo_tree(self) -> list[FileEntry]: ...

    @abstractmethod
    def sample_pipeline_or_project(self) -> str: ...

    def test_id_returns_string(self) -> None:
        pid = self.provider().id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_capabilities_returns_dict(self) -> None:
        caps = self.provider().capabilities()
        assert isinstance(caps, dict)

    def test_discover_for_repo_returns_bindings(self) -> None:
        bindings = self.provider().discover_for_repo(
            self.sample_repo(), self.sample_repo_tree(),
        )
        assert isinstance(bindings, list)

    def test_list_pipelines_returns_list(self) -> None:
        pipelines = self.provider().list_pipelines({})
        assert isinstance(pipelines, list)

    def test_read_variable_store_returns_store(self) -> None:
        store = self.provider().read_variable_store(
            self.sample_pipeline_or_project(), None,
        )
        assert store is not None
        assert hasattr(store, "entries")

    def test_secret_values_are_masked(self) -> None:
        """NFR-1: secret-typed values MUST be masked."""
        store = self.provider().read_variable_store(
            self.sample_pipeline_or_project(), None,
        )
        for entry in store.entries:
            if entry.is_secret:
                assert entry.value is None or entry.value == "[MASKED]", (
                    f"Secret entry '{entry.key}' has value exposed"
                )

    def test_read_provider_identities_returns_list(self) -> None:
        identities = self.provider().read_provider_identities(
            self.sample_pipeline_or_project(), None,
        )
        assert isinstance(identities, list)
