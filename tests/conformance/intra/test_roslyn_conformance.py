"""Conformance tests for RoslynIntraRepoProvider (M8).

All tests run in fixture-mode — no live subprocess, no .NET SDK required.
The fixture is replayed from tests/fixtures/conformance/intra/roslyn/analyze_result.json.

Covers:
  - US1 acceptance scenarios (layer-1 web.config resolution)
  - SC-M8-007 (layer-2 AST resolution via AppConfig.cs)
  - Unresolved paths (not-found, is-secret, dynamic-value)
  - partial_analysis=true contract
  - capabilities() contract
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tendril.connectors.intra.roslyn_subprocess import RoslynIntraRepoProvider
from tendril.connectors.intra.subprocess_bridge import SubprocessBridge, SubprocessError
from tendril.models.ir import IntraRepoFacts, ResolvedValue, Unresolved

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "conformance" / "intra" / "roslyn"
FULL_FIXTURE   = FIXTURE_DIR / "analyze_result.json"
PARTIAL_FIXTURE = FIXTURE_DIR / "analyze_result_partial.json"


def _load_fixture(path: Path) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def _make_provider_with_fixture(fixture_path: Path) -> RoslynIntraRepoProvider:
    """Return a RoslynIntraRepoProvider whose bridge.call() replays fixture data."""
    provider = RoslynIntraRepoProvider(binary_path="/fake/TendrilRoslyn")
    fixture_data = _load_fixture(fixture_path)

    mock_bridge = MagicMock(spec=SubprocessBridge)

    def fake_call(method: str, params: dict) -> dict:
        if method == "analyze":
            return fixture_data
        if method == "resolve_value":
            key = params.get("key", "")
            value_sets = fixture_data.get("value_sets", {})
            def_use    = fixture_data.get("def_use", {})
            if key not in value_sets:
                return {"resolved": False, "reason": "not-found", "detail": None}
            candidates = value_sets[key]
            # Apply same tiebreak as Server.cs
            winner = sorted(
                candidates,
                key=lambda v: (-v.get("layer", 1), v.get("source", "")),
            )[0]
            return {
                "resolved":      True,
                "value":         winner["value"],
                "source":        winner["source"],
                "def_use_chain": def_use.get(key, [winner["source"]]),
                "layer":         winner.get("layer", 1),
            }
        if method == "handshake":
            return {"server_version": "1.0", "compatible": True}
        return {}

    mock_bridge.call.side_effect = fake_call
    provider._bridge = mock_bridge
    return provider


# ---------------------------------------------------------------------------
# US1: layer-1 web.config resolution
# ---------------------------------------------------------------------------

class TestUS1Layer1Resolution:
    """US1 acceptance scenarios — layer-1 config-file parsing."""

    def setup_method(self) -> None:
        self.provider = _make_provider_with_fixture(FULL_FIXTURE)

    def test_resolve_webconfig_layer1(self) -> None:
        """SC-M8-001: resolve_value("LandingPageUrl") returns layer-1 ResolvedValue."""
        result = self.provider.resolve_value("/fake/repo", "LandingPageUrl")

        assert isinstance(result, ResolvedValue), f"Expected ResolvedValue, got {result}"
        assert result.resolved is True
        assert result.value == "https://d-ui.prod.example.com"
        assert result.layer == 1
        assert result.source == "web.config:LandingPageUrl"
        assert result.def_use_chain == ["web.config:LandingPageUrl"]

    def test_analyze_returns_layer1_entry(self) -> None:
        """analyze() returns IntraRepoFacts with layer=1 entry for LandingPageUrl."""
        facts = self.provider.analyze("/fake/repo")

        assert isinstance(facts, IntraRepoFacts)
        assert "LandingPageUrl" in facts.value_sets
        entries = facts.value_sets["LandingPageUrl"]
        assert any(e.get("layer") == 1 for e in entries)

    def test_not_found_returns_unresolved(self) -> None:
        """resolve_value on a missing key returns Unresolved(reason="not-found")."""
        result = self.provider.resolve_value("/fake/repo", "NonExistentKey")

        assert isinstance(result, Unresolved)
        assert result.resolved is False
        assert result.reason == "not-found"

    def test_partial_analysis_flag_propagated(self) -> None:
        """IntraRepoFacts.partial_analysis is propagated from fixture."""
        facts = self.provider.analyze("/fake/repo")
        assert facts.partial_analysis is False   # full fixture has partial=false
        assert facts.call_graph is None

    def test_appsettings_env_specific_has_condition(self) -> None:
        """Layer-1 env-specific entry carries condition=basename (CHK004)."""
        facts = self.provider.analyze("/fake/repo")
        assert "DefaultConnection" in facts.value_sets
        entries = facts.value_sets["DefaultConnection"]
        assert any(e.get("condition") == "appsettings.prod.json" for e in entries)


# ---------------------------------------------------------------------------
# SC-M8-007: layer-2 AST resolution
# ---------------------------------------------------------------------------

class TestLayer2ASTResolution:
    """SC-M8-007: layer-2 const string resolution via CSharpSyntaxTree."""

    def setup_method(self) -> None:
        self.provider = _make_provider_with_fixture(FULL_FIXTURE)

    def test_resolve_layer2_const(self) -> None:
        """resolve_value("ServiceUrl") returns layer-2 ResolvedValue from AppConfig.cs."""
        result = self.provider.resolve_value("/fake/repo", "ServiceUrl")

        assert isinstance(result, ResolvedValue)
        assert result.resolved is True
        assert result.value == "https://svc.prod.example.com"
        assert result.layer == 2
        assert result.source == "src/AppConfig.cs:42"

    def test_analyze_contains_layer2_entry(self) -> None:
        """IntraRepoFacts.value_sets contains a layer=2 entry for ServiceUrl."""
        facts = self.provider.analyze("/fake/repo")
        assert "ServiceUrl" in facts.value_sets
        entries = facts.value_sets["ServiceUrl"]
        assert any(e.get("layer") == 2 for e in entries)

    def test_def_use_chain_present_for_layer2(self) -> None:
        """def_use chain for a layer-2 key contains the source locator."""
        facts = self.provider.analyze("/fake/repo")
        assert "ServiceUrl" in facts.def_use
        assert "src/AppConfig.cs:42" in facts.def_use["ServiceUrl"]


# ---------------------------------------------------------------------------
# Unresolved paths
# ---------------------------------------------------------------------------

class TestUnresolvedPaths:
    """Verify all Unresolved.reason values are surfaced correctly."""

    def setup_method(self) -> None:
        self.provider = _make_provider_with_fixture(FULL_FIXTURE)

    def test_is_secret_redaction(self) -> None:
        """Secret keys return Unresolved(reason="is-secret") without calling bridge (FR-M8-012)."""
        for secret_key in ("DatabasePassword", "ApiSecret", "AccessToken", "ApiKey"):
            result = self.provider.resolve_value("/fake/repo", secret_key)
            assert isinstance(result, Unresolved), f"Expected Unresolved for {secret_key}"
            assert result.reason == "is-secret"

    def test_not_found(self) -> None:
        result = self.provider.resolve_value("/fake/repo", "KeyThatDoesNotExist")
        assert isinstance(result, Unresolved)
        assert result.reason == "not-found"

    def test_secret_keys_absent_from_analyze_facts(self) -> None:
        """analyze() must not return secret keys in value_sets or def_use (FR-M8-012)."""
        # Inject a secret key into fixture response for this test
        provider = _make_provider_with_fixture(FULL_FIXTURE)
        fixture_data = _load_fixture(FULL_FIXTURE)
        fixture_data_with_secret = {**fixture_data}
        fixture_data_with_secret["value_sets"] = {
            **fixture_data["value_sets"],
            "Password": [{"value": "s3cr3t", "source": "web.config:Password",
                          "condition": None, "layer": 1}],
        }
        fixture_data_with_secret["def_use"] = {
            **fixture_data["def_use"],
            "Password": ["web.config:Password"],
        }

        mock_bridge = MagicMock(spec=SubprocessBridge)
        mock_bridge.call.return_value = fixture_data_with_secret
        provider._bridge = mock_bridge

        facts = provider.analyze("/fake/repo")
        assert "Password" not in facts.value_sets
        assert "Password" not in facts.def_use

    def test_bridge_failure_returns_unresolved(self) -> None:
        """SubprocessError from bridge → Unresolved(reason="not-found"), never raises."""
        provider = RoslynIntraRepoProvider(binary_path="/fake/binary")
        mock_bridge = MagicMock(spec=SubprocessBridge)
        mock_bridge.call.side_effect = SubprocessError(
            method="resolve_value", message="process crashed", code=-32603,
        )
        provider._bridge = mock_bridge

        result = provider.resolve_value("/fake/repo", "SomeKey")
        assert isinstance(result, Unresolved)
        assert result.reason == "not-found"


# ---------------------------------------------------------------------------
# partial_analysis contract
# ---------------------------------------------------------------------------

class TestPartialAnalysis:
    """Verify partial_analysis=True contract (FR-M8-004 / CHK005)."""

    def test_partial_analysis_propagated(self) -> None:
        """When fixture has partial_analysis=true, IntraRepoFacts carries it."""
        # Use a partial fixture (only layer-1 data)
        if not PARTIAL_FIXTURE.exists():
            pytest.skip("partial fixture not yet created (T026)")

        provider = _make_provider_with_fixture(PARTIAL_FIXTURE)
        facts = provider.analyze("/fake/repo")
        assert facts.partial_analysis is True
        # No layer-2 entries should be present
        for key, entries in facts.value_sets.items():
            for entry in entries:
                assert entry.get("layer", 1) == 1, \
                    f"Key {key} has layer-2 entry in partial_analysis fixture"


# ---------------------------------------------------------------------------
# capabilities() contract
# ---------------------------------------------------------------------------

class TestCapabilities:
    """Verify capabilities() contract (FR-M8-010 / CHK026)."""

    def test_capabilities_all_false_when_binary_none(self) -> None:
        """No binary configured → all-false capabilities, no exception (FR-M8-010)."""
        provider = RoslynIntraRepoProvider(binary_path=None)
        caps = provider.capabilities()
        assert caps.get("layer1") is False
        assert caps.get("layer2") is False
        assert caps.get("def_use") is False

    def test_capabilities_logs_warning_when_unavailable(self, caplog: pytest.LogCaptureFixture) -> None:
        """Missing binary logs WARNING with event="roslyn-binary-unavailable" (SC-M8-004 / CHK026)."""
        import logging
        provider = RoslynIntraRepoProvider(binary_path=None)
        with caplog.at_level(logging.WARNING):
            provider.capabilities()
        assert any(
            "roslyn-binary-unavailable" in r.getMessage()
            or getattr(r, "event", None) == "roslyn-binary-unavailable"
            for r in caplog.records
        ), "Expected event=roslyn-binary-unavailable in log records"

    def test_capabilities_all_true_when_bridge_healthy(self) -> None:
        """Healthy bridge → layer1, layer2, def_use all True."""
        provider = RoslynIntraRepoProvider(binary_path="/fake/binary")
        mock_bridge = MagicMock(spec=SubprocessBridge)
        mock_bridge.call.return_value = {"server_version": "1.0", "compatible": True}
        provider._bridge = mock_bridge

        caps = provider.capabilities()
        assert caps.get("layer1") is True
        assert caps.get("layer2") is True
        assert caps.get("def_use") is True

    def test_matches_dotnet_repo(self) -> None:
        """matches() returns True for a tree with .cs files (FR-M8-013)."""
        from tendril.models.ir import FileEntry
        provider = RoslynIntraRepoProvider(binary_path=None)
        tree = [FileEntry("src/AppConfig.cs"), FileEntry("web.config")]
        assert provider.matches(tree) is True

    def test_matches_non_dotnet_repo(self) -> None:
        """matches() returns False for a tree with only .py files."""
        from tendril.models.ir import FileEntry
        provider = RoslynIntraRepoProvider(binary_path=None)
        tree = [FileEntry("main.py"), FileEntry("requirements.txt")]
        assert provider.matches(tree) is False
