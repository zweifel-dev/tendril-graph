"""M0 acceptance tests: scaffolding, plugin discovery, Kùzu round-trip.

These verify that:
1. `python -m tendril --help` works
2. FakePlugin registers and appears in the registry
3. Kùzu upsert + query round-trips
4. Environment canonicalization works
5. All 7 ABCs are importable and have the expected methods
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tendril.plugins.base import (
    CONTRACT_VERSION,
    CICDProvider,
    ExtractorPlugin,
    GraphStore,
    IntraRepoProvider,
    LLMProvider,
    TelemetryProvider,
    VCSProvider,
)
from tendril.plugins.registry import PluginRegistry
from tendril.plugins.manifest import PluginManifest
from tendril.models.ir import RepoRef, FileEntry, Evidence, Confidence
from tendril.models.graph import Repo, Deployable, DependsOn, Produces
from tendril.core.environment import EnvironmentCanonicalizer
from tendril.store.kuzu_store import KuzuStore
from tests.fixtures.fake_plugin import (
    FakeVCSProvider,
    FakeCICDProvider,
    FakeExtractor,
)


class TestCLI:
    def test_help_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "tendril", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "tendril" in result.stdout.lower()

    def test_version_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "tendril", "--version"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "0.1.0" in result.stdout

    def test_providers_list_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "tendril", "providers", "list"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0


class TestPluginRegistry:
    def test_register_fake_vcs(self) -> None:
        registry = PluginRegistry()
        manifest = PluginManifest(
            id="fake-vcs",
            family="vcs",
            contract_version="1.0.0-alpha",
        )
        errors = registry.register(manifest, FakeVCSProvider())
        assert errors == []
        assert registry.get("fake-vcs") is not None

    def test_register_fake_cicd(self) -> None:
        registry = PluginRegistry()
        manifest = PluginManifest(
            id="fake-cicd",
            family="cicd",
            contract_version="1.0.0-alpha",
        )
        errors = registry.register(manifest, FakeCICDProvider())
        assert errors == []

    def test_register_fake_extractor(self) -> None:
        registry = PluginRegistry()
        manifest = PluginManifest(
            id="fake-extractor",
            family="extractor",
            contract_version="1.0.0-alpha",
        )
        errors = registry.register(manifest, FakeExtractor())
        assert errors == []

    def test_list_plugins_by_family(self) -> None:
        registry = PluginRegistry()
        for pid, fam, inst in [
            ("fake-vcs", "vcs", FakeVCSProvider()),
            ("fake-cicd", "cicd", FakeCICDProvider()),
            ("fake-ext", "extractor", FakeExtractor()),
        ]:
            registry.register(
                PluginManifest(id=pid, family=fam, contract_version="1.0.0-alpha"),
                inst,
            )
        assert len(registry.list_plugins(family="vcs")) == 1
        assert len(registry.list_plugins(family="cicd")) == 1
        assert len(registry.list_plugins()) == 3

    def test_invalid_family_rejected(self) -> None:
        registry = PluginRegistry()
        manifest = PluginManifest(
            id="bad", family="nosuch", contract_version="1.0.0-alpha",
        )
        errors = registry.register(manifest)
        assert any("unknown family" in e for e in errors)

    def test_incompatible_version_rejected(self) -> None:
        registry = PluginRegistry()
        manifest = PluginManifest(
            id="bad", family="vcs", contract_version="99.0.0",
        )
        errors = registry.register(manifest)
        assert any("not compatible" in e for e in errors)


class TestFakeVCSConformance:
    """Run conformance-style checks against the FakeVCSProvider."""

    def test_id(self) -> None:
        assert FakeVCSProvider().id() == "fake-vcs"

    def test_list_repos(self) -> None:
        repos = FakeVCSProvider().list_repos({})
        assert len(repos) == 3
        assert all(isinstance(r, RepoRef) for r in repos)

    def test_read_tree(self) -> None:
        repo = RepoRef(provider="fake", org="acme", name="webforms-solution")
        tree = FakeVCSProvider().read_tree(repo, "main")
        assert len(tree) > 0
        assert any(f.path == "home.aspx" for f in tree)

    def test_read_file_with_ref(self) -> None:
        repo = RepoRef(provider="fake", org="acme", name="webforms-solution")
        content = FakeVCSProvider().read_file(repo, "abc123", "home.aspx")
        assert b"iframe" in content


class TestFakeCICDConformance:
    def test_secret_values_masked(self) -> None:
        store = FakeCICDProvider().read_variable_store("build-webforms-solution", "prod")
        for entry in store.entries:
            if entry.is_secret:
                assert entry.value is None or entry.value == "[MASKED]"


class TestFakeExtractorConformance:
    def test_matches_aspx(self) -> None:
        tree = [FileEntry(path="home.aspx")]
        assert FakeExtractor().matches(tree) is True

    def test_no_match_without_aspx(self) -> None:
        tree = [FileEntry(path="index.html")]
        assert FakeExtractor().matches(tree) is False

    def test_extract_produces_consumer_refs(self) -> None:
        repo = RepoRef(provider="fake", org="acme", name="webforms-solution")
        tree = [FileEntry(path="home.aspx")]
        result = FakeExtractor().extract(repo, "main", tree, None)
        assert len(result.consumer_refs) > 0
        assert result.consumer_refs[0].raw_value == "{landing-page-url}/dashboard-ui"
        assert "landing-page-url" in result.consumer_refs[0].token_refs


class TestKuzuStore:
    def test_upsert_and_query(self) -> None:
        store = KuzuStore(":memory:")
        store.upsert_node({
            "_table": "Repo",
            "id": "test-1",
            "provider": "github",
            "org": "acme",
            "name": "my-repo",
            "url": "https://github.com/acme/my-repo",
            "default_branch": "main",
            "last_indexed_ref": "",
            "last_seen": "",
        })
        rows = store.query(
            "MATCH (r:Repo) WHERE r.id = $id RETURN r.name",
            {"id": "test-1"},
        )
        assert len(rows) == 1
        assert rows[0]["r.name"] == "my-repo"

    def test_upsert_two_nodes_and_edge(self) -> None:
        store = KuzuStore(":memory:")
        store.upsert_node({
            "_table": "Repo",
            "id": "repo-a",
            "provider": "github",
            "org": "acme",
            "name": "repo-a",
            "url": "",
            "default_branch": "main",
            "last_indexed_ref": "",
            "last_seen": "",
        })
        store.upsert_node({
            "_table": "Deployable",
            "id": "deploy-a",
            "repo_id": "repo-a",
            "kind": "web",
            "name": "repo-a-web",
        })
        store.upsert_edge({
            "_rel_type": "PRODUCES",
            "_from_table": "Repo",
            "_to_table": "Deployable",
            "from_id": "repo-a",
            "to_id": "deploy-a",
            "env": "",
            "provenance": "declared",
            "confidence": "high",
            "evidence": "[]",
            "discovered_at": "",
        })
        rows = store.query(
            "MATCH (r:Repo)-[:PRODUCES]->(d:Deployable) WHERE r.id = $id RETURN d.name",
            {"id": "repo-a"},
        )
        assert len(rows) == 1
        assert rows[0]["d.name"] == "repo-a-web"


class TestEnvironmentCanonicalizer:
    def test_exact_match(self) -> None:
        canon = EnvironmentCanonicalizer({"prod": ["production", "prd", "live"]})
        name, matched = canon.canonicalize("production")
        assert name == "prod"
        assert matched is True

    def test_case_insensitive(self) -> None:
        canon = EnvironmentCanonicalizer({"prod": ["production"]})
        name, matched = canon.canonicalize("Production")
        assert name == "prod"
        assert matched is True

    def test_canonical_name_itself(self) -> None:
        canon = EnvironmentCanonicalizer({"prod": ["production"]})
        name, matched = canon.canonicalize("prod")
        assert name == "prod"
        assert matched is True

    def test_unmatched_returns_raw(self) -> None:
        canon = EnvironmentCanonicalizer({"prod": ["production"]})
        name, matched = canon.canonicalize("custom-env-42")
        assert name == "custom-env-42"
        assert matched is False

    def test_from_file(self) -> None:
        canon = EnvironmentCanonicalizer.from_file()
        name, matched = canon.canonicalize("production")
        assert name == "prod"
        assert matched is True


class TestABCsImportable:
    """Verify all 7 ABCs are importable and have the expected shape."""

    def test_vcs_provider_methods(self) -> None:
        methods = {"id", "capabilities", "list_repos", "read_tree", "read_file", "default_branch"}
        assert methods.issubset(set(dir(VCSProvider)))

    def test_cicd_provider_methods(self) -> None:
        methods = {"id", "capabilities", "discover_for_repo", "list_pipelines", "read_variable_store"}
        assert methods.issubset(set(dir(CICDProvider)))

    def test_extractor_plugin_methods(self) -> None:
        methods = {"id", "matches", "extract"}
        assert methods.issubset(set(dir(ExtractorPlugin)))

    def test_telemetry_provider_methods(self) -> None:
        methods = {"id", "probe", "service_dependencies"}
        assert methods.issubset(set(dir(TelemetryProvider)))

    def test_graph_store_methods(self) -> None:
        methods = {"id", "upsert_node", "upsert_edge", "query", "neighbors", "path"}
        assert methods.issubset(set(dir(GraphStore)))

    def test_llm_provider_methods(self) -> None:
        methods = {"id", "capabilities", "complete"}
        assert methods.issubset(set(dir(LLMProvider)))

    def test_intra_repo_provider_methods(self) -> None:
        methods = {"id", "capabilities", "analyze", "resolve_value"}
        assert methods.issubset(set(dir(IntraRepoProvider)))
