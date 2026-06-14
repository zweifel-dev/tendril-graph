""".NET extractor (SPEC.md §6).

Parses appsettings.json, web.config, .csproj, and related .NET config files
to extract consumer references, provider identities, and token declarations.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
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

DOTNET_INDICATORS = frozenset({
    ".csproj", ".vbproj", ".fsproj", ".sln",
    "appsettings.json", "web.config", "app.config",
})

URL_PATTERN = re.compile(
    r'https?://[a-zA-Z0-9._-]+(?:\.[a-zA-Z]{2,})(?::\d+)?(?:/[^\s"\'<>,;}\]]*)?'
)

TOKEN_IN_VALUE = re.compile(r'\{([a-zA-Z][a-zA-Z0-9_:-]*)\}')


class DotNetExtractor(ExtractorPlugin):
    def id(self) -> str:
        return "dotnet"

    def matches(self, repo_tree: list[FileEntry]) -> bool:
        return any(
            any(f.path.lower().endswith(ind) or f.path.lower() == ind for ind in DOTNET_INDICATORS)
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

            lower_path = entry.path.lower()

            try:
                if lower_path.endswith("appsettings.json") or re.match(
                    r"appsettings\.\w+\.json$", lower_path, re.IGNORECASE,
                ):
                    content = _read_text(read_file, repo, ref, entry.path)
                    env_hint = _env_from_appsettings(entry.path)
                    _extract_appsettings(
                        content, entry.path, env_hint,
                        consumer_refs, token_decls,
                    )

                elif lower_path == "web.config" or lower_path.endswith(".config"):
                    content = _read_text(read_file, repo, ref, entry.path)
                    _extract_web_config(
                        content, entry.path,
                        consumer_refs, token_decls,
                    )

                elif lower_path.endswith((".csproj", ".vbproj", ".fsproj")):
                    content = _read_text(read_file, repo, ref, entry.path)
                    _extract_csproj(content, entry.path, provider_identities)

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


def _env_from_appsettings(path: str) -> str | None:
    m = re.match(r"appsettings\.(\w+)\.json$", path, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _extract_appsettings(
    content: str,
    path: str,
    env_hint: str | None,
    consumer_refs: list[ConsumerRef],
    token_decls: list[TokenDecl],
) -> None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return

    _walk_json(data, path, env_hint, consumer_refs, token_decls, prefix="")


def _walk_json(
    obj: Any,
    path: str,
    env_hint: str | None,
    consumer_refs: list[ConsumerRef],
    token_decls: list[TokenDecl],
    prefix: str,
) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str):
                _classify_string_value(
                    key, value, path, full_key, env_hint,
                    consumer_refs, token_decls,
                )
            else:
                _walk_json(value, path, env_hint, consumer_refs, token_decls, full_key)


def _classify_string_value(
    key: str,
    value: str,
    path: str,
    json_path: str,
    env_hint: str | None,
    consumer_refs: list[ConsumerRef],
    token_decls: list[TokenDecl],
) -> None:
    evidence = Evidence(source_type="file", locator=f"{path}:{json_path}")
    lower_key = key.lower()

    tokens = TOKEN_IN_VALUE.findall(value)
    if tokens:
        for token_name in tokens:
            token_decls.append(TokenDecl(
                name=token_name, declared_in=evidence, injected=True,
            ))
    elif _key_looks_like_url(key) and value:
        # Literal URL in a URL-named key — emit a TokenDecl so this config
        # location appears in downstream evidence (e.g. appsettings.prod.json).
        token_decls.append(TokenDecl(
            name=_camel_to_kebab(key),
            declared_in=evidence,
            injected=False,
        ))

    if URL_PATTERN.search(value) or tokens:
        kind = _infer_kind(lower_key)
        consumer_refs.append(ConsumerRef(
            kind=kind,
            raw_value=value,
            token_refs=tokens,
            env_hint=env_hint,
            evidence=[evidence],
        ))
    elif lower_key in ("baseurl", "baseaddress", "apiurl", "serviceurl", "endpoint"):
        if value:
            consumer_refs.append(ConsumerRef(
                kind=ConsumerRefKind.HTTP_CLIENT,
                raw_value=value,
                token_refs=tokens,
                env_hint=env_hint,
                evidence=[evidence],
            ))


def _camel_to_kebab(s: str) -> str:
    """Convert CamelCase / PascalCase key to kebab-case token name."""
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1-\2', s)
    s = re.sub(r'([a-z\d])([A-Z])', r'\1-\2', s)
    return s.lower()


def _key_looks_like_url(key: str) -> bool:
    lower = key.lower()
    return any(k in lower for k in ("url", "endpoint", "address", "host", "baseurl", "serviceurl"))


def _infer_kind(key_lower: str) -> ConsumerRefKind:
    if "connection" in key_lower:
        return ConsumerRefKind.CONNECTION_STRING
    if any(k in key_lower for k in ("url", "baseaddress", "endpoint", "host", "api")):
        return ConsumerRefKind.HTTP_CLIENT
    return ConsumerRefKind.OTHER


def _extract_web_config(
    content: str,
    path: str,
    consumer_refs: list[ConsumerRef],
    token_decls: list[TokenDecl],
) -> None:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return

    for add in root.iter("add"):
        key = add.get("key", "")
        value = add.get("value", "")
        if not key:
            continue

        evidence = Evidence(source_type="file", locator=f"{path}:appSettings/{key}")
        tokens = TOKEN_IN_VALUE.findall(value)
        for token_name in tokens:
            token_decls.append(TokenDecl(
                name=token_name, declared_in=evidence, injected=True,
            ))

        if value and (URL_PATTERN.search(value) or tokens):
            consumer_refs.append(ConsumerRef(
                kind=_infer_kind(key.lower()),
                raw_value=value,
                token_refs=tokens,
                evidence=[evidence],
            ))

    for cs in root.iter("add"):
        conn_str = cs.get("connectionString", "")
        name = cs.get("name", "")
        if conn_str and name:
            evidence = Evidence(source_type="file", locator=f"{path}:connectionStrings/{name}")
            consumer_refs.append(ConsumerRef(
                kind=ConsumerRefKind.CONNECTION_STRING,
                raw_value=conn_str,
                evidence=[evidence],
            ))

    for endpoint in root.iter("endpoint"):
        address = endpoint.get("address", "")
        name = endpoint.get("name", "")
        if address:
            evidence = Evidence(source_type="file", locator=f"{path}:wcf/{name}")
            consumer_refs.append(ConsumerRef(
                kind=ConsumerRefKind.WCF_ENDPOINT,
                raw_value=address,
                evidence=[evidence],
            ))


def _extract_csproj(
    content: str,
    path: str,
    provider_identities: list[ProviderIdentity],
) -> None:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return

    for ns in ("", "{http://schemas.microsoft.com/developer/msbuild/2003}"):
        for pkg_ref in root.iter(f"{ns}PackageReference"):
            pkg_name = pkg_ref.get("Include", "")
            pkg_version = pkg_ref.get("Version", "")
            if pkg_name:
                provider_identities.append(ProviderIdentity(
                    identity_class=IdentityClass.ARTIFACT,
                    value=f"nuget:{pkg_name}@{pkg_version}" if pkg_version else f"nuget:{pkg_name}",
                    evidence=[Evidence(
                        source_type="file",
                        locator=f"{path}:PackageReference/{pkg_name}",
                    )],
                ))
