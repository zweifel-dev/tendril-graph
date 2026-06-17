"""Runtime configuration helpers for Tendril-Graph.

Reads from environment variables (highest priority) and tendril.toml.
No write paths. Secrets are never echoed.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any


def _load_toml(path: Path) -> dict[str, Any]:
    """Load tendril.toml if it exists; return empty dict otherwise."""
    if not path.exists():
        return {}
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _find_toml() -> dict[str, Any]:
    """Walk up from cwd looking for tendril.toml."""
    here = Path.cwd()
    for candidate in [here, *here.parents]:
        toml_path = candidate / "tendril.toml"
        if toml_path.exists():
            return _load_toml(toml_path)
    return {}


_TOML_CACHE: dict[str, Any] | None = None


def _toml() -> dict[str, Any]:
    global _TOML_CACHE
    if _TOML_CACHE is None:
        _TOML_CACHE = _find_toml()
    return _TOML_CACHE


def get_roslyn_binary() -> str | None:
    """Return path to TendrilRoslyn binary.

    Resolution order (FR-M8-008 / CHK008):
    1. TENDRIL_ROSLYN_BINARY environment variable
    2. [intra_repo] roslyn_binary in tendril.toml
    3. None (PATH is NOT searched — explicit path required)
    """
    env_val = os.environ.get("TENDRIL_ROSLYN_BINARY")
    if env_val:
        return env_val
    return _toml().get("intra_repo", {}).get("roslyn_binary")


# Default secret redaction patterns (FR-M8-012 / CHK006).
# All patterns are case-insensitive globs.
_DEFAULT_REDACT_PATTERNS = [
    "*password*",
    "*secret*",
    "*token*",
    "*apikey*",
    "*api_key*",
    "*connectionstring*",
    "*connstr*",
]


def get_redact_patterns() -> list[str]:
    """Return secret-key redaction glob patterns (case-insensitive).

    Merges defaults with any extra patterns from tendril.toml [redact_patterns].
    """
    extra = _toml().get("redact_patterns", {}).get("extra", [])
    return list(_DEFAULT_REDACT_PATTERNS) + list(extra)


def is_secret_key(key: str, patterns: list[str] | None = None) -> bool:
    """Return True if *key* matches any redaction pattern (case-insensitive)."""
    pats = patterns if patterns is not None else get_redact_patterns()
    key_lower = key.lower()
    return any(fnmatch.fnmatch(key_lower, p.lower()) for p in pats)


# ---------------------------------------------------------------------------
# LLM provider configuration (M9 — hybrid mode)
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Resolved LLM provider configuration.

    Resolution order (highest priority first):
      1. Environment variables (TENDRIL_LLM_*)
      2. [llm] section in tendril.toml
      3. Built-in defaults

    is_complete() returns True iff endpoint + model + api_key are all present.
    """
    endpoint: str | None = None
    model: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 60
    max_evidence_files: int = 20
    max_evidence_bytes: int = 50_000
    cache_path: str = "~/.tendril/llm-cache/"

    def is_complete(self) -> bool:
        return bool(self.endpoint and self.model and self.api_key)

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.endpoint:
            missing.append("endpoint")
        if not self.model:
            missing.append("model")
        if not self.api_key:
            missing.append("api_key")
        return missing


def load_llm_config() -> LLMConfig:
    """Resolve LLMConfig from env vars > tendril.toml [llm] > defaults."""
    toml_llm = _toml().get("llm", {})
    return LLMConfig(
        endpoint=os.environ.get("TENDRIL_LLM_ENDPOINT") or toml_llm.get("endpoint") or None,
        model=os.environ.get("TENDRIL_LLM_MODEL") or toml_llm.get("model") or None,
        api_key=os.environ.get("TENDRIL_LLM_API_KEY") or toml_llm.get("api_key") or None,
        timeout_seconds=int(
            os.environ.get("TENDRIL_LLM_TIMEOUT") or toml_llm.get("timeout_seconds", 60)
        ),
        max_evidence_files=int(toml_llm.get("max_evidence_files", 20)),
        max_evidence_bytes=int(toml_llm.get("max_evidence_bytes", 50_000)),
        cache_path=os.environ.get("TENDRIL_LLM_CACHE_PATH")
            or toml_llm.get("cache_path", "~/.tendril/llm-cache/"),
    )


# ---------------------------------------------------------------------------
# Datadog telemetry configuration (M10)
# ---------------------------------------------------------------------------

@dataclass
class DatadogConfig:
    """Resolved Datadog telemetry configuration.

    Resolution order (highest priority first):
      1. Environment variables (DD_API_KEY, DD_APP_KEY, DD_SITE, TENDRIL_DD_*)
      2. [telemetry.datadog] section in tendril.toml
      3. Built-in defaults

    is_complete() returns True iff api_key, app_key, and site are all present.
    """
    api_key: str | None = None
    app_key: str | None = None
    site: str | None = None
    timeout_seconds: int = 60
    lookback_hours: int = 24
    max_results: int = 1000

    def is_complete(self) -> bool:
        return bool(self.api_key and self.app_key and self.site)

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.api_key:
            missing.append("api_key")
        if not self.app_key:
            missing.append("app_key")
        if not self.site:
            missing.append("site")
        return missing


@dataclass
class HTTPConfig:
    """Shared HTTP resilience configuration.

    Resolution order (highest priority first):
      1. Environment variables (TENDRIL_HTTP_*)
      2. [http] section in tendril.toml
      3. Built-in defaults
    """
    timeout_seconds: int = 30
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_factor: float = 2.0


def load_http_config() -> HTTPConfig:
    """Resolve HTTPConfig from env vars > tendril.toml [http] > defaults."""
    toml_http = _toml().get("http", {})
    return HTTPConfig(
        timeout_seconds=int(
            os.environ.get("TENDRIL_HTTP_TIMEOUT") or toml_http.get("timeout", 30)
        ),
        max_retries=int(
            os.environ.get("TENDRIL_HTTP_RETRIES") or toml_http.get("retries", 3)
        ),
        backoff_base=float(toml_http.get("backoff_base", 1.0)),
        backoff_factor=float(toml_http.get("backoff_factor", 2.0)),
    )


def load_datadog_config() -> DatadogConfig:
    """Resolve DatadogConfig from env vars > tendril.toml [telemetry.datadog] > defaults."""
    toml_dd = _toml().get("telemetry", {}).get("datadog", {})
    return DatadogConfig(
        api_key=os.environ.get("DD_API_KEY") or toml_dd.get("api_key") or None,
        app_key=os.environ.get("DD_APP_KEY") or toml_dd.get("app_key") or None,
        site=os.environ.get("DD_SITE") or toml_dd.get("site") or None,
        timeout_seconds=int(
            os.environ.get("TENDRIL_DD_TIMEOUT_SECONDS")
            or toml_dd.get("timeout_seconds", 60)
        ),
        lookback_hours=int(
            os.environ.get("TENDRIL_DD_LOOKBACK_HOURS")
            or toml_dd.get("lookback_hours", 24)
        ),
        max_results=int(
            os.environ.get("TENDRIL_DD_MAX_RESULTS")
            or toml_dd.get("max_results", 1000)
        ),
    )


# ---------------------------------------------------------------------------
# VCS/CI/CD provider configuration (006-production-readiness)
# ---------------------------------------------------------------------------

def _env_or_none(key: str) -> str | None:
    """Return env var value or None if unset/empty/whitespace."""
    val = os.environ.get(key, "")
    return val if val.strip() else None


@dataclass
class GitHubConfig:
    """GitHub VCS provider credentials.

    Two auth paths: PAT (token) or GitHub App (app_id+install_id+private_key_path).
    """
    token: str = ""
    app_id: str = ""
    install_id: str = ""
    private_key_path: str = ""

    def is_complete(self) -> bool:
        return bool(self.token.strip()) or all(
            f.strip() for f in [self.app_id, self.install_id, self.private_key_path]
        )

    def missing_fields(self) -> list[str]:
        if self.token.strip():
            return []
        missing = []
        if not self.app_id.strip():
            missing.append("app_id")
        if not self.install_id.strip():
            missing.append("install_id")
        if not self.private_key_path.strip():
            missing.append("private_key_path")
        return missing


def load_github_config() -> GitHubConfig:
    """Resolve GitHubConfig from env vars > tendril.toml [vcs.github] > defaults."""
    toml_gh = _toml().get("vcs", {}).get("github", {})
    return GitHubConfig(
        token=_env_or_none("GH_TOKEN") or toml_gh.get("token", ""),
        app_id=_env_or_none("GH_APP_ID") or toml_gh.get("app_id", ""),
        install_id=_env_or_none("GH_INSTALL_ID") or toml_gh.get("install_id", ""),
        private_key_path=_env_or_none("GH_PRIVATE_KEY_PATH") or toml_gh.get("private_key_path", ""),
    )


@dataclass
class BitbucketDCConfig:
    """Bitbucket Data Center VCS provider credentials."""
    base_url: str = ""
    token: str = ""

    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.token.strip())

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.base_url.strip():
            missing.append("base_url")
        if not self.token.strip():
            missing.append("token")
        return missing


def load_bitbucket_dc_config() -> BitbucketDCConfig:
    """Resolve BitbucketDCConfig from env vars > tendril.toml [vcs.bitbucket_dc] > defaults."""
    toml_bb = _toml().get("vcs", {}).get("bitbucket_dc", {})
    return BitbucketDCConfig(
        base_url=_env_or_none("BB_BASE_URL") or toml_bb.get("base_url", ""),
        token=_env_or_none("BB_TOKEN") or toml_bb.get("token", ""),
    )


@dataclass
class TeamCityConfig:
    """TeamCity CI/CD provider credentials."""
    base_url: str = ""
    token: str = ""

    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.token.strip())

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.base_url.strip():
            missing.append("base_url")
        if not self.token.strip():
            missing.append("token")
        return missing


def load_teamcity_config() -> TeamCityConfig:
    """Resolve TeamCityConfig from env vars > tendril.toml [cicd.teamcity] > defaults."""
    toml_tc = _toml().get("cicd", {}).get("teamcity", {})
    return TeamCityConfig(
        base_url=_env_or_none("TC_BASE_URL") or toml_tc.get("base_url", ""),
        token=_env_or_none("TC_TOKEN") or toml_tc.get("token", ""),
    )


@dataclass
class OctopusConfig:
    """Octopus Deploy CI/CD provider credentials."""
    base_url: str = ""
    api_key: str = ""
    space: str = ""

    def is_complete(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip() and self.space.strip())

    def missing_fields(self) -> list[str]:
        missing = []
        if not self.base_url.strip():
            missing.append("base_url")
        if not self.api_key.strip():
            missing.append("api_key")
        if not self.space.strip():
            missing.append("space")
        return missing


def load_octopus_config() -> OctopusConfig:
    """Resolve OctopusConfig from env vars > tendril.toml [cicd.octopus] > defaults."""
    toml_oc = _toml().get("cicd", {}).get("octopus", {})
    return OctopusConfig(
        base_url=_env_or_none("OCTO_URL") or toml_oc.get("base_url", ""),
        api_key=_env_or_none("OCTO_API_KEY") or toml_oc.get("api_key", ""),
        space=_env_or_none("OCTO_SPACE") or toml_oc.get("space", ""),
    )
