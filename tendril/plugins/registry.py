"""Plugin registry — discovery, capability negotiation, version checking.

Discovers plugins via importlib.metadata entry_points (group="tendril.plugins")
and via explicit manifest paths.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tendril.plugins.base import (
    CICDProvider,
    ExtractorPlugin,
    GraphStore,
    IntraRepoProvider,
    LLMProvider,
    TelemetryProvider,
    VCSProvider,
)
from tendril.plugins.manifest import PluginManifest, load_manifest

log = logging.getLogger(__name__)

FAMILY_TO_ABC: dict[str, type] = {
    "vcs": VCSProvider,
    "cicd": CICDProvider,
    "extractor": ExtractorPlugin,
    "intra_repo": IntraRepoProvider,
    "telemetry": TelemetryProvider,
    "graph_store": GraphStore,
    "llm": LLMProvider,
}


@dataclass
class RegisteredPlugin:
    manifest: PluginManifest
    instance: Any = None


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, RegisteredPlugin] = {}

    def discover(self) -> list[str]:
        """Discover plugins via importlib.metadata entry_points."""
        discovered: list[str] = []
        try:
            eps = importlib.metadata.entry_points(group="tendril.plugins")
        except Exception:
            eps = []

        for ep in eps:
            try:
                plugin_factory = ep.load()
                instance = plugin_factory()
                id_attr = getattr(instance, "id", None)
                if callable(id_attr):
                    plugin_id: str = str(id_attr())
                elif id_attr is not None:
                    plugin_id = str(id_attr)
                else:
                    plugin_id = ep.name
                manifest = PluginManifest(
                    id=plugin_id,
                    family=_infer_family(instance),
                    contract_version="1.0.0-alpha",
                    entry_point=ep.value,
                )
                self.register(manifest, instance)
                discovered.append(plugin_id)
            except Exception as exc:
                log.warning("Failed to load plugin %s: %s", ep.name, exc)

        return discovered

    def register(
        self,
        manifest: PluginManifest,
        instance: Any = None,
    ) -> list[str]:
        errors = manifest.validate()
        if errors:
            log.error("Plugin %s has manifest errors: %s", manifest.id, errors)
            return errors
        self._plugins[manifest.id] = RegisteredPlugin(
            manifest=manifest, instance=instance,
        )
        log.info("Registered plugin: %s (family=%s)", manifest.id, manifest.family)
        return []

    def register_from_manifest(self, path: Path) -> list[str]:
        manifest = load_manifest(path)
        return self.register(manifest)

    def get(self, plugin_id: str) -> RegisteredPlugin | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self, family: str | None = None) -> list[RegisteredPlugin]:
        plugins = list(self._plugins.values())
        if family:
            plugins = [p for p in plugins if p.manifest.family == family]
        return plugins

    def get_providers(self, family: str) -> list[Any]:
        return [
            p.instance
            for p in self._plugins.values()
            if p.manifest.family == family and p.instance is not None
        ]


def _infer_family(instance: Any) -> str:
    for family, abc in FAMILY_TO_ABC.items():
        if isinstance(instance, abc):
            return family
    return "unknown"
