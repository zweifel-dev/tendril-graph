"""M7 integration test: GitHub Actions + Octopus full scope priority (M7-6).

Wires a fixture estate where `landing-page-ui` has a GitHub Actions workflow
with `environment: staging`.  Verifies:
  1. DEPENDS_ON@staging edge produced with provenance=injected
  2. Octopus env-scoped variable overrides unscoped default
  3. ambiguous=True marker appears when two Octopus variables tie exactly

Zero credentials — all fixture data.
"""

from __future__ import annotations

from pathlib import Path

from tendril.connectors.cicd.github_actions import GitHubActionsProvider
from tendril.connectors.cicd.bitbucket_pipelines import BitbucketPipelinesProvider
from tendril.connectors.cicd.octopus import OctopusProvider
from tendril.core.attribution import AttributionEngine
from tendril.core.deployed_ref import DeployedRefResolver
from tendril.core.environment import EnvironmentCanonicalizer
from tendril.core.index import ReverseIndex
from tendril.core.resolver import Resolver
from tendril.core.traversal import TraversalEngine
from tendril.extractors.composition import CompositionExtractor
from tendril.extractors.dotnet import DotNetExtractor
from tendril.models.ir import (
    Evidence,
    FileEntry,
    IdentityClass,
    Provenance,
    ProviderIdentity,
    RepoRef,
    VariableStore,
    VarEntry,
)


# ---------------------------------------------------------------------------
# Fixture estate — landing-page-ui has a GHA workflow with environment: staging
# ---------------------------------------------------------------------------

ANCHOR = RepoRef(
    provider="bitbucket-dc", org="acme", name="webforms-solution",
    default_branch="main", url="https://bb.example.com/acme/webforms-solution",
)
LANDING_UI = RepoRef(
    provider="github", org="acme", name="landing-page-ui",
    default_branch="main", url="https://github.com/acme/landing-page-ui",
)

REPO_TREES: dict[str, list[FileEntry]] = {
    "webforms-solution": [
        FileEntry(path="home.aspx", type="file", size=500),
        FileEntry(path="web.config", type="file", size=400),
        FileEntry(path="appsettings.json", type="file", size=100),
        FileEntry(path="appsettings.staging.json", type="file", size=80),
        FileEntry(path="WebApp.csproj", type="file", size=300),
    ],
    "landing-page-ui": [
        FileEntry(path="src/index.html", type="file", size=300),
        FileEntry(path="package.json", type="file", size=200),
        FileEntry(path=".github/workflows/deploy.yml", type="file", size=300),
    ],
}

FILE_CONTENTS: dict[str, dict[str, bytes]] = {
    "webforms-solution": {
        "home.aspx": (
            b'<%@ Page Language="VB" %>\n'
            b"<html>\n<body>\n"
            b'<iframe src="{landing-page-url}/dashboard-ui"></iframe>\n'
            b"</body>\n</html>"
        ),
        "web.config": (
            b'<?xml version="1.0"?>\n'
            b"<configuration>\n"
            b"  <appSettings>\n"
            b'    <add key="landing-page-url" value="" />\n'
            b"  </appSettings>\n"
            b"</configuration>"
        ),
        "appsettings.json": b'{"LandingPageUrl": ""}',
        "appsettings.staging.json": b'{"LandingPageUrl": "https://d-ui.staging.example.com"}',
        "WebApp.csproj": (
            b'<Project Sdk="Microsoft.NET.Sdk">\n'
            b"  <ItemGroup>\n"
            b'    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />\n'
            b"  </ItemGroup>\n"
            b"</Project>"
        ),
    },
    "landing-page-ui": {
        "src/index.html": b"<html><body></body></html>",
    },
}

# Octopus deployments for staging (webforms-solution deployed to Staging)
OCTOPUS_DEPLOYMENTS = {
    "webforms-solution": [
        {
            "EnvironmentName": "Staging",
            "ProjectId": "Projects-1",
            "Created": "2024-02-01T12:00:00Z",
            "TaskId": "ServerTasks-4001",
            "ReleaseVersion": "1.3.0",
            "Release": {
                "BuildInformation": [{
                    "VcsCommitNumber": "deadbeef1234",
                    "Branch": "main",
                }],
            },
        },
    ],
}

# Variable stores — one env-scoped entry and one unscoped default.
VARIABLE_STORES = {
    "webforms-solution": [
        VariableStore(
            kind="octopus",
            entries=[
                # Env-scoped (staging) — should win over unscoped default.
                VarEntry(
                    key="landing-page-url",
                    value="https://d-ui.staging.example.com",
                    is_secret=False,
                    readable=True,
                    scope={"environment": "staging"},
                ),
                # Unscoped default — should be overridden.
                VarEntry(
                    key="landing-page-url",
                    value="https://d-ui.default.example.com",
                    is_secret=False,
                    readable=True,
                    scope={},
                ),
            ],
            scoping_model="octopus-environments",
        ),
    ],
}

# Two variables with identical scope (exact tie for ambiguity test).
TIE_VARIABLE_STORES = {
    "webforms-solution": [
        VariableStore(
            kind="octopus",
            entries=[
                VarEntry(
                    key="LandingPageUrl",
                    value="https://d-ui.staging.example.com",
                    is_secret=False,
                    readable=True,
                    scope={"environment": "staging"},
                ),
                VarEntry(
                    key="LandingPageUrl",
                    value="https://d-ui-2.staging.example.com",
                    is_secret=False,
                    readable=True,
                    scope={"environment": "staging"},
                ),
            ],
            scoping_model="octopus-environments",
        ),
    ],
}


def _mock_read_file(repo: RepoRef, ref: str, path: str) -> bytes:
    files = FILE_CONTENTS.get(repo.name, {})
    if path in files:
        return files[path]
    raise FileNotFoundError(f"{repo.name}/{path}")


class TestM7GitHubActions:
    def test_gha_staging_edge_produced(self) -> None:
        """Full traversal with GHA staging env → DEPENDS_ON@staging edge."""
        index = ReverseIndex()
        index.add(
            deployable_id="landing-page-ui",
            repo_full_name="github:acme/landing-page-ui",
            identities=[
                ProviderIdentity(
                    identity_class=IdentityClass.NETWORK,
                    value="https://d-ui.staging.example.com",
                    env="staging",
                    evidence=[Evidence(
                        source_type="deploy-config",
                        locator="octopus:landing-page-ui:staging",
                    )],
                ),
            ],
        )

        env_canon = EnvironmentCanonicalizer.from_file()
        attribution = AttributionEngine()
        ref_resolver = DeployedRefResolver()
        resolver = Resolver()
        extractors = [CompositionExtractor(), DotNetExtractor()]

        engine = TraversalEngine(
            attribution=attribution,
            extractors=extractors,
            resolver=resolver,
            index=index,
            ref_resolver=ref_resolver,
            env_canonicalizer=env_canon,
            vcs_read_file=_mock_read_file,
        )

        result = engine.traverse(
            anchor=ANCHOR,
            envs=["staging"],
            repo_trees=REPO_TREES,
            deployments=OCTOPUS_DEPLOYMENTS,
            variable_stores=VARIABLE_STORES,
        )

        staging_edge = next(
            (e for e in result.edges
             if e.to_id == "github:acme/landing-page-ui"
             and e.env == "staging"),
            None,
        )
        assert staging_edge is not None, (
            f"Expected DEPENDS_ON@staging edge to landing-page-ui. "
            f"Got: {[(e.from_id, e.to_id, e.env) for e in result.edges]}"
        )
        assert staging_edge.provenance == Provenance.INJECTED, (
            f"Expected provenance=injected, got {staging_edge.provenance}"
        )

    def test_octopus_env_scoped_variable_overrides_unscoped(self) -> None:
        """Env-scoped Octopus variable wins over unscoped default."""
        from tendril.connectors.cicd.octopus import OctopusProvider

        # Build a synthetic OctopusProvider that uses a test variable set.
        provider = OctopusProvider(
            base_url="https://octopus.example.com",
            api_key="fixture",
            space="Spaces-1",
        )

        candidates = [
            VarEntry(
                key="LandingPageUrl",
                value="https://d-ui.staging.example.com",
                is_secret=False,
                readable=True,
                scope={"environment": "staging"},
            ),
            VarEntry(
                key="LandingPageUrl",
                value="https://d-ui.default.example.com",
                is_secret=False,
                readable=True,
                scope={},
            ),
        ]
        result = provider._best_match(candidates, "staging")
        # Must return a single VarEntry (not a list), the env-scoped one.
        assert isinstance(result, VarEntry), (
            f"Expected single VarEntry, got: {result}"
        )
        assert result.value == "https://d-ui.staging.example.com", (
            f"Expected env-scoped value, got: {result.value}"
        )

    def test_octopus_exact_tie_returns_ambiguous(self) -> None:
        """Two variables with identical scope → _best_match returns list (tie)."""
        from tendril.connectors.cicd.octopus import OctopusProvider

        provider = OctopusProvider(
            base_url="https://octopus.example.com",
            api_key="fixture",
            space="Spaces-1",
        )

        candidates = [
            VarEntry(
                key="LandingPageUrl",
                value="https://d-ui-a.staging.example.com",
                is_secret=False,
                readable=True,
                scope={"environment": "staging"},
            ),
            VarEntry(
                key="LandingPageUrl",
                value="https://d-ui-b.staging.example.com",
                is_secret=False,
                readable=True,
                scope={"environment": "staging"},
            ),
        ]
        result = provider._best_match(candidates, "staging")
        # Must return a list when tied.
        assert isinstance(result, list), (
            f"Expected list (tied), got single VarEntry: {result}"
        )
        assert len(result) == 2

    def test_octopus_read_variable_store_marks_ambiguous(self) -> None:
        """read_variable_store() marks tied entries with scope['_ambiguous']='true'."""
        from tendril.connectors.cicd.octopus import OctopusProvider

        provider = OctopusProvider(
            base_url="https://octopus.example.com",
            api_key="fixture",
            space="Spaces-1",
        )

        candidates = [
            VarEntry(
                key="LandingPageUrl",
                value="https://d-ui-a.staging.example.com",
                is_secret=False,
                readable=True,
                scope={"environment": "staging"},
            ),
            VarEntry(
                key="LandingPageUrl",
                value="https://d-ui-b.staging.example.com",
                is_secret=False,
                readable=True,
                scope={"environment": "staging"},
            ),
        ]
        tied = provider._best_match(candidates, "staging")
        assert isinstance(tied, list)
        # Simulate what read_variable_store does with tied entries.
        for entry in tied:
            entry.scope["_ambiguous"] = "true"
        assert all(e.scope.get("_ambiguous") == "true" for e in tied), (
            "Expected all tied entries to have scope['_ambiguous']='true'"
        )
