"""TeamCity CI/CD provider conformance tests (SPEC.md §4.3, SC-002).

Runs the full ConformanceCICDProvider suite against TeamCityProvider using
pre-recorded fixtures — no network calls.
"""
from __future__ import annotations

from pathlib import Path

from tendril.connectors.cicd.teamcity import TeamCityProvider
from tendril.models.ir import FileEntry, RepoRef
from tests.conformance.test_cicd_provider import ConformanceCICDProvider

_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent / "fixtures" / "conformance" / "cicd" / "teamcity"
)


class TestTeamCityConformance(ConformanceCICDProvider):
    """TeamCity conformance suite — fixture mode, zero network calls."""

    def provider(self) -> TeamCityProvider:
        return TeamCityProvider(
            base_url="https://teamcity.example.com",
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

    def sample_repo_tree(self) -> list[FileEntry]:
        return [
            FileEntry(path=".teamcity/settings.kts", type="file", size=200),
            FileEntry(path="WebApp.csproj", type="file", size=300),
        ]

    def sample_pipeline_or_project(self) -> str:
        return "AcmeWebforms_Build"
