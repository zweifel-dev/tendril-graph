"""RoslynIntraRepoProvider — IntraRepoProvider backed by TendrilRoslyn subprocess.

Implements FR-M8-003/004/005/010/012/013.
Thread-safe via SubprocessBridge's internal lock.
"""

from __future__ import annotations

import logging
from typing import Any

from tendril.config import get_redact_patterns, get_roslyn_binary, is_secret_key
from tendril.connectors.intra.subprocess_bridge import SubprocessBridge, SubprocessError
from tendril.models.ir import (
    Capabilities,
    FileEntry,
    IntraRepoFacts,
    ResolvedValue,
    Unresolved,
)
from tendril.plugins.base import IntraRepoProvider

log = logging.getLogger(__name__)

# .NET indicator extensions / filenames
_DOTNET_INDICATORS = frozenset({".cs", ".vb", ".csproj", ".vbproj", ".sln"})
_DOTNET_FILENAMES  = frozenset({"web.config"})
_DOTNET_PREFIXES   = ("appsettings",)


def _is_dotnet_repo(repo_tree: list[FileEntry]) -> bool:
    for entry in repo_tree:
        path_lower = entry.path.lower()
        name = path_lower.split("/")[-1]
        ext  = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        if ext in _DOTNET_INDICATORS:
            return True
        if name in _DOTNET_FILENAMES:
            return True
        if any(name.startswith(p) for p in _DOTNET_PREFIXES) and name.endswith(".json"):
            return True
    return False


class RoslynIntraRepoProvider(IntraRepoProvider):
    """IntraRepoProvider backed by the TendrilRoslyn subprocess (M8).

    One SubprocessBridge instance per provider instance.
    One provider instance per ``tendril graph build`` run (CHK017).
    """

    _PROVIDER_ID = "roslyn-intra-repo"

    def __init__(
        self,
        binary_path: str | None = None,
        default_timeout: float = 30.0,
        analyze_timeout: float = 120.0,
    ) -> None:
        resolved_path = binary_path if binary_path is not None else get_roslyn_binary()
        self._binary_path = resolved_path
        self._bridge: SubprocessBridge | None = None
        self._default_timeout = default_timeout
        self._analyze_timeout = analyze_timeout
        self._redact_patterns = get_redact_patterns()
        self._available: bool | None = None  # None = not yet probed

    def id(self) -> str:
        return self._PROVIDER_ID

    # ── capability probing ────────────────────────────────────────────────────

    def capabilities(self) -> Capabilities:
        """Return capability flags.  All-false when binary is absent/incompatible.

        Never raises (Principle V — NON-NEGOTIABLE).
        """
        if self._binary_path is None:
            self._warn_binary_unavailable("binary path not configured")
            return {"layer1": False, "layer2": False, "def_use": False}

        try:
            bridge = self._get_bridge()
            result = bridge.call("handshake", {"client_version": "1.0"})
            compatible = result.get("compatible", False)
            if not compatible:
                self._warn_binary_unavailable("version incompatible")
                return {"layer1": False, "layer2": False, "def_use": False}
            return {"layer1": True, "layer2": True, "def_use": True}
        except (SubprocessError, FileNotFoundError, OSError) as exc:
            self._warn_binary_unavailable(str(exc))
            return {"layer1": False, "layer2": False, "def_use": False}

    def _warn_binary_unavailable(self, detail: str) -> None:
        log.warning(
            "Roslyn binary unavailable: %s",
            detail,
            extra={"event": "roslyn-binary-unavailable"},
        )

    # ── matches ───────────────────────────────────────────────────────────────

    def matches(self, repo_tree: list[FileEntry]) -> bool:
        """Return True if the repo contains .NET files (FR-M8-013 / CHK027)."""
        return _is_dotnet_repo(repo_tree)

    # ── analyze ───────────────────────────────────────────────────────────────

    def analyze(self, repo_path: str) -> IntraRepoFacts:
        """Run full analysis (layer 1 + layer 2) on the .NET repo.

        Returns empty IntraRepoFacts on binary absence or subprocess failure.
        Never raises (Principle V — NON-NEGOTIABLE).
        """
        if self._binary_path is None:
            return IntraRepoFacts(partial_analysis=True)

        try:
            bridge = self._get_bridge()
            raw = bridge.call("analyze", {"repo_path": repo_path})
            return self._deserialize_facts(raw)
        except (SubprocessError, OSError) as exc:
            log.warning(
                "RoslynIntraRepoProvider.analyze failed for %s: %s",
                repo_path, exc,
            )
            return IntraRepoFacts(partial_analysis=True)

    # ── resolve_value ─────────────────────────────────────────────────────────

    def resolve_value(self, repo_path: str, key: str) -> ResolvedValue | Unresolved:
        """Resolve a single key.  Applies secret redaction before returning.

        Never raises; never fabricates a value (Principle VII).
        """
        # Secret check first — key name is enough (CHK006 / FR-M8-012)
        if is_secret_key(key, self._redact_patterns):
            return Unresolved(reason="is-secret")

        if self._binary_path is None:
            return Unresolved(reason="not-found")

        try:
            bridge = self._get_bridge()
            raw = bridge.call("resolve_value", {"repo_path": repo_path, "key": key})
            return self._deserialize_resolved(raw)
        except (SubprocessError, OSError) as exc:
            log.warning(
                "RoslynIntraRepoProvider.resolve_value failed for %s/%s: %s",
                repo_path, key, exc,
            )
            return Unresolved(reason="not-found", detail=str(exc))

    # ── internals ─────────────────────────────────────────────────────────────

    def _get_bridge(self) -> SubprocessBridge:
        if self._bridge is None:
            assert self._binary_path is not None
            self._bridge = SubprocessBridge(
                command=[self._binary_path],
                default_timeout=self._default_timeout,
                analyze_timeout=self._analyze_timeout,
            )
        return self._bridge

    def close(self) -> None:
        """Release the subprocess.  Call when the build run is complete."""
        if self._bridge is not None:
            self._bridge._close()
            self._bridge = None

    def __enter__(self) -> "RoslynIntraRepoProvider":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ── deserialization ───────────────────────────────────────────────────────

    def _deserialize_facts(self, raw: dict[str, Any]) -> IntraRepoFacts:
        """Convert raw RPC result dict to IntraRepoFacts, applying secret redaction."""
        value_sets: dict[str, list[Any]] = {}
        def_use: dict[str, Any] = {}

        for key, entries in (raw.get("value_sets") or {}).items():
            if is_secret_key(key, self._redact_patterns):
                continue  # drop secret keys entirely (FR-M8-012)
            value_sets[key] = entries

        for key, chain in (raw.get("def_use") or {}).items():
            if is_secret_key(key, self._redact_patterns):
                continue
            def_use[key] = chain

        return IntraRepoFacts(
            def_use=def_use,
            value_sets=value_sets,
            call_graph=None,
            partial_analysis=bool(raw.get("partial_analysis", False)),
            truncated=bool(raw.get("truncated", False)),
            skipped_files=list(raw.get("skipped_files") or []),
        )

    def _deserialize_resolved(self, raw: dict[str, Any]) -> ResolvedValue | Unresolved:
        if raw.get("resolved") is False:
            return Unresolved(
                reason=raw.get("reason", "not-found"),
                detail=raw.get("detail"),
            )
        return ResolvedValue(
            value=raw.get("value"),
            def_use_chain=raw.get("def_use_chain"),
            resolved=True,
            source=raw.get("source"),
            layer=raw.get("layer"),
        )
