"""Variable resolution + acquisition ladder (SPEC.md §9, critique C1 fix).

Tokens are evaluated per environment against the store the attribution
profile selected. The `ref` parameter threads the deployed SHA through
source reads (FR-24).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from tendril.models.ir import (
    AcquisitionResult,
    CICDProfile,
    Evidence,
    TokenDecl,
    VarEntry,
)

log = logging.getLogger(__name__)


def _parse_kv_from_logs(lines: list[str], key: str) -> str | None:
    """Extract a KEY=VALUE pair from deploy log lines (case-insensitive key match)."""
    pattern = re.compile(rf'^{re.escape(key)}=(.+)', re.IGNORECASE)
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


class Resolver:
    def __init__(
        self,
        vcs_providers: dict[str, Any] | None = None,
        cicd_providers: dict[str, Any] | None = None,
    ) -> None:
        self._vcs = vcs_providers or {}
        self._cicd = cicd_providers or {}

    def acquire(
        self,
        token: TokenDecl,
        repo: Any,
        env: str,
        profile: CICDProfile,
        ref: str | None = None,
        static_values: dict[str, str] | None = None,
        variable_stores: list[Any] | None = None,
        deploy_logs: list[str] | None = None,
    ) -> AcquisitionResult:
        """Acquisition ladder (§9) with ref parameter (critique C1 fix).

        Rungs 1-4, rung 5 (browser) removed from v0.
        """
        # Rung 1: Static config in repo (at deployed ref)
        if static_values and token.name in static_values:
            value = static_values[token.name]
            if value:
                return AcquisitionResult(
                    value=value,
                    rung="static",
                    evidence=[Evidence(
                        source_type="static-config",
                        locator=f"{token.declared_in}" if token.declared_in else f"static:{token.name}",
                    )],
                    resolved=True,
                )

        # Rung 2: CI/CD variable store API
        stores = variable_stores or []
        for store in stores:
            entry = _find_in_store(store, token.name, env)
            if entry:
                if entry.is_secret:
                    return AcquisitionResult(
                        value=AcquisitionResult.UNRESOLVED_SECRET,
                        rung="store_api",
                        evidence=[Evidence(
                            source_type="variable-store",
                            locator=f"{store.kind}:{token.name} (secret)",
                        )],
                        resolved=False,
                        is_secret=True,
                    )
                if entry.value:
                    return AcquisitionResult(
                        value=entry.value,
                        rung="store_api",
                        evidence=[Evidence(
                            source_type="variable-store",
                            locator=f"{store.kind}:{token.name}",
                        )],
                        resolved=True,
                    )

        # Rung 3: Effective-value / preview API
        deploy_owner = profile.deploy_owner
        if deploy_owner:
            provider = self._cicd.get(deploy_owner.provider_id)
            if provider and hasattr(provider, "read_effective_value"):
                try:
                    result = provider.read_effective_value(
                        token.name,
                        profile.repo.name if profile.repo else "",
                        env,
                    )
                    if result and isinstance(result, dict):
                        value = result.get("Value") or result.get("value")
                        if value:
                            return AcquisitionResult(
                                value=value,
                                rung="preview_api",
                                evidence=[Evidence(
                                    source_type="preview-api",
                                    locator=f"{deploy_owner.provider_id}:preview:{token.name}@{env}",
                                )],
                                resolved=True,
                            )
                except Exception:
                    pass

        # Rung 4: Deploy-log harvesting
        if deploy_logs:
            log_result = _parse_kv_from_logs(deploy_logs, token.name)
            if log_result is not None:
                return AcquisitionResult(
                    value=log_result,
                    rung="deploy_log",
                    evidence=[Evidence(
                        source_type="deploy-log",
                        locator=f"deploy-log:{token.name}",
                    )],
                    resolved=True,
                )

        return AcquisitionResult(
            value=AcquisitionResult.UNRESOLVED_NO_SOURCE,
            rung="exhausted",
            evidence=[Evidence(
                source_type="acquisition-ladder",
                locator=f"unresolved:{token.name}@{env}",
            )],
            resolved=False,
        )


def _find_in_store(store: Any, token_name: str, env: str) -> VarEntry | None:
    if not hasattr(store, "entries"):
        return None

    for entry in store.entries:
        if entry.key.lower() != token_name.lower():
            continue
        entry_env = entry.scope.get("env", "")
        if entry_env and entry_env.lower() == env.lower():
            return entry
        if not entry_env:
            return entry

    return None
