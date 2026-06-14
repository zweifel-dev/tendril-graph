"""End-to-end integration test — the M4 acceptance criterion.

Proves one real DEPENDS_ON@prod edge from anchor repo webforms-solution
through to landing-page-ui, with confidence, evidence, deployed SHA,
and explicit unknowns.

Uses the fake plugin fixtures — no live API calls.
"""

from __future__ import annotations

import pytest

from tendril.core.attribution import AttributionEngine
from tendril.core.deployed_ref import DeployedRefResolver
from tendril.core.environment import EnvironmentCanonicalizer
from tendril.core.index import ReverseIndex
from tendril.core.resolver import Resolver
from tendril.core.traversal import TraversalEngine
from tendril.extractors.composition import CompositionExtractor
from tendril.extractors.dotnet import DotNetExtractor
from tendril.models.ir import (
    Confidence,
    Evidence,
    FileEntry,
    IdentityClass,
    Provenance,
    ProviderIdentity,
    RepoRef,
    VariableStore,
    VarEntry,
)
from tendril.store.kuzu_store import KuzuStore


# ---------------------------------------------------------------------------
# Fixture data — the synthetic 3-repo estate
# ---------------------------------------------------------------------------

ANCHOR = RepoRef(
    provider="bitbucket-dc", org="acme", name="webforms-solution",
    default_branch="main", url="https://bb.example.com/acme/webforms-solution",
)

LANDING_UI = RepoRef(
    provider="github", org="acme", name="landing-page-ui",
    default_branch="main", url="https://github.com/acme/landing-page-ui",
)

LANDING_API = RepoRef(
    provider="github", org="acme", name="landing-page-api",
    default_branch="main", url="https://github.com/acme/landing-page-api",
)

REPO_TREES: dict[str, list[FileEntry]] = {
    "webforms-solution": [
        FileEntry(path="home.aspx", type="file", size=500),
        FileEntry(path="web.config", type="file", size=400),
        FileEntry(path="appsettings.json", type="file", size=100),
        FileEntry(path="appsettings.prod.json", type="file", size=80),
        FileEntry(path="WebApp.csproj", type="file", size=300),
        FileEntry(path=".teamcity/settings.kts", type="file", size=200),
    ],
    "landing-page-ui": [
        FileEntry(path="src/index.html", type="file", size=300),
        FileEntry(path="package.json", type="file", size=200),
        FileEntry(path=".env.production", type="file", size=50),
        FileEntry(path=".github/workflows/deploy.yml", type="file", size=300),
    ],
    "landing-page-api": [
        FileEntry(path="Program.cs", type="file", size=400),
        FileEntry(path="appsettings.json", type="file", size=100),
        FileEntry(path="appsettings.prod.json", type="file", size=80),
        FileEntry(path="Api.csproj", type="file", size=250),
        FileEntry(path=".github/workflows/build.yml", type="file", size=250),
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
        "appsettings.prod.json": b'{"LandingPageUrl": "https://d-ui.prod.example.com"}',
        "WebApp.csproj": (
            b'<Project Sdk="Microsoft.NET.Sdk">\n'
            b"  <ItemGroup>\n"
            b'    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />\n'
            b"  </ItemGroup>\n"
            b"</Project>"
        ),
    },
    "landing-page-ui": {
        "src/index.html": b"<html><body><script src='/app.js'></script></body></html>",
        ".env.production": b"REACT_APP_API_URL=https://api.prod.example.com",
    },
    "landing-page-api": {
        "appsettings.json": b'{"BaseUrl": ""}',
        "appsettings.prod.json": b'{"BaseUrl": "https://api.prod.example.com"}',
    },
}

OCTOPUS_DEPLOYMENTS = {
    "webforms-solution": [
        {
            "EnvironmentName": "Production",
            "ProjectId": "Projects-1",
            "Created": "2024-01-15T10:30:00Z",
            "TaskId": "ServerTasks-3217",
            "ReleaseVersion": "1.2.3",
            "Release": {
                "BuildInformation": [{
                    "VcsCommitNumber": "abc123def456",
                    "Branch": "main",
                }],
            },
        },
    ],
}

VARIABLE_STORES = {
    "webforms-solution": [
        VariableStore(
            kind="octopus",
            entries=[
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


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_first_depends_on_edge(self) -> None:
        """M4 acceptance: produce one DEPENDS_ON@prod edge with full evidence."""

        # 1. Build the reverse index with provider identities
        index = ReverseIndex()
        index.add(
            deployable_id="landing-page-ui",
            repo_full_name="github:acme/landing-page-ui",
            identities=[
                ProviderIdentity(
                    identity_class=IdentityClass.NETWORK,
                    value="https://d-ui.prod.example.com",
                    env="prod",
                    evidence=[Evidence(
                        source_type="deploy-config",
                        locator="octopus:landing-page-ui:prod",
                    )],
                ),
            ],
        )
        index.add(
            deployable_id="landing-page-api",
            repo_full_name="github:acme/landing-page-api",
            identities=[
                ProviderIdentity(
                    identity_class=IdentityClass.NETWORK,
                    value="https://api.prod.example.com",
                    env="prod",
                    evidence=[Evidence(
                        source_type="deploy-config",
                        locator="octopus:landing-page-api:prod",
                    )],
                ),
            ],
        )

        # 2. Set up the pipeline components
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

        # 3. Run BFS from anchor
        result = engine.traverse(
            anchor=ANCHOR,
            envs=["prod"],
            repo_trees=REPO_TREES,
            deployments=OCTOPUS_DEPLOYMENTS,
            variable_stores=VARIABLE_STORES,
        )

        # 4. Verify the first real DEPENDS_ON@prod edge
        assert len(result.edges) > 0, "Expected at least one DEPENDS_ON edge"

        target_edge = next(
            (e for e in result.edges
             if e.to_id == "github:acme/landing-page-ui"
             and e.env == "prod"),
            None,
        )
        assert target_edge is not None, (
            f"Expected DEPENDS_ON edge to landing-page-ui@prod. "
            f"Got edges: {[(e.from_id, e.to_id, e.env) for e in result.edges]}"
        )

        # SC-003 exact assertions
        assert target_edge.from_id == "bitbucket-dc:acme/webforms-solution"
        assert target_edge.to_id == "github:acme/landing-page-ui"
        assert target_edge.env == "prod"
        assert target_edge.provenance == Provenance.INJECTED
        assert target_edge.confidence == Confidence.HIGH
        assert target_edge.deployed_ref == "abc123def456"
        assert len(target_edge.evidence) >= 3, (
            f"Expected ≥3 evidence items, got {len(target_edge.evidence)}: "
            f"{[e.locator for e in target_edge.evidence]}"
        )
        assert target_edge.unknowns == []
        assert target_edge.ambiguous is False

    def test_deployed_ref_resolved(self) -> None:
        """Verify the deployed SHA is resolved from Octopus deployments."""
        ref_resolver = DeployedRefResolver()
        from tendril.models.ir import CICDProfile, CICDProviderEntry

        profile = CICDProfile(
            repo=ANCHOR,
            environments=["prod"],
            providers=[CICDProviderEntry(
                provider_id="octopus",
                roles=["deploy"],
            )],
        )
        ref = ref_resolver.resolve(
            profile, "Production", OCTOPUS_DEPLOYMENTS["webforms-solution"],
        )
        assert ref is not None
        assert ref.sha == "abc123def456"
        assert ref.branch == "main"

    def test_secret_remains_unresolved(self) -> None:
        """Verify secret-typed values are never resolved (UNRESOLVED_SECRET)."""
        from tendril.models.ir import CICDProfile, CICDProviderEntry, TokenDecl

        resolver = Resolver()
        profile = CICDProfile(
            repo=ANCHOR,
            environments=["prod"],
            providers=[CICDProviderEntry(
                provider_id="octopus",
                roles=["deploy"],
            )],
        )
        token = TokenDecl(name="db-connection-string")
        result = resolver.acquire(
            token=token,
            repo=ANCHOR,
            env="prod",
            profile=profile,
            ref="abc123def456",
            variable_stores=VARIABLE_STORES["webforms-solution"],
        )
        assert not result.resolved
        assert result.is_secret

    def test_composition_extractor_finds_iframe(self) -> None:
        """Verify the composition extractor detects the iframe + token."""
        ext = CompositionExtractor()
        tree = REPO_TREES["webforms-solution"]
        assert ext.matches(tree)

        result = ext.extract(ANCHOR, "HEAD", tree, _mock_read_file)
        assert len(result.consumer_refs) > 0
        iframe_ref = next(
            (r for r in result.consumer_refs if "landing-page-url" in r.token_refs),
            None,
        )
        assert iframe_ref is not None
        assert "{landing-page-url}" in iframe_ref.raw_value

    def test_dotnet_extractor_finds_appsettings(self) -> None:
        """Verify the .NET extractor finds config values."""
        ext = DotNetExtractor()
        tree = REPO_TREES["webforms-solution"]
        assert ext.matches(tree)

        result = ext.extract(ANCHOR, "HEAD", tree, _mock_read_file)
        urls = [r for r in result.consumer_refs if "prod.example.com" in r.raw_value]
        assert len(urls) > 0

    def test_kuzu_stores_edge(self) -> None:
        """Verify the DEPENDS_ON edge round-trips through Kùzu."""
        store = KuzuStore(":memory:")

        store.upsert_node({
            "_table": "Deployable",
            "id": "webforms-solution",
            "repo_id": "bitbucket-dc:acme/webforms-solution",
            "kind": "web",
            "name": "webforms-solution",
        })
        store.upsert_node({
            "_table": "Deployable",
            "id": "landing-page-ui",
            "repo_id": "github:acme/landing-page-ui",
            "kind": "web",
            "name": "landing-page-ui",
        })
        store.upsert_edge({
            "_rel_type": "DEPENDS_ON",
            "_from_table": "Deployable",
            "_to_table": "Deployable",
            "from_id": "webforms-solution",
            "to_id": "landing-page-ui",
            "env": "prod",
            "provenance": "injected",
            "confidence": "high",
            "evidence": '[\"home.aspx:4\", \"octopus:var-preview\"]',
            "discovered_at": "2024-01-15T10:30:00Z",
            "deployed_ref": "abc123def456",
            "ambiguous": False,
            "stale": False,
        })

        rows = store.query(
            "MATCH (a:Deployable)-[r:DEPENDS_ON]->(b:Deployable) "
            "WHERE a.id = $from_id AND r.env = $env "
            "RETURN b.name, r.confidence, r.deployed_ref",
            {"from_id": "webforms-solution", "env": "prod"},
        )
        assert len(rows) == 1
        assert rows[0]["b.name"] == "landing-page-ui"
        assert rows[0]["r.confidence"] == "high"
        assert rows[0]["r.deployed_ref"] == "abc123def456"

    def test_rung4_parses_kv_from_logs(self) -> None:
        """Rung 4 extracts KEY=VALUE from deploy log lines (case-insensitive)."""
        from tendril.models.ir import CICDProfile, CICDProviderEntry, TokenDecl

        resolver = Resolver()
        profile = CICDProfile(
            repo=ANCHOR,
            environments=["prod"],
            providers=[CICDProviderEntry(provider_id="octopus", roles=["deploy"])],
        )
        token = TokenDecl(name="landing-page-url")
        result = resolver.acquire(
            token=token,
            repo=ANCHOR,
            env="prod",
            profile=profile,
            deploy_logs=[
                "landing-page-url=https://d-ui.prod.example.com",
                "other-var=some-value",
            ],
        )
        assert result.resolved, f"Expected resolved, got rung={result.rung}"
        assert result.value == "https://d-ui.prod.example.com"
        assert result.rung == "deploy_log"

    def test_environment_canonicalization(self) -> None:
        """Verify 'Production' maps to 'prod' for Octopus→internal join."""
        canon = EnvironmentCanonicalizer.from_file()
        name, matched = canon.canonicalize("Production")
        assert name == "prod"
        assert matched is True
