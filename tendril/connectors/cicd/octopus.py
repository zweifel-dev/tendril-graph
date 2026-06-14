"""Octopus Deploy CI/CD provider — CICDProvider implementation (SPEC.md §4.3).

Read-only connector for Octopus Deploy.  When *fixture_dir* is set,
responses are loaded from ``{fixture_dir}/{key}.json`` instead of HTTP —
this is the primary mode for the conformance suite.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

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
from tendril.plugins.base import CICDProvider

logger = logging.getLogger(__name__)


class OctopusProvider(CICDProvider):
    """Read-only Octopus Deploy connector (deploy plane)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        space: str,
        fixture_dir: Path | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._space = space
        self._fixture_dir = fixture_dir
        self._config_as_code: bool | None = None  # probed lazily

    # ------------------------------------------------------------------
    # ABC identity / capabilities
    # ------------------------------------------------------------------

    def id(self) -> str:
        return "octopus"

    def capabilities(self) -> Capabilities:
        return {
            "variable_preview": True,
            "deploy_logs": True,
            "env_scoping_model": True,
            "intrinsic": bool(self._config_as_code),
            "extrinsic": True,
            "config_as_code": bool(self._config_as_code),
        }

    # ------------------------------------------------------------------
    # Internal HTTP / fixture helpers
    # ------------------------------------------------------------------

    def _api_prefix(self) -> str:
        return f"/api/{self._space}"

    def _get_json(self, path: str, *, fixture_key: str | None = None) -> Any:
        """Fetch JSON from the Octopus REST API or a fixture file."""
        if self._fixture_dir is not None:
            key = fixture_key or path.strip("/").replace("/", "_")
            fixture_path = self._fixture_dir / f"{key}.json"
            with open(fixture_path, "r", encoding="utf-8") as fh:
                return json.load(fh)

        url = f"{self._base_url}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "X-Octopus-ApiKey": self._api_key,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310 — read-only
            return json.loads(resp.read().decode("utf-8"))

    def _get_text(self, path: str, *, fixture_key: str | None = None) -> str:
        """Fetch plain text (e.g. task logs)."""
        if self._fixture_dir is not None:
            key = fixture_key or path.strip("/").replace("/", "_")
            txt_path = self._fixture_dir / f"{key}.txt"
            if txt_path.exists():
                return txt_path.read_text(encoding="utf-8")
            json_path = self._fixture_dir / f"{key}.json"
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            return ""

        url = f"{self._base_url}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "X-Octopus-ApiKey": self._api_key,
                "Accept": "text/plain",
            },
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            return resp.read().decode("utf-8")

    # ------------------------------------------------------------------
    # CICDProvider interface
    # ------------------------------------------------------------------

    def list_pipelines(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        """Return all projects visible in the configured space."""
        data = self._get_json(
            f"{self._api_prefix()}/projects",
            fixture_key="projects",
        )
        items: list[dict[str, Any]] = data.get("Items", [])
        return [
            {
                "id": proj.get("Id", ""),
                "name": proj.get("Name", ""),
                "slug": proj.get("Slug", ""),
                "project_group_id": proj.get("ProjectGroupId", ""),
                "persistence_settings": proj.get("PersistenceSettings", {}),
            }
            for proj in items
        ]

    def discover_for_repo(
        self,
        repo: RepoRef,
        repo_tree: list[FileEntry],
    ) -> list[PipelineBinding]:
        """Discover Octopus projects associated with *repo*.

        Two discovery strategies:
        1. **Intrinsic (Config-as-Code)** — an ``.octopus/`` directory in
           the repo tree indicates the project is version-controlled.
        2. **Extrinsic (artifact provenance)** — scan projects for build
           information that references *repo*.
        """
        bindings: list[PipelineBinding] = []

        # --- 1. Intrinsic: .octopus/ (Config-as-Code) ------------------
        has_octopus_dir = any(
            entry.path == ".octopus" or entry.path.startswith(".octopus/")
            for entry in repo_tree
        )
        if has_octopus_dir:
            self._config_as_code = True
            bindings.append(
                PipelineBinding(
                    provider=self.id(),
                    pipeline_id="__config_as_code__",
                    repo=repo,
                    roles=["deploy"],
                )
            )

        # --- 2. Extrinsic: artifact provenance via projects -------------
        try:
            projects = self.list_pipelines({})
        except Exception:
            logger.debug("Could not list Octopus projects", exc_info=True)
            projects = []

        repo_slug = f"{repo.org}/{repo.name}".lower()

        for proj in projects:
            proj_id = proj.get("id", "")
            # Check persistence settings for CaC URL matching this repo
            ps = proj.get("persistence_settings", {})
            ps_url = str(ps.get("Url", ps.get("url", ""))).lower()
            if repo_slug in ps_url or (repo.url and repo.url.lower() in ps_url):
                bindings.append(
                    PipelineBinding(
                        provider=self.id(),
                        pipeline_id=proj_id,
                        repo=repo,
                        roles=["deploy"],
                    )
                )
                continue

            # Check deployment processes / build info for repo references
            try:
                releases = self._get_json(
                    f"{self._api_prefix()}/projects/{proj_id}/releases",
                    fixture_key=f"releases_{proj_id}",
                )
                for rel in releases.get("Items", [])[:5]:  # sample recent
                    build_info = rel.get("BuildInformation", [])
                    for bi in build_info:
                        vcs_url = str(bi.get("VcsCommitUrl", bi.get("VcsRoot", ""))).lower()
                        if repo_slug in vcs_url:
                            bindings.append(
                                PipelineBinding(
                                    provider=self.id(),
                                    pipeline_id=proj_id,
                                    repo=repo,
                                    roles=["deploy"],
                                )
                            )
                            break
                    else:
                        continue
                    break
            except Exception:
                logger.debug(
                    "Could not inspect releases for %s", proj_id, exc_info=True,
                )

        return bindings

    def read_variable_store(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> VariableStore:
        """Read the variable set for a project.

        Octopus variables carry a rich scoping model (environment, role,
        tenant, channel).  Sensitive variables have their value masked:
        ``value=None, is_secret=True`` (NFR-1).
        """
        data = self._get_json(
            f"{self._api_prefix()}/variables/{pipeline_or_project}",
            fixture_key=f"variables_{pipeline_or_project}",
        )
        entries: list[VarEntry] = []
        for var in data.get("Variables", []):
            is_sensitive = bool(var.get("IsSensitive", False))
            scope_obj = var.get("Scope", {})

            scope: dict[str, str | None] = {}
            for scope_key in ("Environment", "Role", "Tenant", "Channel"):
                vals = scope_obj.get(scope_key, [])
                if vals:
                    scope[scope_key.lower()] = ",".join(str(v) for v in vals)

            # If caller requested a specific env, skip variables that are
            # scoped to a different environment.
            env_scope_val = scope.get("environment")
            if env and env_scope_val:
                env_scopes = {e.strip().lower() for e in env_scope_val.split(",")}
                if env.lower() not in env_scopes:
                    continue

            entries.append(
                VarEntry(
                    key=var.get("Name", ""),
                    value=None if is_sensitive else var.get("Value"),
                    is_secret=is_sensitive,
                    readable=not is_sensitive,
                    scope=scope,
                )
            )

        return VariableStore(
            kind="octopus-variable-set",
            entries=entries,
            scoping_model="environment,role,tenant,channel",
        )

    def read_provider_identities(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> list[ProviderIdentity]:
        """Extract provider identities from deployment targets and tenants."""
        identities: list[ProviderIdentity] = []

        # --- Deployment targets (machines) ---
        try:
            machines = self._get_json(
                f"{self._api_prefix()}/machines",
                fixture_key="machines",
            )
            for m in machines.get("Items", []):
                endpoint = m.get("Endpoint", {})
                uri = endpoint.get("Uri", endpoint.get("Url", ""))
                if uri:
                    identities.append(
                        ProviderIdentity(
                            identity_class=IdentityClass.DEPLOY,
                            value=uri,
                            env=env,
                            evidence=[
                                Evidence(
                                    source_type="octopus-machine",
                                    locator=m.get("Id", ""),
                                )
                            ],
                        )
                    )
                # Hostnames from machine name
                machine_name = m.get("Name", "")
                if machine_name:
                    identities.append(
                        ProviderIdentity(
                            identity_class=IdentityClass.NETWORK,
                            value=machine_name,
                            env=env,
                            evidence=[
                                Evidence(
                                    source_type="octopus-machine",
                                    locator=m.get("Id", ""),
                                )
                            ],
                        )
                    )
        except Exception:
            logger.debug("Could not fetch Octopus machines", exc_info=True)

        # --- Tenants ---
        try:
            tenants = self._get_json(
                f"{self._api_prefix()}/tenants",
                fixture_key="tenants",
            )
            for t in tenants.get("Items", []):
                identities.append(
                    ProviderIdentity(
                        identity_class=IdentityClass.LOGICAL,
                        value=t.get("Name", ""),
                        env=env,
                        evidence=[
                            Evidence(
                                source_type="octopus-tenant",
                                locator=t.get("Id", ""),
                            )
                        ],
                    )
                )
        except Exception:
            logger.debug("Could not fetch Octopus tenants", exc_info=True)

        return identities

    def read_effective_value(
        self,
        token: str,
        project: str,
        env: str,
    ) -> dict[str, Any] | None:
        """Use the Octopus variable preview API (rung 3 of acquisition ladder).

        Returns the effective value for *token* in the given *project* and
        *env*, after Octopus has applied its scoping rules.
        """
        try:
            data = self._get_json(
                f"{self._api_prefix()}/variables/{project}/preview"
                f"?environment={env}",
                fixture_key=f"variable_preview_{project}_{env}",
            )
        except Exception:
            logger.debug(
                "Variable preview failed for %s/%s/%s",
                project, env, token,
                exc_info=True,
            )
            return None

        # The preview returns the full evaluated set; locate the token.
        for var in data.get("Variables", []):
            if var.get("Name", "") == token:
                if var.get("IsSensitive", False):
                    return {
                        "name": token,
                        "value": None,
                        "is_secret": True,
                        "resolved": True,
                    }
                return {
                    "name": token,
                    "value": var.get("Value"),
                    "is_secret": False,
                    "resolved": True,
                }

        return None

    def read_deploy_logs(self, run_id: str) -> list[str]:
        """Fetch the raw task log for *run_id*."""
        try:
            raw = self._get_text(
                f"{self._api_prefix()}/tasks/{run_id}/raw",
                fixture_key=f"task_log_{run_id}",
            )
            return raw.splitlines()
        except Exception:
            logger.debug("Could not fetch task log for %s", run_id, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Deployed-ref resolution (Octopus-specific)
    # ------------------------------------------------------------------

    def resolve_deployed_ref(
        self,
        project_id: str,
        env: str,
    ) -> DeployedRef | None:
        """Resolve the currently deployed VCS ref for *project_id* in *env*.

        Walk: deployments → release → build-info → VCS commit SHA.
        This is the linchpin for Invariant 10 ("resolve at the deployed
        ref, not ``main``").
        """
        try:
            deployments = self._get_json(
                f"{self._api_prefix()}/deployments"
                f"?projects={project_id}&environments={env}"
                f"&take=1",
                fixture_key=f"deployments_{project_id}_{env}",
            )
        except Exception:
            logger.debug(
                "Could not fetch deployments for %s/%s",
                project_id, env,
                exc_info=True,
            )
            return None

        items = deployments.get("Items", [])
        if not items:
            return None

        deployment = items[0]
        release_id = deployment.get("ReleaseId", "")
        deploy_time = deployment.get("Created", "")

        if not release_id:
            return None

        # Fetch the release to get build information
        try:
            release = self._get_json(
                f"{self._api_prefix()}/releases/{release_id}",
                fixture_key=f"release_{release_id}",
            )
        except Exception:
            logger.debug("Could not fetch release %s", release_id, exc_info=True)
            return None

        # Build information is either inline or needs a separate call
        build_info_list = release.get("BuildInformation", [])
        if not build_info_list:
            # Try the dedicated build-information endpoint
            try:
                bi_data = self._get_json(
                    f"{self._api_prefix()}/build-information"
                    f"?packageId={release.get('SelectedPackages', [{}])[0].get('ActionName', '')}",
                    fixture_key=f"build_info_{release_id}",
                )
                build_info_list = bi_data.get("Items", [])
            except Exception:
                logger.debug(
                    "Could not fetch build info for release %s",
                    release_id,
                    exc_info=True,
                )

        sha = ""
        branch = ""
        for bi in build_info_list:
            sha = bi.get("VcsCommitNumber", bi.get("VcsCommitId", ""))
            branch = bi.get("Branch", bi.get("VcsBranch", ""))
            if sha:
                break

        if not sha:
            return None

        return DeployedRef(
            sha=sha,
            branch=branch,
            env=env,
            deployable_id=project_id,
            deploy_timestamp=deploy_time,
            source=f"octopus:release:{release_id}",
        )
