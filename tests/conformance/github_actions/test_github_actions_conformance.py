"""GitHub Actions CI/CD provider conformance suite (M7-4).

Subclasses ConformanceCICDProvider and provides GitHub Actions fixtures.
Verifies that ``discover_for_repo()`` returns the correct PipelineBindings
for both environment-scoped and build-only workflows.
"""

from __future__ import annotations

from pathlib import Path

from tendril.connectors.cicd.github_actions import GitHubActionsProvider
from tendril.models.ir import FileEntry, RepoRef
from tests.conformance.test_cicd_provider import ConformanceCICDProvider

_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures" / "conformance" / "cicd" / "github_actions"
)


class TestGitHubActionsConformance(ConformanceCICDProvider):
    """GitHub Actions conformance suite — fixture mode, zero network calls."""

    def provider(self) -> GitHubActionsProvider:
        return GitHubActionsProvider(fixture_dir=_FIXTURE_DIR)

    def sample_repo(self) -> RepoRef:
        return RepoRef(
            provider="github",
            org="acme",
            name="landing-page-ui",
            default_branch="main",
            url="https://github.com/acme/landing-page-ui",
        )

    def sample_repo_tree(self) -> list[FileEntry]:
        return [
            FileEntry(path=".github/workflows/deploy_with_environment.yml", type="file", size=300),
            FileEntry(path=".github/workflows/deploy_no_environment.yml", type="file", size=200),
        ]

    def sample_pipeline_or_project(self) -> str:
        return "landing-page-ui"

    # ------------------------------------------------------------------
    # GitHub Actions–specific assertions (M7-4)
    # ------------------------------------------------------------------

    def test_discover_deploy_workflow_returns_deploy_binding(self) -> None:
        """Workflow with ``environment: staging`` → PipelineBinding(roles=["deploy"], env="staging")."""
        provider = GitHubActionsProvider(fixture_dir=_FIXTURE_DIR)
        repo = self.sample_repo()
        bindings = provider.discover_for_repo(repo, [])

        deploy_bindings = [b for b in bindings if "deploy" in b.roles]
        assert len(deploy_bindings) >= 1, (
            f"Expected at least one deploy binding, got: {[(b.roles, b.env) for b in bindings]}"
        )
        staging_bindings = [b for b in deploy_bindings if b.env == "staging"]
        assert len(staging_bindings) >= 1, (
            f"Expected deploy binding with env='staging', got: {[(b.roles, b.env) for b in deploy_bindings]}"
        )

    def test_discover_build_only_workflow_returns_build_binding(self) -> None:
        """Workflow with no ``environment:`` blocks → PipelineBinding(roles=["build"]), no exception."""
        provider = GitHubActionsProvider(fixture_dir=_FIXTURE_DIR)
        repo = self.sample_repo()
        bindings = provider.discover_for_repo(repo, [])

        build_bindings = [b for b in bindings if b.roles == ["build"]]
        assert len(build_bindings) >= 1, (
            f"Expected at least one build-only binding, got: {[(b.roles, b.env) for b in bindings]}"
        )

    def test_discover_does_not_raise_on_no_environment(self) -> None:
        """discover_for_repo must not raise even when no environment: blocks are found."""
        provider = GitHubActionsProvider(fixture_dir=_FIXTURE_DIR)
        repo = self.sample_repo()
        # Must not raise.
        result = provider.discover_for_repo(repo, [])
        assert isinstance(result, list)

    def test_parse_workflow_from_bytes_with_environment(self) -> None:
        """Parsing a workflow YAML with environment: field returns deploy binding."""
        content = b"""
jobs:
  deploy:
    environment: production
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
"""
        provider = GitHubActionsProvider()
        repo = self.sample_repo()
        bindings = provider.parse_workflow_bytes(content, "test.yml", repo)
        assert any(b.env == "production" and "deploy" in b.roles for b in bindings), (
            f"Expected production deploy binding, got: {[(b.roles, b.env) for b in bindings]}"
        )

    def test_parse_workflow_object_form_environment(self) -> None:
        """``environment: {name: staging, url: ...}`` form is handled."""
        content = b"""
jobs:
  deploy:
    environment:
      name: staging
      url: https://staging.example.com
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
"""
        provider = GitHubActionsProvider()
        repo = self.sample_repo()
        bindings = provider.parse_workflow_bytes(content, "test.yml", repo)
        assert any(b.env == "staging" and "deploy" in b.roles for b in bindings), (
            f"Expected staging deploy binding, got: {[(b.roles, b.env) for b in bindings]}"
        )
