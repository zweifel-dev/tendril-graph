"""Shared IR types from SPEC.md §4.1.

These are the normalized interchange types that cross the plugin boundary.
Every connector, extractor, and core component speaks this vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


Capabilities = dict[str, bool]


class Provenance(str, Enum):
    DECLARED = "declared"
    INJECTED = "injected"
    OBSERVED = "observed"
    LLM_JUDGED = "llm-judged"


class Confidence(str, Enum):
    VERY_HIGH = "very-high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very-low"


class IdentityClass(str, Enum):
    NETWORK = "network"
    LOGICAL = "logical"
    DEPLOY = "deploy"
    ARTIFACT = "artifact"
    ASYNC = "async"
    DATA = "data"


class ConsumerRefKind(str, Enum):
    IFRAME = "iframe"
    SCRIPT = "script"
    LINK = "link"
    COMPOSITION = "composition"
    HTTP_CLIENT = "http-client"
    CONNECTION_STRING = "connection-string"
    WCF_ENDPOINT = "wcf-endpoint"
    NUGET = "nuget"
    NPM = "npm"
    ENV_VAR = "env-var"
    IMPORT = "import"
    QUEUE = "queue"
    TOPIC = "topic"
    OTHER = "other"


@dataclass(frozen=True)
class Evidence:
    source_type: str
    locator: str

    def __str__(self) -> str:
        return f"{self.source_type}:{self.locator}"


@dataclass
class RepoRef:
    provider: str
    org: str
    name: str
    default_branch: str = "main"
    url: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.provider}:{self.org}/{self.name}"


@dataclass(frozen=True)
class FileEntry:
    path: str
    type: str = "file"
    size: int = 0


@dataclass
class ConsumerRef:
    kind: ConsumerRefKind
    raw_value: str
    token_refs: list[str] = field(default_factory=list)
    env_hint: str | None = None
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class ProviderIdentity:
    identity_class: IdentityClass
    value: str
    env: str | None = None
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class TokenDecl:
    name: str
    declared_in: Evidence | None = None
    injected: bool = False


@dataclass
class VarEntry:
    key: str
    value: str | None = None
    is_secret: bool = False
    readable: bool = True
    scope: dict[str, str | None] = field(default_factory=dict)
    effective_at: str | None = None


@dataclass
class VariableStore:
    kind: str
    entries: list[VarEntry] = field(default_factory=list)
    scoping_model: str = ""


@dataclass
class PipelineBinding:
    provider: str
    pipeline_id: str
    repo: RepoRef | None = None
    roles: list[str] = field(default_factory=list)
    env: str | None = None


@dataclass
class CICDProfile:
    """Per-repo CI/CD attribution output (SPEC.md §7)."""
    repo: RepoRef | None = None
    environments: list[str] = field(default_factory=list)
    providers: list[CICDProviderEntry] = field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def build_owner(self) -> CICDProviderEntry | None:
        return next((p for p in self.providers if "build" in p.roles), None)

    @property
    def deploy_owner(self) -> CICDProviderEntry | None:
        return next((p for p in self.providers if "deploy" in p.roles), None)


@dataclass
class CICDProviderEntry:
    provider_id: str
    roles: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    evidence: list[Evidence] = field(default_factory=list)
    env_scoping_source: str = ""
    variable_stores: list[VariableStore] = field(default_factory=list)


@dataclass
class DeployedRef:
    sha: str
    branch: str = ""
    env: str = ""
    deployable_id: str = ""
    deploy_timestamp: str = ""
    source: str = ""


@dataclass
class ObservedEdge:
    from_service: str
    to_service: str
    env: str
    capability: str = ""
    last_seen: str = ""
    sample_count: int = 0


@dataclass
class ServiceEntity:
    service: str
    repo: str | None = None
    deps: list[str] = field(default_factory=list)
    team: str | None = None


@dataclass
class ResolvedValue:
    value: str | None = None
    value_set: list[str] | None = None
    def_use_chain: list[str] | None = None
    resolved: bool = False


@dataclass
class IntraRepoFacts:
    def_use: dict[str, Any] = field(default_factory=dict)
    value_sets: dict[str, list[str]] = field(default_factory=dict)
    dataflow_paths: list[dict[str, Any]] = field(default_factory=list)
    call_graph: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class AcquisitionResult:
    """Result of the value acquisition ladder (SPEC.md §9)."""
    value: str | None = None
    rung: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    resolved: bool = False
    is_secret: bool = False

    UNRESOLVED_SECRET = "__UNRESOLVED_SECRET__"
    UNRESOLVED_NO_SOURCE = "__UNRESOLVED_NO_SOURCE__"
