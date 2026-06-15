"""Bitbucket Pipelines CI/CD provider conformance suite (M7-5).

Subclasses ConformanceCICDProvider and provides Bitbucket Pipelines fixtures.
Verifies that ``discover_for_repo()`` returns the correct PipelineBindings
for a workflow with a ``deployment:`` field.
"""

from __future__ import annotations

from pathlib import Path

from tendril.connectors.cicd.bitbucket_pipelines import BitbucketPipelinesProvider
from tendril.models.ir import FileEntry, RepoRef
from tests.conformance.test_cicd_provider import ConformanceCICDProvider

_FIXTURE_DIR = (
    Path(__file__).parent.parent.parent
    / "fixtures" / "conformance" / "cicd" / "bitbucket_pipelines"
)


class TestBitbucketPipelinesConformance(ConformanceCICDProvider):
    """Bitbucket Pipelines conformance suite — fixture mode, zero network calls."""

    def provider(self) -> BitbucketPipelinesProvider:
        return BitbucketPipelinesProvider(fixture_dir=_FIXTURE_DIR)

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
            FileEntry(path="bitbucket-pipelines.yml", type="file", size=300),
        ]

    def sample_pipeline_or_project(self) -> str:
        return "webforms-solution"

    # ------------------------------------------------------------------
    # Bitbucket Pipelines–specific assertions (M7-5)
    # ------------------------------------------------------------------

    def test_discover_deployment_step_returns_deploy_binding(self) -> None:
        """Step with ``deployment: staging`` → PipelineBinding(roles=["deploy"], env="staging")."""
        provider = BitbucketPipelinesProvider(fixture_dir=_FIXTURE_DIR)
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

    def test_parse_pipeline_from_bytes_with_deployment(self) -> None:
        """YAML with ``deployment: staging`` → PipelineBinding(roles=["deploy"], env="staging")."""
        content = b"""
pipelines:
  branches:
    main:
      - step:
          name: Deploy
          deployment: staging
          script:
            - echo deploy
"""
        provider = BitbucketPipelinesProvider()
        repo = self.sample_repo()
        bindings = provider.parse_pipeline_bytes(content, "bitbucket-pipelines.yml", repo)
        assert any(b.env == "staging" and "deploy" in b.roles for b in bindings), (
            f"Expected staging deploy binding, got: {[(b.roles, b.env) for b in bindings]}"
        )

    def test_parse_pipeline_default_section(self) -> None:
        """``pipelines.default`` steps with deployment are scanned."""
        content = b"""
pipelines:
  default:
    - step:
        name: Deploy
        deployment: production
        script:
          - echo deploy
"""
        provider = BitbucketPipelinesProvider()
        repo = self.sample_repo()
        bindings = provider.parse_pipeline_bytes(content, "bitbucket-pipelines.yml", repo)
        assert any(b.env == "production" and "deploy" in b.roles for b in bindings), (
            f"Expected production deploy binding, got: {[(b.roles, b.env) for b in bindings]}"
        )
