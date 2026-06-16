"""Shared IR types from SPEC.md §4.1.

These are the normalized interchange types that cross the plugin boundary.
Every connector, extractor, and core component speaks this vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    SERVICE_TAG = "service-tag"


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
    # M8 additions — layer and source locator from IntraRepoProvider
    source: str | None = None          # e.g. "web.config:LandingPageUrl" or "src/App.cs:42"
    layer: int | None = None           # 1 = config-file, 2 = AST analysis


@dataclass
class Unresolved:
    """Typed failure result from IntraRepoProvider.resolve_value() (M8).

    reason enum values: "not-found", "dynamic-value", "is-secret",
    "build-failed", "parse-error", "nuget-restore-failed",
    "workspace-load-failed",
    "llm-error", "rate-limited", "budget-exceeded",
    "grounding-failed", "unresolvable-redacted".
    """
    reason: str = "not-found"
    detail: str | None = None
    resolved: bool = False  # always False; present for isinstance discrimination


@dataclass
class IntraRepoFacts:
    def_use: dict[str, Any] = field(default_factory=dict)
    value_sets: dict[str, list[Any]] = field(default_factory=dict)
    dataflow_paths: list[dict[str, Any]] = field(default_factory=list)
    call_graph: None = None            # always None in M8 (reserved)
    # M8 additions
    partial_analysis: bool = False     # True when layer-2 failed
    truncated: bool = False            # True when response > 10 MB was trimmed
    skipped_files: list[dict[str, str]] = field(default_factory=list)


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


# ---------------------------------------------------------------------------
# M10 Telemetry cross-validation data model
# ---------------------------------------------------------------------------


@dataclass
class ResolvedObservedEdge:
    """Post-resolution form of ObservedEdge (service names resolved to repo IDs)."""
    from_id: str
    to_id: str
    env: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: Confidence = Confidence.HIGH
    deployed_ref: str | None = None


@dataclass
class ConfirmedEdge:
    """Edge present in both static graph and runtime observations."""
    from_id: str
    to_id: str
    env: str
    static_provenance: str = ""
    static_confidence: str = ""
    runtime_capabilities: list[str] = field(default_factory=list)


@dataclass
class StaticOnlyEdge:
    """Static edge with no corresponding runtime traffic."""
    from_id: str
    to_id: str
    env: str
    provenance: str = ""
    confidence: str = ""


@dataclass
class RuntimeOnlyEdge:
    """Observed edge not present in the static graph, written to store."""
    from_id: str
    to_id: str
    env: str
    confidence: str = "high"
    evidence: list[Evidence] = field(default_factory=list)
    deployed_ref: str | None = None


@dataclass
class UnknownService:
    """Unresolvable Datadog service name."""
    service: str
    env: str
    capability: str
    reason: str = "no-index-match"
    candidates: list[str] | None = None


@dataclass
class DegradationNotice:
    """Signal that a capability degraded during cross-validation.

    reason is one of: inactive, rate-limited, error, schema-error,
    truncated, store-write-error.
    """
    capability: str
    reason: str
    message: str = ""


@dataclass
class DivergenceReport:
    """Main reconciliation output from telemetry cross-validation."""
    env: str
    confirmed: list[ConfirmedEdge] = field(default_factory=list)
    static_only: list[StaticOnlyEdge] = field(default_factory=list)
    runtime_only: list[RuntimeOnlyEdge] = field(default_factory=list)
    unknowns: list[UnknownService] = field(default_factory=list)
    capabilities_probed: dict[str, bool] = field(default_factory=dict)
    metadata: list[DegradationNotice] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict.

        Evidence objects are converted to their string representation.
        """
        raw = asdict(self)
        # Walk nested structures and convert Evidence-shaped dicts to strings
        def _convert_evidence(obj: object) -> object:
            if isinstance(obj, dict):
                # Detect Evidence-shaped dicts produced by asdict()
                if set(obj.keys()) == {"source_type", "locator"}:
                    return f"{obj['source_type']}:{obj['locator']}"
                return {k: _convert_evidence(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert_evidence(item) for item in obj]
            return obj
        return _convert_evidence(raw)  # type: ignore[return-value]
