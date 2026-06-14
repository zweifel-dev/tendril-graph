"""Conformance test suite for VCSProvider implementations (SPEC.md §4.2).

Plugin authors subclass ConformanceVCSProvider, set `provider` to their
implementation, and run `pytest`. The suite is the executable definition
of the contract.
"""

from __future__ import annotations

import pytest
from abc import ABC, abstractmethod

from tendril.plugins.base import VCSProvider
from tendril.models.ir import RepoRef


class ConformanceVCSProvider(ABC):
    """Abstract conformance suite. Subclass and set `provider`."""

    @abstractmethod
    def provider(self) -> VCSProvider: ...

    @abstractmethod
    def sample_repo(self) -> RepoRef: ...

    @abstractmethod
    def sample_ref(self) -> str: ...

    @abstractmethod
    def sample_file_path(self) -> str: ...

    def test_id_returns_string(self) -> None:
        pid = self.provider().id()
        assert isinstance(pid, str)
        assert len(pid) > 0

    def test_capabilities_returns_dict(self) -> None:
        caps = self.provider().capabilities()
        assert isinstance(caps, dict)

    def test_list_repos_returns_list(self) -> None:
        repos = self.provider().list_repos({})
        assert isinstance(repos, list)
        for r in repos:
            assert isinstance(r, RepoRef)

    def test_read_tree_returns_file_entries(self) -> None:
        tree = self.provider().read_tree(self.sample_repo(), self.sample_ref())
        assert isinstance(tree, list)
        assert len(tree) > 0

    def test_read_file_returns_bytes(self) -> None:
        content = self.provider().read_file(
            self.sample_repo(), self.sample_ref(), self.sample_file_path(),
        )
        assert isinstance(content, bytes)

    def test_default_branch_returns_string(self) -> None:
        branch = self.provider().default_branch(self.sample_repo())
        assert isinstance(branch, str)
        assert len(branch) > 0

    def test_read_file_with_explicit_ref(self) -> None:
        """FR-24: read_file MUST accept an explicit ref (deployed SHA)."""
        content = self.provider().read_file(
            self.sample_repo(), self.sample_ref(), self.sample_file_path(),
        )
        assert isinstance(content, bytes)
