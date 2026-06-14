"""Seven provider plugin ABCs — the extensibility core (SPEC.md §4).

Each ABC defines a stable, semantically versioned interface. Adding a
provider means implementing one of these; core never hardcodes a platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tendril.models.ir import (
    ConsumerRef,
    Capabilities,
    DeployedRef,
    Evidence,
    FileEntry,
    IntraRepoFacts,
    ObservedEdge,
    PipelineBinding,
    ProviderIdentity,
    RepoRef,
    ResolvedValue,
    ServiceEntity,
    TokenDecl,
    VariableStore,
)

CONTRACT_VERSION = "1.0.0-alpha"


# ---------------------------------------------------------------------------
# §4.2  VCSProvider (source plane)
# ---------------------------------------------------------------------------

class VCSProvider(ABC):
    """Read-only access to a version-control system."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def list_repos(self, scope: dict[str, Any]) -> list[RepoRef]: ...

    @abstractmethod
    def read_tree(self, repo: RepoRef, ref: str) -> list[FileEntry]: ...

    @abstractmethod
    def read_file(self, repo: RepoRef, ref: str, path: str) -> bytes: ...

    @abstractmethod
    def default_branch(self, repo: RepoRef) -> str: ...

    def list_webhooks(self, repo: RepoRef) -> list[dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# §4.3  CICDProvider (build/deploy plane)
# ---------------------------------------------------------------------------

class CICDProvider(ABC):
    """Read-only access to a CI/CD system's pipelines and variable stores."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def discover_for_repo(
        self, repo: RepoRef, repo_tree: list[FileEntry],
    ) -> list[PipelineBinding]: ...

    @abstractmethod
    def list_pipelines(self, scope: dict[str, Any]) -> list[dict[str, Any]]: ...

    @abstractmethod
    def read_variable_store(
        self, pipeline_or_project: str, env: str | None,
    ) -> VariableStore: ...

    @abstractmethod
    def read_provider_identities(
        self, pipeline_or_project: str, env: str | None,
    ) -> list[ProviderIdentity]: ...

    def read_effective_value(
        self, token: str, project: str, env: str,
    ) -> dict[str, Any] | None:
        return None

    def read_deploy_logs(self, run_id: str) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# §4.4  ExtractorPlugin (language/framework)
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    consumer_refs: list[ConsumerRef] = field(default_factory=list)
    provider_identities: list[ProviderIdentity] = field(default_factory=list)
    token_decls: list[TokenDecl] = field(default_factory=list)


class ExtractorPlugin(ABC):
    """Locate and classify consumer refs and provider identities in a repo.

    Extractors never resolve — they locate and classify only.
    Multiple extractors may match one repo; results are merged.
    """

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def matches(self, repo_tree: list[FileEntry]) -> bool: ...

    @abstractmethod
    def extract(
        self,
        repo: RepoRef,
        ref: str,
        tree: list[FileEntry],
        read_file: Any,
    ) -> ExtractionResult: ...


# ---------------------------------------------------------------------------
# §4.5  TelemetryProvider (runtime plane, optional)
# ---------------------------------------------------------------------------

class TelemetryProvider(ABC):
    """Optional runtime observability data for cross-validation."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def probe(self, env: str) -> Capabilities: ...

    def service_dependencies(self, env: str) -> list[ObservedEdge]:
        return []

    def edges_from_traces(self, env: str) -> list[ObservedEdge]:
        return []

    def edges_from_logs(self, env: str) -> list[ObservedEdge]:
        return []

    def edges_from_rum(self, env: str) -> list[ObservedEdge]:
        return []

    def service_catalog(self) -> list[ServiceEntity]:
        return []

    def deploy_events(self, env: str) -> list[dict[str, Any]]:
        return []


# ---------------------------------------------------------------------------
# §4.6  GraphStore (persistence)
# ---------------------------------------------------------------------------

class GraphStore(ABC):
    """Property-graph persistence behind which Kùzu or Neo4j sits."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def upsert_node(self, node: dict[str, Any]) -> None: ...

    @abstractmethod
    def upsert_edge(self, edge: dict[str, Any]) -> None: ...

    @abstractmethod
    def query(self, spec: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    @abstractmethod
    def neighbors(
        self,
        node_id: str,
        rel: str | None = None,
        env: str | None = None,
        min_confidence: str | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def path(
        self, from_id: str, to_id: str, env: str | None = None,
    ) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# §4.7  LLMProvider (judgment, grounded — §15)
# ---------------------------------------------------------------------------

@dataclass
class LLMRequest:
    goal: str
    evidence: list[dict[str, Any]]
    output_schema: dict[str, Any] | None = None
    tools: list[str] | None = None
    max_files: int = 20
    max_bytes: int = 50_000


@dataclass
class LLMResponse:
    content: str
    structured: dict[str, Any] | None = None
    trace_id: str = ""
    usage: dict[str, int] | None = None


class LLMProvider(ABC):
    """BYOK LLM access — gateway-agnostic, grounded, never authoritative."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def complete(self, req: LLMRequest) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# §4.8  IntraRepoProvider (dataflow facts — §6, §12)
# ---------------------------------------------------------------------------

class IntraRepoProvider(ABC):
    """Intra-repo static-analysis facts: def-use, value-sets, call graph."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def analyze(self, repo_path: str) -> IntraRepoFacts: ...

    @abstractmethod
    def resolve_value(self, reference: str) -> ResolvedValue: ...
