"""Plugin manifest loading and validation (SPEC.md §4.9).

Plugins register via `tendril-plugin.toml` manifests declaring id, family,
contract_version, and static capabilities. Discovery uses
importlib.metadata entry_points.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tendril.plugins.base import CONTRACT_VERSION


VALID_FAMILIES = frozenset({
    "vcs", "cicd", "extractor", "intra_repo",
    "telemetry", "graph_store", "llm",
})


@dataclass
class PluginManifest:
    id: str
    family: str
    contract_version: str
    capabilities: dict[str, bool] = field(default_factory=dict)
    entry_point: str = ""
    subprocess_binary: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.id:
            errors.append("manifest missing 'id'")
        if self.family not in VALID_FAMILIES:
            errors.append(
                f"unknown family '{self.family}'; "
                f"must be one of {sorted(VALID_FAMILIES)}"
            )
        if not self.contract_version:
            errors.append("manifest missing 'contract_version'")
        elif not _major_compatible(self.contract_version, CONTRACT_VERSION):
            errors.append(
                f"contract version '{self.contract_version}' is not compatible "
                f"with core contract '{CONTRACT_VERSION}'"
            )
        return errors


def load_manifest(path: Path) -> PluginManifest:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    plugin = data.get("plugin", data)
    return PluginManifest(
        id=plugin.get("id", ""),
        family=plugin.get("family", ""),
        contract_version=plugin.get("contract_version", ""),
        capabilities=plugin.get("capabilities", {}),
        entry_point=plugin.get("entry_point", ""),
        subprocess_binary=plugin.get("subprocess_binary", ""),
    )


def _major_compatible(plugin_ver: str, core_ver: str) -> bool:
    """Check that the major version of the plugin matches core."""
    try:
        p_major = int(plugin_ver.split(".")[0])
        c_major = int(core_ver.split(".")[0])
        return p_major == c_major
    except (ValueError, IndexError):
        return False
