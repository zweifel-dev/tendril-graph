"""Bitbucket Pipelines CI/CD provider stub — CICDProvider implementation (M7-3).

Reads `bitbucket-pipelines.yml` to discover deployment-scoped pipeline
bindings.  Variable store reads return empty (deferred to a future milestone).

Scanned YAML paths:
  pipelines.branches.<pattern>.steps[].deployment
  pipelines.pull-requests.<pattern>.steps[].deployment
  pipelines.custom.<name>.steps[].deployment
  pipelines.default.steps[].deployment
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from tendril.models.ir import (
    Capabilities,
    FileEntry,
    PipelineBinding,
    ProviderIdentity,
    RepoRef,
    VariableStore,
)
from tendril.plugins.base import CICDProvider

log = logging.getLogger(__name__)


class BitbucketPipelinesProvider(CICDProvider):
    """Read-only Bitbucket Pipelines connector (stub — v0)."""

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self._fixture_dir = fixture_dir

    # ------------------------------------------------------------------
    # ABC identity / capabilities
    # ------------------------------------------------------------------

    def id(self) -> str:
        return "bitbucket-pipelines"

    def capabilities(self) -> Capabilities:
        return {
            "intrinsic": True,
            "env_scoping_model": True,
            "variable_preview": False,
            "deploy_logs": False,
        }

    # ------------------------------------------------------------------
    # CICDProvider interface
    # ------------------------------------------------------------------

    def discover_for_repo(
        self,
        repo: RepoRef,
        repo_tree: list[FileEntry],
    ) -> list[PipelineBinding]:
        """Parse `bitbucket-pipelines.yml` and produce PipelineBindings.

        Steps with a ``deployment:`` field produce bindings with roles=["deploy"].
        In fixture mode, reads from ``fixture_dir/bitbucket-pipelines.yml``.
        """
        if self._fixture_dir is not None:
            pipeline_file = self._fixture_dir / "bitbucket-pipelines.yml"
            if pipeline_file.exists():
                return self._parse_pipeline_bytes(
                    pipeline_file.read_bytes(), str(pipeline_file), repo,
                )
            return []

        # Live mode: check for bitbucket-pipelines.yml in repo tree.
        has_pipeline_file = any(
            e.path == "bitbucket-pipelines.yml" for e in repo_tree
        )
        if not has_pipeline_file:
            return []

        return [
            PipelineBinding(
                provider=self.id(),
                pipeline_id="bitbucket-pipelines.yml",
                repo=repo,
                roles=["build"],
            )
        ]

    def list_pipelines(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def read_variable_store(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> VariableStore:
        return VariableStore(kind="bitbucket-pipelines", entries=[], scoping_model="bitbucket-deployments")

    def read_provider_identities(
        self,
        pipeline_or_project: str,
        env: str | None,
    ) -> list[ProviderIdentity]:
        return []

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def parse_pipeline_bytes(self, content: bytes, source: str, repo: RepoRef) -> list[PipelineBinding]:
        """Public entry point used by tests that supply raw YAML bytes."""
        return self._parse_pipeline_bytes(content, source, repo)

    def _parse_pipeline_bytes(
        self,
        content: bytes,
        source: str,
        repo: RepoRef,
    ) -> list[PipelineBinding]:
        try:
            doc = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            log.debug("Skipping invalid bitbucket-pipelines.yml at %s: %s", source, exc)
            return []

        if not isinstance(doc, dict):
            return []

        pipelines = doc.get("pipelines", {})
        if not isinstance(pipelines, dict):
            return []

        bindings: list[PipelineBinding] = []
        for section_name in ("branches", "pull-requests", "custom"):
            section = pipelines.get(section_name, {})
            if not isinstance(section, dict):
                continue
            for pattern_or_name, steps_wrapper in section.items():
                bindings.extend(
                    self._extract_from_steps(steps_wrapper, source, pattern_or_name, repo)
                )

        # pipelines.default is a list of steps directly (not a dict).
        default = pipelines.get("default")
        if default is not None:
            bindings.extend(
                self._extract_from_steps(default, source, "default", repo)
            )

        return bindings

    def _extract_from_steps(
        self,
        steps_wrapper: Any,
        source: str,
        context: str,
        repo: RepoRef,
    ) -> list[PipelineBinding]:
        """Extract deployment bindings from a list of step definitions."""
        bindings: list[PipelineBinding] = []
        if not isinstance(steps_wrapper, list):
            return bindings

        for item in steps_wrapper:
            if not isinstance(item, dict):
                continue
            step = item.get("step", item)
            if not isinstance(step, dict):
                continue
            deployment = step.get("deployment")
            if deployment:
                bindings.append(
                    PipelineBinding(
                        provider=self.id(),
                        pipeline_id=f"{source}#{context}",
                        repo=repo,
                        roles=["deploy"],
                        env=str(deployment),
                    )
                )
        return bindings
