"""Composition extractor (SPEC.md §6, FR-13).

Scans server-rendered markup (.aspx, .ascx, .master, .cshtml, .html) for
iframe/script/link/importmap references and detects token placeholders.
Locate-and-classify only — never resolves.
"""

from __future__ import annotations

import re
from typing import Any

from tendril.models.ir import (
    ConsumerRef,
    ConsumerRefKind,
    Evidence,
    FileEntry,
    ProviderIdentity,
    RepoRef,
    TokenDecl,
)
from tendril.plugins.base import ExtractionResult, ExtractorPlugin

COMPOSITION_EXTENSIONS = frozenset({
    ".aspx", ".ascx", ".master", ".cshtml", ".razor", ".html", ".htm",
})

TOKEN_PATTERNS = [
    (r"\{([a-zA-Z][a-zA-Z0-9_-]*)\}", "curly"),
    (r"#\{([a-zA-Z][a-zA-Z0-9_-]*)\}", "hash-curly"),
    (r"\$\{([a-zA-Z][a-zA-Z0-9_-]*)\}", "dollar-curly"),
    (r"%\(([a-zA-Z][a-zA-Z0-9_-]*)\)%", "percent"),
    (r"<%\$\s*AppSettings:\s*([a-zA-Z][a-zA-Z0-9_-]*)\s*%>", "asp-appsettings"),
]

IFRAME_RE = re.compile(r'<iframe\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
SCRIPT_RE = re.compile(r'<script\b[^>]*\bsrc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
LINK_RE = re.compile(r'<link\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


class CompositionExtractor(ExtractorPlugin):
    def id(self) -> str:
        return "composition"

    def matches(self, repo_tree: list[FileEntry]) -> bool:
        return any(
            _has_composition_ext(f.path) for f in repo_tree if f.type == "file"
        )

    def extract(
        self,
        repo: RepoRef,
        ref: str,
        tree: list[FileEntry],
        read_file: Any,
    ) -> ExtractionResult:
        consumer_refs: list[ConsumerRef] = []
        token_decls: list[TokenDecl] = []
        seen_tokens: set[str] = set()

        for entry in tree:
            if entry.type != "file" or not _has_composition_ext(entry.path):
                continue

            try:
                content = read_file(repo, ref, entry.path)
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
            except Exception:
                continue

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                evidence_loc = f"{entry.path}:{line_num}"

                for pattern, kind in [
                    (IFRAME_RE, ConsumerRefKind.IFRAME),
                    (SCRIPT_RE, ConsumerRefKind.SCRIPT),
                    (LINK_RE, ConsumerRefKind.LINK),
                ]:
                    for match in pattern.finditer(line):
                        raw_value = match.group(1)
                        if _is_static_asset(raw_value):
                            continue

                        tokens = _extract_tokens(raw_value)
                        consumer_refs.append(ConsumerRef(
                            kind=kind,
                            raw_value=raw_value,
                            token_refs=[t for t, _ in tokens],
                            evidence=[Evidence(
                                source_type="file", locator=evidence_loc,
                            )],
                        ))

                        for token_name, token_syntax in tokens:
                            if token_name not in seen_tokens:
                                seen_tokens.add(token_name)
                                token_decls.append(TokenDecl(
                                    name=token_name,
                                    declared_in=Evidence(
                                        source_type="file",
                                        locator=evidence_loc,
                                    ),
                                    injected=True,
                                ))

        return ExtractionResult(
            consumer_refs=consumer_refs,
            provider_identities=[],
            token_decls=token_decls,
        )


def _has_composition_ext(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in COMPOSITION_EXTENSIONS)


def _extract_tokens(value: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for pattern_str, syntax_name in TOKEN_PATTERNS:
        for match in re.finditer(pattern_str, value):
            tokens.append((match.group(1), syntax_name))
    return tokens


def _is_static_asset(url: str) -> bool:
    lower = url.lower()
    return any(lower.endswith(ext) for ext in (
        ".css", ".js", ".png", ".jpg", ".gif", ".svg", ".ico", ".woff", ".woff2",
    )) and not any(tok in url for tok in ("{", "#{", "${", "%(", "<%$"))
