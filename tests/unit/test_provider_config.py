"""Unit tests for VCS/CI/CD provider config classes (T026).

Verifies: env var priority over TOML, empty/whitespace treated as unset,
is_complete() and missing_fields() behavior for each provider.
"""

from __future__ import annotations

import os

import pytest

from tendril.config import (
    BitbucketDCConfig,
    GitHubConfig,
    OctopusConfig,
    TeamCityConfig,
    load_bitbucket_dc_config,
    load_github_config,
    load_octopus_config,
    load_teamcity_config,
)


class TestGitHubConfig:
    def test_token_path_complete(self) -> None:
        cfg = GitHubConfig(token="ghp_abc123")
        assert cfg.is_complete() is True
        assert cfg.missing_fields() == []

    def test_app_path_complete(self) -> None:
        cfg = GitHubConfig(app_id="123", install_id="456", private_key_path="/path/to/key.pem")
        assert cfg.is_complete() is True
        assert cfg.missing_fields() == []

    def test_empty_is_incomplete(self) -> None:
        cfg = GitHubConfig()
        assert cfg.is_complete() is False

    def test_whitespace_treated_as_unset(self) -> None:
        cfg = GitHubConfig(token="  ")
        assert cfg.is_complete() is False

    def test_partial_app_incomplete(self) -> None:
        cfg = GitHubConfig(app_id="123")
        assert cfg.is_complete() is False
        missing = cfg.missing_fields()
        assert "install_id" in missing
        assert "private_key_path" in missing

    def test_env_var_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "env-token")
        cfg = load_github_config()
        assert cfg.token == "env-token"

    def test_empty_env_var_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GH_TOKEN", "  ")
        cfg = load_github_config()
        assert cfg.token == ""  # whitespace treated as unset, falls to default


class TestBitbucketDCConfig:
    def test_complete(self) -> None:
        cfg = BitbucketDCConfig(base_url="https://bb.example.com", token="tok")
        assert cfg.is_complete() is True
        assert cfg.missing_fields() == []

    def test_empty_is_incomplete(self) -> None:
        cfg = BitbucketDCConfig()
        assert cfg.is_complete() is False
        assert "base_url" in cfg.missing_fields()
        assert "token" in cfg.missing_fields()

    def test_env_var_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BB_BASE_URL", "https://env-bb.example.com")
        monkeypatch.setenv("BB_TOKEN", "env-tok")
        cfg = load_bitbucket_dc_config()
        assert cfg.base_url == "https://env-bb.example.com"
        assert cfg.token == "env-tok"


class TestTeamCityConfig:
    def test_complete(self) -> None:
        cfg = TeamCityConfig(base_url="https://tc.example.com", token="tok")
        assert cfg.is_complete() is True

    def test_empty_is_incomplete(self) -> None:
        cfg = TeamCityConfig()
        assert cfg.is_complete() is False

    def test_env_var_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TC_BASE_URL", "https://env-tc.example.com")
        monkeypatch.setenv("TC_TOKEN", "env-tok")
        cfg = load_teamcity_config()
        assert cfg.base_url == "https://env-tc.example.com"


class TestOctopusConfig:
    def test_complete(self) -> None:
        cfg = OctopusConfig(base_url="https://octo.example.com", api_key="key", space="Default")
        assert cfg.is_complete() is True
        assert cfg.missing_fields() == []

    def test_missing_space(self) -> None:
        cfg = OctopusConfig(base_url="https://octo.example.com", api_key="key")
        assert cfg.is_complete() is False
        assert "space" in cfg.missing_fields()

    def test_env_var_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OCTO_URL", "https://env-octo.example.com")
        monkeypatch.setenv("OCTO_API_KEY", "env-key")
        monkeypatch.setenv("OCTO_SPACE", "Spaces-1")
        cfg = load_octopus_config()
        assert cfg.base_url == "https://env-octo.example.com"
        assert cfg.api_key == "env-key"
        assert cfg.space == "Spaces-1"
