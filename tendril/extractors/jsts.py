"""JS/TS extractor — stub for v0 (SPEC.md §6).

Will implement .env*, package.json, API base URLs in v1.
Matches but returns minimal results for now.
"""

from __future__ import annotations

import json
import re
from typing import Any

from tendril.models.ir import (
    ConsumerRef,
    ConsumerRefKind,
    Evidence,
    FileEntry,
    IdentityClass,
    ProviderIdentity,
    RepoRef,
    TokenDecl,
)
from tendril.plugins.base import ExtractionResult, ExtractorPlugin

JSTS_INDICATORS = frozenset({
    "package.json", "tsconfig.json",
})

ENV_FILE_RE = re.compile(r"\.env(\.\w+)?$", re.IGNORECASE)
URL_RE = re.compile(r'https?://[a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,})(?::\d+)?(?:/[^\s"\']*)?')


class JSTSExtractor(ExtractorPlugin):
    def id(self) -> str:
        return "jsts"

    def matches(self, repo_tree: list[FileEntry]) -> bool:
        return any(
            f.path.lower() in JSTS_INDICATORS or f.path.lower() == "package.json"
            for f in repo_tree
        )

    def extract(
        self,
        repo: RepoRef,
        ref: str,
        tree: list[FileEntry],
        read_file: Any,
    ) -> ExtractionResult:
        consumer_refs: list[ConsumerRef] = []
        provider_identities: list[ProviderIdentity] = []
        token_decls: list[TokenDecl] = []

        for entry in tree:
            if entry.type != "file":
                continue

            try:
                if ENV_FILE_RE.search(entry.path):
                    content = _read_text(read_file, repo, ref, entry.path)
                    env_hint = _env_from_dotenv(entry.path)
                    _extract_dotenv(content, entry.path, env_hint, consumer_refs, token_decls)
            except Exception:
                continue

        return ExtractionResult(
            consumer_refs=consumer_refs,
            provider_identities=provider_identities,
            token_decls=token_decls,
        )


def _read_text(read_file: Any, repo: RepoRef, ref: str, path: str) -> str:
    raw = read_file(repo, ref, path)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _env_from_dotenv(path: str) -> str | None:
    m = re.search(r"\.env\.(\w+)$", path, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _extract_dotenv(
    content: str,
    path: str,
    env_hint: str | None,
    consumer_refs: list[ConsumerRef],
    token_decls: list[TokenDecl],
) -> None:
    for line_num, line in enumerate(content.split("\n"), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")

        if URL_RE.search(value):
            evidence = Evidence(source_type="file", locator=f"{path}:{line_num}")
            consumer_refs.append(ConsumerRef(
                kind=ConsumerRefKind.ENV_VAR,
                raw_value=value,
                env_hint=env_hint,
                evidence=[evidence],
            ))
