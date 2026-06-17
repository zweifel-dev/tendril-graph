"""Integration tests for live-mode graph build (T028).

Verifies that `tendril graph build` (without --fixture-dir) discovers providers
from env-var credentials, calls real provider methods, and builds a graph.

Uses monkeypatch to inject credentials + mock provider HTTP responses so that
zero real API calls are made.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tendril.cli.main import main
from tendril.models.ir import (
    Capabilities,
    DeployedRef,
    Evidence,
    FileEntry,
    IdentityClass,
    PipelineBinding,
    ProviderIdentity,
    RepoRef,
    VarEntry,
    VariableStore,
)


# ---------------------------------------------------------------------------
# Fake providers — satisfy the interface, return canned data
# ---------------------------------------------------------------------------

class FakeVCSProvider:
    """Minimal VCS provider returning fixture-like data."""

    def __init__(self) -> None:
        self._repos = [
            RepoRef(provider="github", org="acme", name="web-app",
                    default_branch="main", url="https://github.com/acme/web-app"),
            RepoRef(provider="github", org="acme", name="api-service",
                    default_branch="main", url="https://github.com/acme/api-service"),
        ]

    def id(self) -> str:
        return "github"

    def list_repos(self, scope: dict) -> list[RepoRef]:
        return self._repos

    def read_tree(self, repo: RepoRef, ref: str) -> list[FileEntry]:
        if repo.name == "web-app":
            return [
                FileEntry(path="web.config", type="file", size=200),
                FileEntry(path="src/app.cs", type="file", size=500),
            ]
        return [FileEntry(path="README.md", type="file", size=100)]

    def read_file(self, repo: RepoRef, ref: str, path: str) -> bytes:
        if repo.name == "web-app" and path == "web.config":
            return b'<configuration><appSettings><add key="ApiUrl" value="https://api.acme.com/v1" /></appSettings></configuration>'
        raise FileNotFoundError(f"{repo.name}/{path}")


class FakeCICDProvider:
    """Minimal CI/CD provider returning canned deployment + variable data."""

    def id(self) -> str:
        return "octopus"

    def capabilities(self) -> Capabilities:
        return {"variable_preview": True, "deploy_logs": True}

    def discover_for_repo(self, repo: RepoRef, repo_tree: list[FileEntry]) -> list[PipelineBinding]:
        if repo.name == "web-app":
            return [PipelineBinding(provider="octopus", pipeline_id="proj-1", repo=repo, roles=["deploy"])]
        return []

    def resolve_deployed_ref(self, project_id: str, env: str) -> DeployedRef | None:
        if project_id == "proj-1":
            return DeployedRef(sha="aaa111bbb222", branch="main")
        return None

    def read_variable_store(self, pipeline_or_project: str, env: str | None) -> VariableStore:
        return VariableStore(
            kind="octopus-variable-set",
            entries=[
                VarEntry(key="ApiUrl", value="https://api.acme.com/v1", is_secret=False, readable=True, scope={}),
            ],
            scoping_model="environment",
        )

    def read_provider_identities(self, pipeline_or_project: str, env: str | None) -> list[ProviderIdentity]:
        return [
            ProviderIdentity(
                identity_class=IdentityClass.NETWORK,
                value="https://api.acme.com/v1",
                env=env,
                evidence=[Evidence(source_type="octopus-machine", locator="machine-1")],
            ),
        ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLiveMode:
    """Live-mode graph build with fake providers — no real HTTP calls."""

    def test_live_mode_exits_1_without_credentials(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """No VCS credentials → exit 1 with helpful error message."""
        # Clear all credential env vars
        for var in ("GH_TOKEN", "GH_APP_ID", "GH_INSTALL_ID", "GH_PRIVATE_KEY_PATH",
                     "BB_BASE_URL", "BB_TOKEN"):
            monkeypatch.delenv(var, raising=False)

        exit_code = main([
            "graph", "build",
            "--anchor", "github:acme/web-app",
            "--env", "prod",
            "--db", str(tmp_path / "g.db"),
        ])
        assert exit_code == 1

    def test_live_mode_with_github_token(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """GH_TOKEN set → GitHub provider discovered, graph build runs."""
        monkeypatch.setenv("GH_TOKEN", "ghp_test_token")
        # Clear other providers
        for var in ("BB_BASE_URL", "BB_TOKEN", "TC_BASE_URL", "TC_TOKEN",
                     "OCTO_URL", "OCTO_API_KEY", "OCTO_SPACE",
                     "DD_API_KEY", "DD_APP_KEY", "DD_SITE"):
            monkeypatch.delenv(var, raising=False)

        fake_vcs = FakeVCSProvider()
        fake_cicd = FakeCICDProvider()

        # Patch the provider constructors to return fakes
        with patch("tendril.cli.main.GitHubProvider", return_value=fake_vcs, create=True), \
             patch("tendril.connectors.vcs.github.GitHubProvider", new=lambda **kw: fake_vcs):

            # We need to patch at the import point inside _graph_build_live.
            # The function does `from tendril.connectors.vcs.github import GitHubProvider`
            # so we patch the module-level class.
            import tendril.connectors.vcs.github as gh_mod
            original_cls = gh_mod.GitHubProvider

            try:
                gh_mod.GitHubProvider = lambda *a, **kw: fake_vcs

                db_path = str(tmp_path / "live.db")
                exit_code = main([
                    "graph", "build",
                    "--anchor", "github:acme/web-app",
                    "--env", "prod",
                    "--db", db_path,
                ])
                assert exit_code == 0
            finally:
                gh_mod.GitHubProvider = original_cls

    def test_live_mode_degradation_no_cicd(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Missing CI/CD credentials → degradation notices, but still exit 0."""
        monkeypatch.setenv("GH_TOKEN", "ghp_test_token")
        for var in ("BB_BASE_URL", "BB_TOKEN", "TC_BASE_URL", "TC_TOKEN",
                     "OCTO_URL", "OCTO_API_KEY", "OCTO_SPACE",
                     "DD_API_KEY", "DD_APP_KEY", "DD_SITE"):
            monkeypatch.delenv(var, raising=False)

        fake_vcs = FakeVCSProvider()

        import tendril.connectors.vcs.github as gh_mod
        original_cls = gh_mod.GitHubProvider

        try:
            gh_mod.GitHubProvider = lambda *a, **kw: fake_vcs

            db_path = str(tmp_path / "degrade.db")
            exit_code = main([
                "graph", "build",
                "--anchor", "github:acme/web-app",
                "--env", "prod",
                "--db", db_path,
            ])
            assert exit_code == 0

            captured = capsys.readouterr()
            assert "degradation" in captured.out.lower() or "degradation" in captured.err.lower()
        finally:
            gh_mod.GitHubProvider = original_cls
