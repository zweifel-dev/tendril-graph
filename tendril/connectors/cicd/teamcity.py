"""TeamCity CI/CD provider — CICDProvider implementation (SPEC.md §4.3).

Read-only connector for JetBrains TeamCity.  When *fixture_dir* is set,
responses are loaded from ``{fixture_dir}/{key}.json`` instead of HTTP —
this is the primary mode for the conformance suite.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tendril.models.ir import (
    Capabilities,
    Evidence,
    FileEntry,
    IdentityClass,
    PipelineBinding,
    ProviderIdentity,
    RepoRef,
    VarEntry,
    VariableStore,
)
from tendril.config import HTTPConfig
from tendril.connectors._http import resilient_get
from tendril.plugins.base import CICDProvider

logger = logging.getLogger(__name__)

_MINIMUM_SUPPORTED_VERSION = "2021.1"


class TeamCityProvider(CICDProvider):
    """Read-only TeamCity connector (build plane)."""

    def __init__(
        self,
        base_url: str,
        token: str,
        fixture_dir: Path | None = None,
        http_config: HTTPConfig | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._fixture_dir = fixture_dir
        self._http_config = http_config or HTTPConfig()
        self._server_version: str | None = None

    # ------------------------------------------------------------------
    # ABC identity / capabilities
    # ------------------------------------------------------------------

    def id(self) -> str:
        return "teamcity"

    def capabilities(self) -> Capabilities:
        return {
            "variable_preview": False,
            "deploy_logs": True,
            "env_scoping_model": False,
            "intrinsic": True,
            "extrinsic": True,
        }

    # ------------------------------------------------------------------
    # Internal HTTP / fixture helpers
    # ------------------------------------------------------------------

    def _get_json(self, path: str, *, fixture_key: str | None = None) -> Any:
        """Fetch JSON from the TeamCity REST API or a fixture file."""
        if self._fixture_dir is not None:
            key = fixture_key or path.strip("/").replace("/", "_")
            fixture_path = self._fixture_dir / f"{key}.json"
            with open(fixture_path, "r", encoding="utf-8") as fh:
                return json.load(fh)

        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        result = resilient_get(url, headers=headers, config=self._http_config)
        if not result.ok:
            raise urllib.error.URLError(result.error or f"HTTP {result.status}")
        return json.loads(result.body.decode("utf-8"))

    def _get_text(self, path: str, *, fixture_key: str | None = None) -> str:
        """Fetch plain text (e.g. build logs)."""
        if self._fixture_dir is not None:
            key = fixture_key or path.strip("/").replace("/", "_")
            # Logs are stored as plain .txt alongside JSON fixtures.
            txt_path = self._fixture_dir / f"{key}.txt"
            if txt_path.exists():
                return txt_path.read_text(encoding="utf-8")
            # Fall back to .json that wraps text in a JSON string.
            json_path = self._fixture_dir / f"{key}.json"
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            return ""

        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "text/plain",
        }
        result = resilient_get(url, headers=headers, config=self._http_config)
        if not result.ok:
            raise urllib.error.URLError(result.error or f"HTTP {result.status}")
        return result.body.decode("utf-8")

    def _check_version(self) -> None:
        """Log a warning if the TeamCity version is below the tested minimum."""
        if self._server_version is not None:
            return
        try:
            info = self._get_json("/app/rest/server", fixture_key="server")
            self._server_version = str(info.get("version", "unknown"))
            if (
                self._server_version != "unknown"
                and self._server_version < _MINIMUM_SUPPORTED_VERSION
            ):
                logger.warning(
                    "TeamCity %s is below the tested minimum %s — "
                    "some API endpoints may behave differently",
                    self._server_version,
                    _MINIMUM_SUPPORTED_VERSION,
                )
        except Exception:
            logger.debug("Could not read TeamCity server version", exc_info=True)
            self._server_version = "unknown"

    # ------------------------------------------------------------------
    # CICDProvider interface
    # ------------------------------------------------------------------

    def list_pipelines(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        """Return all build configurations visible to the token.

        *scope* is accepted but currently unused (reserved for project
        filtering).
        """
        self._check_version()
        data = self._get_json("/app/rest/buildTypes", fixture_key="buildTypes")
        build_types: list[dict[str, Any]] = data.get("buildType", [])
        return [
            {
                "id": bt.get("id", ""),
                "name": bt.get("name", ""),
                "project_id": bt.get("projectId", ""),
                "project_name": bt.get("projectName", ""),
                "href": bt.get("href", ""),
            }
            for bt in build_types
        ]

    def discover_for_repo(
        self,
        repo: RepoRef,
        repo_tree: list[FileEntry],
    ) -> list[PipelineBinding]:
        """Discover TeamCity pipelines associated with *repo*.

        Two discovery strategies:
        1. **Intrinsic** — a ``.teamcity/`` directory in the repo tree
           (Kotlin DSL / XML settings).
        2. **Extrinsic** — VCS roots whose URL matches *repo*.
        """
        self._check_version()
        bindings: list[PipelineBinding] = []

        # --- 1. Intrinsic: .teamcity/ directory -------------------------
        has_teamcity_dir = any(
            entry.path == ".teamcity" or entry.path.startswith(".teamcity/")
            for entry in repo_tree
        )
        if has_teamcity_dir:
            bindings.append(
                PipelineBinding(
                    provider=self.id(),
                    pipeline_id="__intrinsic__",
                    repo=repo,
                    roles=["build"],
                )
            )

        # --- 2. Extrinsic: VCS root URL matching ------------------------
        try:
            vcs_data = self._get_json("/app/rest/vcs-roots", fixture_key="vcs-roots")
        except Exception:
            logger.debug("Could not fetch VCS roots", exc_info=True)
            vcs_data = {}

        repo_urls = _repo_url_variants(repo)

        for vr in vcs_data.get("vcs-root", []):
            vcs_url = str(vr.get("url", vr.get("href", "")))
            vr_id = str(vr.get("id", ""))

            # Fetch the full VCS root details to get the actual repository URL
            if vcs_url and not vcs_url.startswith(("http://", "https://", "git@")):
                try:
                    detail = self._get_json(
                        f"/app/rest/vcs-roots/id:{vr_id}",
                        fixture_key=f"vcs-root_{vr_id}",
                    )
                    props = {
                        p["name"]: p.get("value", "")
                        for p in detail.get("properties", {}).get("property", [])
                    }
                    vcs_url = props.get("url", vcs_url)
                except Exception:
                    logger.debug("Could not fetch VCS root %s", vr_id, exc_info=True)

            if _url_matches_repo(vcs_url, repo_urls):
                bindings.append(
                    PipelineBinding(
                        provider=self.id(),
                        pipeline_id=vr_id,
                        repo=repo,
                        roles=["build"],
                    )
                )

        return bindings

    def read_variable_store(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> VariableStore:
        """Read parameters for a build configuration.

        Password-type parameters have their value masked: ``value=None,
        is_secret=True`` (NFR-1).
        """
        data = self._get_json(
            f"/app/rest/buildTypes/{pipeline_or_project}/parameters",
            fixture_key=f"parameters_{pipeline_or_project}",
        )
        entries: list[VarEntry] = []
        for prop in data.get("property", []):
            name = prop.get("name", "")
            ptype = prop.get("type", {})
            raw_type = ptype if isinstance(ptype, str) else ptype.get("rawValue", "")
            is_secret = "password" in raw_type.lower()

            entries.append(
                VarEntry(
                    key=name,
                    value=None if is_secret else prop.get("value"),
                    is_secret=is_secret,
                    scope={"env": env} if env else {},
                )
            )

        return VariableStore(kind="teamcity-parameters", entries=entries)

    def read_provider_identities(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> list[ProviderIdentity]:
        """Extract provider identities from build-configuration parameters.

        Looks for parameters whose names suggest a deploy target, hostname,
        or service URL (e.g. ``deploy.host``, ``env.service_url``).
        """
        store = self.read_variable_store(pipeline_or_project, env)
        identities: list[ProviderIdentity] = []
        _DEPLOY_HINTS = {"host", "url", "endpoint", "target", "server", "address"}

        for entry in store.entries:
            key_lower = entry.key.lower()
            if entry.is_secret or entry.value is None:
                continue
            parts = set(key_lower.replace(".", " ").replace("_", " ").split())
            if parts & _DEPLOY_HINTS:
                identities.append(
                    ProviderIdentity(
                        identity_class=IdentityClass.NETWORK,
                        value=entry.value,
                        env=env,
                        evidence=[
                            Evidence(
                                source_type="teamcity-parameter",
                                locator=f"{pipeline_or_project}:{entry.key}",
                            )
                        ],
                    )
                )

        return identities

    def read_deploy_logs(self, run_id: str) -> list[str]:
        """Fetch the build log for *run_id* (deploy-log harvest, rung 4)."""
        try:
            raw = self._get_text(
                f"/app/rest/builds/{run_id}/log",
                fixture_key=f"build_log_{run_id}",
            )
            return raw.splitlines()
        except Exception:
            logger.debug("Could not fetch build log for %s", run_id, exc_info=True)
            return []


# ------------------------------------------------------------------
# URL matching helpers
# ------------------------------------------------------------------

def _normalize_git_url(url: str) -> str:
    """Normalize a Git URL to ``host/org/repo`` for comparison."""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # Strip protocol
    for prefix in ("https://", "http://", "ssh://", "git@"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    # git@ style: git@host:org/repo → host/org/repo
    url = url.replace(":", "/", 1) if ":" in url and "/" not in url.split(":")[0] else url
    return url.lower()


def _repo_url_variants(repo: RepoRef) -> set[str]:
    """Generate plausible normalized URL suffixes for *repo*."""
    variants: set[str] = set()
    slug = f"{repo.org}/{repo.name}".lower()
    variants.add(slug)
    if repo.url:
        variants.add(_normalize_git_url(repo.url))
    return variants


def _url_matches_repo(vcs_url: str, repo_variants: set[str]) -> bool:
    """Return True if *vcs_url* matches any of the *repo_variants*."""
    normalized = _normalize_git_url(vcs_url)
    return any(normalized.endswith(v) for v in repo_variants)
