"""M6 acceptance test: golden fixture — full pipeline, zero credentials (M6-4).

Wires all providers from fixture data using the same pattern as
test_end_to_end.py.  Runs TraversalEngine.traverse() from the anchor repo,
then asserts the golden DEPENDS_ON@prod edge matches every field in
tests/fixtures/golden/expected/depends_on_prod.json.

Acceptance gate: pytest tests/integration/test_golden_fixture.py -v
passes on a fresh checkout with no credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

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

_GOLDEN_EXPECTED = (
    Path(__file__).parent.parent / "fixtures" / "golden" / "expected" / "depends_on_prod.json"
)

# ---------------------------------------------------------------------------
# Fixture estate (mirrors test_end_to_end.py — no duplication of JSON files)
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
# Tests
# ---------------------------------------------------------------------------

class TestGoldenFixture:
    def test_golden_depends_on_edge_matches_expected(self) -> None:
        """Full pipeline from fixture → DEPENDS_ON@prod matching expected JSON."""
        assert _GOLDEN_EXPECTED.exists(), f"Expected file missing: {_GOLDEN_EXPECTED}"
        expected = json.loads(_GOLDEN_EXPECTED.read_text())

        # Build the reverse index.
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
            envs=["prod"],
            repo_trees=REPO_TREES,
            deployments=OCTOPUS_DEPLOYMENTS,
            variable_stores=VARIABLE_STORES,
        )

        # Find the golden edge.
        target_edge = next(
            (e for e in result.edges
             if e.from_id == expected["from_id"]
             and e.to_id == expected["to_id"]
             and e.env == expected["env"]),
            None,
        )
        assert target_edge is not None, (
            f"No edge matching expected from={expected['from_id']} "
            f"to={expected['to_id']} env={expected['env']}. "
            f"Got edges: {[(e.from_id, e.to_id, e.env) for e in result.edges]}"
        )

        assert target_edge.provenance.value == expected["provenance"], (
            f"Provenance mismatch: {target_edge.provenance} != {expected['provenance']}"
        )
        assert target_edge.confidence.value == expected["confidence"], (
            f"Confidence mismatch: {target_edge.confidence} != {expected['confidence']}"
        )
        assert target_edge.deployed_ref == expected["deployed_ref"], (
            f"Deployed ref mismatch: {target_edge.deployed_ref} != {expected['deployed_ref']}"
        )

        evidence_locators = [str(e) for e in target_edge.evidence]
        for substring in expected["evidence_contains"]:
            assert any(substring in loc for loc in evidence_locators), (
                f"Evidence '{substring}' not found in {evidence_locators}"
            )

        assert target_edge.unknowns == expected["unknowns"]
