"""Bitbucket Data Center VCS provider conformance tests (SPEC.md §4.2, SC-002).

Runs the full ConformanceVCSProvider suite against BitbucketDCProvider using
pre-recorded fixtures — no network calls.
"""
from __future__ import annotations

from pathlib import Path

from tendril.connectors.vcs.bitbucket_dc import BitbucketDCProvider
from tendril.models.ir import RepoRef
from tests.conformance.test_vcs_provider import ConformanceVCSProvider

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "conformance" / "vcs"


class TestBitbucketDCConformance(ConformanceVCSProvider):
    """Bitbucket DC conformance suite — fixture mode, zero network calls."""

    def provider(self) -> BitbucketDCProvider:
        return BitbucketDCProvider(
            base_url="https://bitbucket.example.com",
            token="fixture",
            fixture_dir=_FIXTURE_DIR,
        )

    def sample_repo(self) -> RepoRef:
        return RepoRef(
            provider="bitbucket-dc",
            org="ACME",
            name="webforms-solution",
            default_branch="main",
            url="https://bitbucket.example.com/scm/acme/webforms-solution.git",
        )

    def sample_ref(self) -> str:
        return "main"

    def sample_file_path(self) -> str:
        return "web.config"

    def test_read_tree_includes_nested_paths(self) -> None:
        """FR-008: read_tree returns files at all directory depths (3+ levels)."""
        p = self.provider()
        repo = self.sample_repo()
        tree = p.read_tree(repo, self.sample_ref())
        paths = [f.path for f in tree]
        # Must include files at depth 3 (src/Config/Transforms/*)
        assert "src/Config/Transforms/web.staging.config" in paths, (
            f"Nested path not found in tree: {paths}"
        )
        # Must include files at depth 2 (src/Services/*)
        assert "src/Services/ApiClient.cs" in paths
        # Must still include root-level files
        assert "web.config" in paths
