"""Octopus Deploy CI/CD provider — CICDProvider implementation (SPEC.md §4.3).

Read-only connector for Octopus Deploy.  When *fixture_dir* is set,
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
from tendril.config import HTTPConfig
from tendril.connectors._http import resilient_get
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
        http_config: HTTPConfig | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._space = space
        self._fixture_dir = fixture_dir
        self._http_config = http_config or HTTPConfig()
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
        headers = {
            "X-Octopus-ApiKey": self._api_key,
            "Accept": "application/json",
        }
        result = resilient_get(url, headers=headers, config=self._http_config)
        if not result.ok:
            raise urllib.error.URLError(result.error or f"HTTP {result.status}")
        return json.loads(result.body.decode("utf-8"))

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
        headers = {
            "X-Octopus-ApiKey": self._api_key,
            "Accept": "text/plain",
        }
        result = resilient_get(url, headers=headers, config=self._http_config)
        if not result.ok:
            raise urllib.error.URLError(result.error or f"HTTP {result.status}")
        return result.body.decode("utf-8")

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

    # ------------------------------------------------------------------
    # Scope resolution helpers (M7-2)
    # ------------------------------------------------------------------

    def _scope_matches(
        self,
        var_scope: dict[str, str | None],
        env: str,
        role: str | None = None,
        tenant: str | None = None,
        channel: str | None = None,
    ) -> bool:
        """Return True if *var_scope* is compatible with the given env/role/etc.

        A scope dimension that is absent in *var_scope* is treated as a wildcard
        (matches any value).  A present dimension must match the requested value.
        """
        env_scope = var_scope.get("environment")
        if env_scope:
            env_scopes = {e.strip().lower() for e in env_scope.split(",")}
            if env.lower() not in env_scopes:
                return False

        if role is not None:
            role_scope = var_scope.get("role")
            if role_scope:
                role_scopes = {r.strip().lower() for r in role_scope.split(",")}
                if role.lower() not in role_scopes:
                    return False

        if tenant is not None:
            tenant_scope = var_scope.get("tenant")
            if tenant_scope:
                tenant_scopes = {t.strip().lower() for t in tenant_scope.split(",")}
                if tenant.lower() not in tenant_scopes:
                    return False

        if channel is not None:
            channel_scope = var_scope.get("channel")
            if channel_scope:
                channel_scopes = {c.strip().lower() for c in channel_scope.split(",")}
                if channel.lower() not in channel_scopes:
                    return False

        return True

    def _best_match(
        self,
        candidates: list[VarEntry],
        env: str,
    ) -> VarEntry | list[VarEntry]:
        """Select the best-scoped variable from *candidates* for *env*.

        Priority (highest first): env-scoped > role-scoped > tenant-scoped >
        channel-scoped > unscoped.  Within the same priority tier, the entry
        with the most scope dimensions set wins.  An exact tie returns all
        tied entries so the caller can emit ``ambiguous=True``.
        """
        compatible = [c for c in candidates if self._scope_matches(c.scope, env)]
        if not compatible:
            # Fall back to unscoped entries.
            compatible = [c for c in candidates if not any(c.scope.values())]
        if not compatible:
            compatible = candidates  # last resort

        def _rank(entry: VarEntry) -> tuple[int, int]:
            scope = entry.scope
            priority = 0
            dimensions = 0
            if scope.get("environment"):
                priority = max(priority, 4)
                dimensions += 1
            if scope.get("role"):
                priority = max(priority, 3)
                dimensions += 1
            if scope.get("tenant"):
                priority = max(priority, 2)
                dimensions += 1
            if scope.get("channel"):
                priority = max(priority, 1)
                dimensions += 1
            return (priority, dimensions)

        max_rank = max(_rank(c) for c in compatible)
        best = [c for c in compatible if _rank(c) == max_rank]

        if len(best) == 1:
            return best[0]
        return best  # tied — caller must handle ambiguity

    def read_variable_store(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> VariableStore:
        """Read the variable set for a project.

        Octopus variables carry a rich scoping model (environment, role,
        tenant, channel).  Sensitive variables have their value masked:
        ``value=None, is_secret=True`` (NFR-1).

        When *env* is provided, ``_best_match()`` selects the highest-priority
        scoped entry per variable name.  Exact ties are returned with
        ``scope["_ambiguous"] = "true"`` so callers can detect ambiguous
        resolution (M7-2).
        """
        data = self._get_json(
            f"{self._api_prefix()}/variables/{pipeline_or_project}",
            fixture_key=f"variables_{pipeline_or_project}",
        )

        # Parse all variable entries, grouped by name.
        by_name: dict[str, list[VarEntry]] = {}
        for var in data.get("Variables", []):
            is_sensitive = bool(var.get("IsSensitive", False))
            scope_obj = var.get("Scope", {})

            scope: dict[str, str | None] = {}
            for scope_key in ("Environment", "Role", "Tenant", "Channel"):
                vals = scope_obj.get(scope_key, [])
                if vals:
                    scope[scope_key.lower()] = ",".join(str(v) for v in vals)

            entry = VarEntry(
                key=var.get("Name", ""),
                value=None if is_sensitive else var.get("Value"),
                is_secret=is_sensitive,
                readable=not is_sensitive,
                scope=scope,
            )
            by_name.setdefault(entry.key, []).append(entry)

        if not env:
            # No env filter — return all entries as-is.
            return VariableStore(
                kind="octopus-variable-set",
                entries=[e for group in by_name.values() for e in group],
                scoping_model="environment,role,tenant,channel",
            )

        # Apply best-match scoping per variable name.
        entries: list[VarEntry] = []
        for _name, group in by_name.items():
            result = self._best_match(group, env)
            if isinstance(result, list):
                # Tied — emit all tied candidates with ambiguous marker.
                for tied_entry in result:
                    tied_entry.scope["_ambiguous"] = "true"
                    entries.append(tied_entry)
            else:
                entries.append(result)

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
