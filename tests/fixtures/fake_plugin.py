"""A trivial fake plugin for testing plugin discovery and conformance.

Implements VCSProvider with canned responses so the conformance skeleton
can run without any live API calls.
"""

from __future__ import annotations

from typing import Any

from tendril.models.ir import (
    Capabilities,
    ConsumerRef,
    ConsumerRefKind,
    Evidence,
    FileEntry,
    ProviderIdentity,
    RepoRef,
    TokenDecl,
)
from tendril.plugins.base import (
    CICDProvider,
    ExtractionResult,
    ExtractorPlugin,
    VCSProvider,
)
from tendril.models.ir import (
    PipelineBinding,
    VariableStore,
    VarEntry,
)


# ---------------------------------------------------------------------------
# Fake VCS
# ---------------------------------------------------------------------------

FAKE_REPOS = [
    RepoRef(
        provider="fake",
        org="acme",
        name="webforms-solution",
        default_branch="main",
        url="https://fake.example.com/acme/webforms-solution",
    ),
    RepoRef(
        provider="fake",
        org="acme",
        name="landing-page-ui",
        default_branch="main",
        url="https://fake.example.com/acme/landing-page-ui",
    ),
    RepoRef(
        provider="fake",
        org="acme",
        name="landing-page-api",
        default_branch="main",
        url="https://fake.example.com/acme/landing-page-api",
    ),
]

FAKE_TREES: dict[str, list[FileEntry]] = {
    "webforms-solution": [
        FileEntry(path="home.aspx", type="file", size=1200),
        FileEntry(path="web.config", type="file", size=800),
        FileEntry(path="appsettings.json", type="file", size=200),
        FileEntry(path="appsettings.prod.json", type="file", size=150),
        FileEntry(path="WebApp.csproj", type="file", size=400),
        FileEntry(path=".teamcity/settings.kts", type="file", size=300),
    ],
    "landing-page-ui": [
        FileEntry(path="src/index.html", type="file", size=500),
        FileEntry(path="package.json", type="file", size=300),
        FileEntry(path=".env.production", type="file", size=50),
        FileEntry(path=".github/workflows/deploy.yml", type="file", size=400),
    ],
    "landing-page-api": [
        FileEntry(path="Program.cs", type="file", size=600),
        FileEntry(path="appsettings.json", type="file", size=200),
        FileEntry(path="appsettings.prod.json", type="file", size=100),
        FileEntry(path="Api.csproj", type="file", size=350),
        FileEntry(path=".github/workflows/build.yml", type="file", size=350),
    ],
}

FAKE_FILES: dict[str, dict[str, bytes]] = {
    "webforms-solution": {
        "home.aspx": b'<%@ Page Language="VB" %>\n<html>\n<body>\n<iframe src="{landing-page-url}/dashboard-ui"></iframe>\n</body>\n</html>',
        "web.config": b'<?xml version="1.0"?>\n<configuration>\n  <appSettings>\n    <add key="landing-page-url" value="" />\n  </appSettings>\n</configuration>',
        "appsettings.json": b'{"LandingPageUrl": ""}',
        "appsettings.prod.json": b'{"LandingPageUrl": "https://d-ui.prod.example.com"}',
    },
    "landing-page-ui": {
        "src/index.html": b'<html><body><script src="/app.js"></script></body></html>',
        ".env.production": b'REACT_APP_API_URL=https://api.prod.example.com',
    },
    "landing-page-api": {
        "appsettings.json": b'{"BaseUrl": ""}',
        "appsettings.prod.json": b'{"BaseUrl": "https://api.prod.example.com"}',
    },
}


class FakeVCSProvider(VCSProvider):
    def id(self) -> str:
        return "fake-vcs"

    def capabilities(self) -> Capabilities:
        return {"graphql": False, "webhooks": False}

    def list_repos(self, scope: dict[str, Any]) -> list[RepoRef]:
        return list(FAKE_REPOS)

    def read_tree(self, repo: RepoRef, ref: str) -> list[FileEntry]:
        return FAKE_TREES.get(repo.name, [])

    def read_file(self, repo: RepoRef, ref: str, path: str) -> bytes:
        files = FAKE_FILES.get(repo.name, {})
        if path in files:
            return files[path]
        raise FileNotFoundError(f"{repo.name}/{path} not in fixtures")

    def default_branch(self, repo: RepoRef) -> str:
        return "main"


# ---------------------------------------------------------------------------
# Fake CI/CD
# ---------------------------------------------------------------------------

class FakeCICDProvider(CICDProvider):
    def id(self) -> str:
        return "fake-cicd"

    def capabilities(self) -> Capabilities:
        return {
            "variable_preview": True,
            "deploy_logs": True,
            "env_scoping_model": True,
            "intrinsic": False,
            "extrinsic": True,
        }

    def discover_for_repo(
        self, repo: RepoRef, repo_tree: list[FileEntry],
    ) -> list[PipelineBinding]:
        return [
            PipelineBinding(
                provider="fake-cicd",
                pipeline_id=f"build-{repo.name}",
                repo=repo,
                roles=["build", "deploy"],
                env=None,
            ),
        ]

    def list_pipelines(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"id": "build-webforms-solution", "name": "WebForms Build"}]

    def read_variable_store(
        self, pipeline_or_project: str, env: str | None,
    ) -> VariableStore:
        entries = [
            VarEntry(
                key="landing-page-url",
                value="https://d-ui.prod.example.com",
                is_secret=False,
                readable=True,
                scope={"env": "prod"},
            ),
            VarEntry(
                key="db-connection-string",
                value=None,
                is_secret=True,
                readable=False,
                scope={"env": "prod"},
            ),
        ]
        if env:
            entries = [e for e in entries if e.scope.get("env") == env or not e.scope.get("env")]
        return VariableStore(kind="fake-store", entries=entries, scoping_model="env")

    def read_provider_identities(
        self, pipeline_or_project: str, env: str | None,
    ) -> list[ProviderIdentity]:
        return []


# ---------------------------------------------------------------------------
# Fake Extractor
# ---------------------------------------------------------------------------

class FakeExtractor(ExtractorPlugin):
    def id(self) -> str:
        return "fake-extractor"

    def matches(self, repo_tree: list[FileEntry]) -> bool:
        return any(f.path.endswith(".aspx") for f in repo_tree)

    def extract(
        self,
        repo: RepoRef,
        ref: str,
        tree: list[FileEntry],
        read_file: Any,
    ) -> ExtractionResult:
        return ExtractionResult(
            consumer_refs=[
                ConsumerRef(
                    kind=ConsumerRefKind.IFRAME,
                    raw_value="{landing-page-url}/dashboard-ui",
                    token_refs=["landing-page-url"],
                    evidence=[Evidence(source_type="file", locator="home.aspx:4")],
                ),
            ],
            provider_identities=[],
            token_decls=[
                TokenDecl(
                    name="landing-page-url",
                    declared_in=Evidence(source_type="file", locator="web.config:4"),
                    injected=True,
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Entry point factories (for importlib.metadata discovery)
# ---------------------------------------------------------------------------

def create_fake_vcs() -> FakeVCSProvider:
    return FakeVCSProvider()

def create_fake_cicd() -> FakeCICDProvider:
    return FakeCICDProvider()

def create_fake_extractor() -> FakeExtractor:
    return FakeExtractor()
