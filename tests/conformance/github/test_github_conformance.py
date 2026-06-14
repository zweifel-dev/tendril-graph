"""GitHub VCS provider conformance tests (SPEC.md §4.2, SC-002).

Runs the full ConformanceVCSProvider suite against GitHubProvider using
pre-recorded fixtures — no network calls.
"""
from __future__ import annotations

from pathlib import Path

from tendril.connectors.vcs.github import GitHubProvider
from tendril.models.ir import RepoRef
from tests.conformance.test_vcs_provider import ConformanceVCSProvider

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "conformance" / "vcs"


class TestGitHubConformance(ConformanceVCSProvider):
    """GitHub conformance suite — fixture mode, zero network calls."""

    def provider(self) -> GitHubProvider:
        return GitHubProvider(token="fixture", fixture_dir=_FIXTURE_DIR)

    def sample_repo(self) -> RepoRef:
        return RepoRef(
            provider="github",
            org="acme",
            name="landing-page-ui",
            default_branch="main",
            url="https://github.com/acme/landing-page-ui.git",
        )

    def sample_ref(self) -> str:
        return "main"

    def sample_file_path(self) -> str:
        return "src/index.html"
