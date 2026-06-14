"""Deployed-ref resolution (SPEC.md §1.1, FR-24).

Resolves the exact SHA/branch deployed to each environment by following
the deploy plane chain: Octopus deployment → release → build metadata → VCS ref.
"""

from __future__ import annotations

import logging
from typing import Any

from tendril.models.ir import CICDProfile, DeployedRef, Evidence

log = logging.getLogger(__name__)


class DeployedRefResolver:
    def __init__(
        self,
        cicd_providers: dict[str, Any] | None = None,
        env_canonicalizer: Any = None,
    ) -> None:
        self._providers = cicd_providers or {}
        self._cache: dict[str, DeployedRef] = {}
        self._env_canon = env_canonicalizer

    def resolve(
        self,
        profile: CICDProfile,
        env: str,
        deployments: list[dict[str, Any]] | None = None,
    ) -> DeployedRef | None:
        cache_key = f"{profile.repo.full_name if profile.repo else '?'}@{env}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try deployment records if provided — works even if attribution did not
        # identify the deploy owner (graceful degradation, §4 invariant 5).
        if deployments:
            ref = self._resolve_from_deployments(deployments, env)
            if ref:
                self._cache[cache_key] = ref
                return ref

        deploy_owner = profile.deploy_owner
        if not deploy_owner:
            log.debug("No deploy owner for %s and no matching deployment record", cache_key)
            return None

        log.info("Could not resolve deployed ref for %s", cache_key)
        return None

    def _resolve_from_deployments(
        self,
        deployments: list[dict[str, Any]],
        env: str,
    ) -> DeployedRef | None:
        for deploy in deployments:
            deploy_env = deploy.get("EnvironmentName", deploy.get("environment", ""))
            # Canonicalize the deployment env name if a canonicalizer is available
            # so "Production" matches canonical "prod".
            if self._env_canon:
                norm_deploy_env, _ = self._env_canon.canonicalize(deploy_env)
            else:
                norm_deploy_env = deploy_env.lower()
            if norm_deploy_env.lower() != env.lower():
                continue

            release = deploy.get("Release", deploy.get("release", {}))
            build_info = release.get("BuildInformation", release.get("build_info", []))

            if isinstance(build_info, list) and build_info:
                info = build_info[0]
                sha = info.get("VcsCommitNumber", info.get("sha", ""))
                branch = info.get("Branch", info.get("branch", ""))
            elif isinstance(build_info, dict):
                sha = build_info.get("VcsCommitNumber", build_info.get("sha", ""))
                branch = build_info.get("Branch", build_info.get("branch", ""))
            else:
                sha = release.get("SelectedPackages", [{}])[0].get("Version", "") if release.get("SelectedPackages") else ""
                branch = ""

            if not sha:
                sha = deploy.get("ReleaseVersion", deploy.get("release_version", ""))

            if sha:
                return DeployedRef(
                    sha=sha,
                    branch=branch,
                    env=env,
                    deployable_id=deploy.get("ProjectId", deploy.get("project_id", "")),
                    deploy_timestamp=deploy.get("Created", deploy.get("created", "")),
                    source=deploy.get("TaskId", deploy.get("task_id", "")),
                )

        return None

    def resolve_from_fixture(
        self,
        deployments_data: list[dict[str, Any]],
        env: str,
        repo_full_name: str = "",
    ) -> DeployedRef | None:
        ref = self._resolve_from_deployments(deployments_data, env)
        if ref and repo_full_name:
            cache_key = f"{repo_full_name}@{env}"
            self._cache[cache_key] = ref
        return ref
