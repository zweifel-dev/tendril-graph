"""Reverse index — global provider-identity index (SPEC.md §8).

Materializes all provider projections: for every deployable, every identity
it claims, keyed for exact and normalized lookup with alias resolution.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from tendril.models.ir import (
    Confidence,
    Evidence,
    IdentityClass,
    ProviderIdentity,
)

log = logging.getLogger(__name__)


@dataclass
class IndexEntry:
    deployable_id: str
    repo_full_name: str
    identity_class: IdentityClass
    raw_value: str
    confidence: Confidence
    evidence: list[Evidence] = field(default_factory=list)
    env: str | None = None


class ReverseIndex:
    def __init__(self) -> None:
        self._exact: dict[str, list[IndexEntry]] = {}
        self._normalized: dict[str, list[IndexEntry]] = {}

    def add(
        self,
        deployable_id: str,
        repo_full_name: str,
        identities: list[ProviderIdentity],
    ) -> None:
        for identity in identities:
            entry = IndexEntry(
                deployable_id=deployable_id,
                repo_full_name=repo_full_name,
                identity_class=identity.identity_class,
                raw_value=identity.value,
                confidence=_class_confidence(identity.identity_class),
                evidence=list(identity.evidence),
                env=identity.env,
            )

            self._exact.setdefault(identity.value, []).append(entry)

            normalized = _normalize(identity.value, identity.identity_class)
            self._normalized.setdefault(normalized, []).append(entry)

    def lookup(
        self, value: str, env: str | None = None,
    ) -> list[IndexEntry]:
        candidates = self._exact.get(value, [])
        if not candidates:
            normalized = _normalize_lookup(value)
            candidates = self._normalized.get(normalized, [])

        if env:
            env_lower = env.lower()
            env_matched = [c for c in candidates if c.env and c.env.lower() == env_lower]
            env_agnostic = [c for c in candidates if not c.env]
            return env_matched or env_agnostic or candidates

        return candidates

    @property
    def size(self) -> int:
        return sum(len(v) for v in self._exact.values())


def _normalize(value: str, identity_class: IdentityClass) -> str:
    if identity_class == IdentityClass.NETWORK:
        return _normalize_url(value)
    return value.lower().strip()


def _normalize_url(url: str) -> str:
    if "://" not in url:
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host = host.lower().rstrip(".")
        host = re.sub(r"^www\.", "", host)
        path = parsed.path.rstrip("/") or "/"
        return f"{host}{path}"
    except Exception:
        return url.lower()


def _normalize_lookup(value: str) -> str:
    if "://" in value or "." in value:
        return _normalize_url(value)
    return value.lower().strip()


def _class_confidence(identity_class: IdentityClass) -> Confidence:
    return {
        IdentityClass.DEPLOY: Confidence.HIGH,
        IdentityClass.ARTIFACT: Confidence.HIGH,
        IdentityClass.NETWORK: Confidence.HIGH,
        IdentityClass.LOGICAL: Confidence.MEDIUM,
        IdentityClass.ASYNC: Confidence.MEDIUM,
        IdentityClass.DATA: Confidence.LOW,
    }.get(identity_class, Confidence.MEDIUM)
