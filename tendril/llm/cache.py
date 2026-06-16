"""Disk-based LLM response cache for hybrid mode (M9 FR-011).

Cache key: SHA-256 of JSON-serialised {goal, sorted locators}.
Entries are stored as flat {sha256}.json files under cache_path.
If the cache directory is inaccessible, operations log a WARNING and no-op
(the build never fails due to cache errors).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class DiskCacheEntry:
    cache_key: str
    goal: str
    locators: list[str]
    raw_response: dict[str, Any]
    created_at: str
    contract_version: str


class DiskResponseCache:
    def __init__(self, cache_path: str) -> None:
        self._root = Path(cache_path).expanduser()

    def _ensure_dir(self) -> bool:
        """Return True if cache dir is usable; log WARNING + return False otherwise."""
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            return True
        except OSError as exc:
            log.warning("LLM cache directory inaccessible (%s): %s — operating without cache", self._root, exc)
            return False

    @staticmethod
    def make_cache_key(goal: str, locators: list[str]) -> str:
        payload = json.dumps(
            {"goal": goal, "locators": sorted(locators)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()

    def get(self, goal: str, locators: list[str]) -> dict[str, Any] | None:
        if not self._ensure_dir():
            return None
        key = self.make_cache_key(goal, locators)
        entry_path = self._root / f"{key}.json"
        try:
            if entry_path.exists():
                data = json.loads(entry_path.read_bytes())
                return data.get("raw_response")
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("LLM cache read error for key %s: %s", key, exc)
        return None

    def put(
        self,
        goal: str,
        locators: list[str],
        raw_response: dict[str, Any],
        contract_version: str,
    ) -> None:
        if not self._ensure_dir():
            return
        key = self.make_cache_key(goal, locators)
        entry = DiskCacheEntry(
            cache_key=key,
            goal=goal,
            locators=sorted(locators),
            raw_response=raw_response,
            created_at=datetime.now(timezone.utc).isoformat(),
            contract_version=contract_version,
        )
        entry_path = self._root / f"{key}.json"
        try:
            entry_path.write_text(
                json.dumps(entry.__dict__, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("LLM cache write error for key %s: %s", key, exc)
