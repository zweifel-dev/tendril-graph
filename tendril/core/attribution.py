"""CI/CD Attribution Engine (SPEC.md §7).

Discovers each repo's CI/CD providers (build owner, deploy owner) and
produces a CICDProfile that routes tokens to the correct variable store.
Runs BETWEEN extraction and resolution.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from tendril.models.ir import (
    CICDProfile,
    CICDProviderEntry,
    Confidence,
    Evidence,
    FileEntry,
    PipelineBinding,
    RepoRef,
)

log = logging.getLogger(__name__)

# core/attribution.py → parent = core/, parent.parent = project root
SIGNATURES_FILE = Path(__file__).parent.parent / "data" / "deploy_step_signatures.yaml"

INTRINSIC_DETECTORS: dict[str, list[str]] = {
    "github-actions": [".github/workflows/"],
    "teamcity": [".teamcity/"],
    "octopus": [".octopus/"],
    "circleci": [".circleci/config.yml"],
    "bitbucket-pipelines": ["bitbucket-pipelines.yml"],
    "azure-devops": ["azure-pipelines.yml"],
    "jenkins": ["Jenkinsfile"],
}

# Workflow file prefixes/names per provider — used to find files to read.
_WORKFLOW_FILE_PATTERNS: dict[str, list[str]] = {
    "github-actions": [".github/workflows/"],
    "teamcity": [".teamcity/"],
    "circleci": [".circleci/"],
    "azure-devops": ["azure-pipelines.yml"],
    "bitbucket-pipelines": ["bitbucket-pipelines.yml"],
    "jenkins": ["Jenkinsfile"],
}


class AttributionEngine:
    def __init__(
        self,
        cicd_providers: list[Any] | None = None,
        signatures_path: Path | None = None,
    ) -> None:
        self._cicd_providers = cicd_providers or []
        self._signatures = _load_signatures(signatures_path or SIGNATURES_FILE)

    def attribute(
        self,
        repo: RepoRef,
        repo_tree: list[FileEntry],
        extrinsic_bindings: list[PipelineBinding] | None = None,
        read_file: Any = None,
        ref: str = "HEAD",
    ) -> CICDProfile:
        intrinsic = self._detect_intrinsic(repo_tree)
        extrinsic = extrinsic_bindings or []

        providers: list[CICDProviderEntry] = []
        detected_envs: list[str] = []

        for provider_id, evidence_list in intrinsic.items():
            roles = ["build"]
            deploy_evidence = self._detect_deploy_steps(
                repo_tree, provider_id,
                read_file=read_file, repo=repo, ref=ref,
            )
            if deploy_evidence:
                roles.append("deploy")
                evidence_list.extend(deploy_evidence)

            providers.append(CICDProviderEntry(
                provider_id=provider_id,
                roles=roles,
                confidence=Confidence.HIGH,
                evidence=evidence_list,
                env_scoping_source=_env_scoping_source(provider_id),
            ))

        for binding in extrinsic:
            existing = next(
                (p for p in providers if p.provider_id == binding.provider),
                None,
            )
            if existing:
                for role in binding.roles:
                    if role not in existing.roles:
                        existing.roles.append(role)
                existing.evidence.append(
                    Evidence(source_type="extrinsic", locator=f"pipeline:{binding.pipeline_id}")
                )
            else:
                providers.append(CICDProviderEntry(
                    provider_id=binding.provider,
                    roles=binding.roles,
                    confidence=Confidence.MEDIUM,
                    evidence=[Evidence(
                        source_type="extrinsic",
                        locator=f"pipeline:{binding.pipeline_id}",
                    )],
                    env_scoping_source=_env_scoping_source(binding.provider),
                ))
            if binding.env and binding.env not in detected_envs:
                detected_envs.append(binding.env)

        providers = _resolve_chaining(providers)
        confidence = _overall_confidence(providers)

        return CICDProfile(
            repo=repo,
            environments=detected_envs,
            providers=providers,
            confidence=confidence,
            evidence=[e for p in providers for e in p.evidence],
        )

    def _detect_intrinsic(
        self, repo_tree: list[FileEntry],
    ) -> dict[str, list[Evidence]]:
        result: dict[str, list[Evidence]] = {}
        paths = {f.path for f in repo_tree}

        for provider_id, detector_patterns in INTRINSIC_DETECTORS.items():
            for pattern in detector_patterns:
                if pattern.endswith("/"):
                    if any(p.startswith(pattern) or p == pattern.rstrip("/") for p in paths):
                        result.setdefault(provider_id, []).append(
                            Evidence(source_type="intrinsic", locator=f"dir:{pattern}")
                        )
                else:
                    if pattern in paths:
                        result.setdefault(provider_id, []).append(
                            Evidence(source_type="intrinsic", locator=f"file:{pattern}")
                        )

        return result

    def _detect_deploy_steps(
        self,
        repo_tree: list[FileEntry],
        build_provider_id: str,
        read_file: Any = None,
        repo: RepoRef | None = None,
        ref: str = "HEAD",
    ) -> list[Evidence]:
        """Scan workflow files for deploy-step signatures.

        When *read_file* is available (a VCSProvider.read_file callable), reads
        each workflow file and searches for signature patterns. Without it,
        returns nothing — we never fabricate attribution.
        """
        if not read_file or not repo:
            return []

        workflow_paths = _workflow_paths_for_provider(repo_tree, build_provider_id)
        if not workflow_paths:
            return []

        # Read all relevant workflow files
        file_contents: dict[str, str] = {}
        for wf_path in workflow_paths:
            try:
                raw = read_file(repo, ref, wf_path)
                content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                file_contents[wf_path] = content
            except Exception:
                log.debug("Could not read workflow file %s@%s", wf_path, ref)

        if not file_contents:
            return []

        evidence: list[Evidence] = []
        for sig in self._signatures:
            pattern = sig.get("pattern", "")
            if not pattern:
                continue
            for wf_path, content in file_contents.items():
                # action_id uses exact string match; step_name_pattern uses regex
                match_type = sig.get("match_type", "step_name_pattern")
                if match_type == "action_id":
                    matched = pattern in content
                else:
                    try:
                        matched = bool(re.search(pattern, content))
                    except re.error:
                        matched = pattern in content

                if matched:
                    evidence.append(Evidence(
                        source_type="deploy-step-signature",
                        locator=f"{wf_path}:{sig['provider_id']}:{pattern}",
                    ))
                    break  # one match per signature is enough

        return evidence


def _workflow_paths_for_provider(
    repo_tree: list[FileEntry], provider_id: str,
) -> list[str]:
    """Return file paths of workflow files for the given build provider."""
    patterns = _WORKFLOW_FILE_PATTERNS.get(provider_id, [])
    paths: list[str] = []
    for entry in repo_tree:
        if entry.type != "file":
            continue
        for pat in patterns:
            if pat.endswith("/"):
                if entry.path.startswith(pat):
                    paths.append(entry.path)
            else:
                if entry.path == pat:
                    paths.append(entry.path)
    return paths


def _resolve_chaining(providers: list[CICDProviderEntry]) -> list[CICDProviderEntry]:
    """Handle build→deploy chaining (e.g., TC builds, Octopus deploys).

    If a dedicated deploy-only provider exists, strip "deploy" from any provider
    that got it incidentally (e.g., TC detected an Octopus step in its config).
    """
    deploy_dedicated = [p for p in providers if p.roles == ["deploy"]]
    if not deploy_dedicated:
        return providers

    for p in providers:
        if "build" in p.roles and "deploy" in p.roles and p not in deploy_dedicated:
            p.roles = [r for r in p.roles if r != "deploy"]

    return providers


def _overall_confidence(providers: list[CICDProviderEntry]) -> Confidence:
    if not providers:
        return Confidence.LOW
    confidences = [p.confidence for p in providers]
    if all(c == Confidence.HIGH for c in confidences):
        return Confidence.HIGH
    if any(c == Confidence.LOW for c in confidences):
        return Confidence.LOW
    return Confidence.MEDIUM


def _env_scoping_source(provider_id: str) -> str:
    return {
        "github-actions": "github-environments",
        "octopus": "octopus-environments",
        "teamcity": "teamcity-parameters",
        "circleci": "circleci-contexts",
        "bitbucket-pipelines": "bitbucket-deployments",
    }.get(provider_id, "")


def _load_signatures(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        log.warning("Deploy step signatures not found: %s", path)
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("signatures", [])
