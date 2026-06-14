"""Graph node and edge types matching SPEC.md §2 domain model.

These are the types that get persisted to the GraphStore. They map 1:1
to the Kùzu/Neo4j schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tendril.models.ir import Confidence, Evidence, IdentityClass, Provenance


# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------

@dataclass
class Repo:
    id: str
    provider: str
    org: str
    name: str
    url: str = ""
    default_branch: str = "main"
    last_indexed_ref: str = ""
    last_seen: str = ""


@dataclass
class Deployable:
    id: str
    repo_id: str
    kind: str = "web"
    name: str = ""


@dataclass
class Environment:
    id: str
    name: str
    canonical_name: str = ""
    provenance: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class Endpoint:
    id: str
    scheme: str = ""
    host: str = ""
    port: int | None = None
    path_base: str = ""
    env: str = ""

    @property
    def url(self) -> str:
        port_str = f":{self.port}" if self.port else ""
        return f"{self.scheme}://{self.host}{port_str}{self.path_base}"


@dataclass
class ServiceIdentity:
    """Canonical service identity with aliases across identity classes (§3)."""
    id: str
    canonical_value: str
    identity_class: IdentityClass = IdentityClass.NETWORK
    aliases: list[str] = field(default_factory=list)
    env: str | None = None


@dataclass
class ConfigVar:
    id: str
    name: str
    declared_in: str = ""
    injected: bool = False


@dataclass
class DeployedRefNode:
    id: str
    sha: str
    branch: str = ""
    env: str = ""
    deployable_id: str = ""
    deploy_timestamp: str = ""
    source: str = ""


@dataclass
class Pipeline:
    id: str
    provider: str
    pipeline_id: str = ""
    name: str = ""


@dataclass
class CICDProviderNode:
    id: str
    system: str
    roles: list[str] = field(default_factory=list)


@dataclass
class VariableStoreNode:
    id: str
    kind: str
    readable: bool = True
    scopes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Edge types — all environment-scoped, carry provenance + confidence + evidence
# ---------------------------------------------------------------------------

@dataclass
class EdgeBase:
    from_id: str
    to_id: str
    env: str = ""
    provenance: Provenance = Provenance.DECLARED
    confidence: Confidence = Confidence.MEDIUM
    evidence: list[Evidence] = field(default_factory=list)
    discovered_at: str = ""
    deployed_ref: str = ""
    stale: bool = False

    @property
    def edge_type(self) -> str:
        return self.__class__.__name__


@dataclass
class DependsOn(EdgeBase):
    """Deployable —DEPENDS_ON→ Deployable @env. The primary query edge."""
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)
    resolved_via: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)


@dataclass
class Produces(EdgeBase):
    """Repo —PRODUCES→ Deployable."""
    pass


@dataclass
class Exposes(EdgeBase):
    """Deployable —EXPOSES→ Endpoint @env (provider projection)."""
    pass


@dataclass
class Consumes(EdgeBase):
    """Deployable —CONSUMES→ Endpoint @env (consumer projection)."""
    pass


@dataclass
class ResolvesTo(EdgeBase):
    """Endpoint —RESOLVES_TO→ Deployable @env (the join result)."""
    pass


@dataclass
class BuiltBy(EdgeBase):
    """Repo —BUILT_BY→ CICDProvider."""
    pass


@dataclass
class DeployedBy(EdgeBase):
    """Repo —DEPLOYED_BY→ CICDProvider @env."""
    pass


@dataclass
class ResolvesVarsFrom(EdgeBase):
    """CICDProvider —RESOLVES_VARS_FROM→ VariableStore."""
    pass


@dataclass
class Builds(EdgeBase):
    """Pipeline —BUILDS→ Repo."""
    pass


@dataclass
class Deploys(EdgeBase):
    """Pipeline —DEPLOYS→ Deployable @env."""
    pass


@dataclass
class InjectedInto(EdgeBase):
    """ConfigVar —INJECTED_INTO→ Deployable @env."""
    pass


@dataclass
class DeployedAs(EdgeBase):
    """Deployable —DEPLOYED_AS→ DeployedRefNode @env."""
    pass
