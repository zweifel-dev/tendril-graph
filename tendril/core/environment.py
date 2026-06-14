"""Environment canonicalization (closes SPEC.md §17.3).

Strategy: case-fold + configurable alias table. Unmatched env names
get the raw name + low confidence — never a resolution failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# core/environment.py → parent = core/, parent.parent = project root
DEFAULT_ENVIRONMENTS_FILE = Path(__file__).parent.parent / "data" / "environments_default.yaml"


@dataclass
class CanonicalEnvironment:
    canonical: str
    aliases: frozenset[str]


class EnvironmentCanonicalizer:
    def __init__(self, env_config: dict[str, list[str]] | None = None) -> None:
        self._lookup: dict[str, str] = {}
        if env_config:
            self._load(env_config)

    @classmethod
    def from_file(cls, path: Path | None = None) -> EnvironmentCanonicalizer:
        path = path or DEFAULT_ENVIRONMENTS_FILE
        if not path.exists():
            log.warning("Environment config not found: %s", path)
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f)
        envs = data.get("environments", {})
        config: dict[str, list[str]] = {}
        for canonical, info in envs.items():
            aliases = info.get("aliases", []) if isinstance(info, dict) else info
            config[canonical] = aliases
        return cls(config)

    def _load(self, env_config: dict[str, list[str]]) -> None:
        for canonical, aliases in env_config.items():
            lower_canonical = canonical.lower()
            self._lookup[lower_canonical] = canonical
            for alias in aliases:
                self._lookup[alias.lower()] = canonical

    def canonicalize(self, env_name: str) -> tuple[str, bool]:
        """Return (canonical_name, is_exact_match).

        If no match, returns (original_name, False) — never fails.
        """
        canonical = self._lookup.get(env_name.lower())
        if canonical:
            return canonical, True
        return env_name, False

    def all_canonical(self) -> list[str]:
        return sorted(set(self._lookup.values()))
