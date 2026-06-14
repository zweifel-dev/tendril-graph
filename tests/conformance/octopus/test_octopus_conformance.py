"""Octopus Deploy CI/CD provider conformance tests (SPEC.md §4.3, SC-002).

Runs the full ConformanceCICDProvider suite against OctopusProvider using
pre-recorded fixtures — no network calls. Includes the Octopus-specific
resolve_deployed_ref test (US3 acceptance scenario 3).
"""
from __future__ import annotations

from pathlib import Path

from tendril.connectors.cicd.octopus import OctopusProvider
from tendril.models.ir import FileEntry, RepoRef
from tests.conformance.test_cicd_provider import ConformanceCICDProvider

_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent / "fixtures" / "cicd" / "octopus"
)


class TestOctopusConformance(ConformanceCICDProvider):
    """Octopus conformance suite — fixture mode, zero network calls."""

    def provider(self) -> OctopusProvider:
        return OctopusProvider(
            base_url="https://octopus.example.com",
            api_key="fixture",
            space="Spaces-1",
            fixture_dir=_FIXTURE_DIR,
        )

    def sample_repo(self) -> RepoRef:
        return RepoRef(
            provider="bitbucket-dc",
            org="acme",
            name="webforms-solution",
            default_branch="main",
            url="https://bitbucket.example.com/scm/acme/webforms-solution.git",
        )

    def sample_repo_tree(self) -> list[FileEntry]:
        return [
            FileEntry(path="WebApp.csproj", type="file", size=300),
            FileEntry(path=".teamcity/settings.kts", type="file", size=200),
        ]

    def sample_pipeline_or_project(self) -> str:
        return "Projects-1"

    # -----------------------------------------------------------------------
    # Octopus-specific: resolve_deployed_ref (US3 acceptance scenario 3)
    # -----------------------------------------------------------------------

    def test_resolve_deployed_ref_returns_sha(self) -> None:
        """Octopus resolve_deployed_ref must return non-null with valid SHA (≥7 chars)."""
        ref = self.provider().resolve_deployed_ref("Projects-1", "prod")
        assert ref is not None, (
            "resolve_deployed_ref returned None — check deployments_Projects-1_prod.json "
            "and release_Releases-50.json fixtures"
        )
        assert len(ref.sha) >= 7, f"SHA '{ref.sha}' is shorter than 7 characters"
        assert ref.sha == "abc123def456", (
            f"Expected SHA 'abc123def456', got '{ref.sha}' — "
            "check release_Releases-50.json VcsCommitNumber field"
        )
