Tendril-Graph: Full Implementation Plan
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌

 Context

 M0–M4 are complete. All 68 tests pass (conformance suites for GitHub, Bitbucket DC, TeamCity, Octopus; rung 4 deploy-log
 harvesting; SC-003-exact end-to-end assertions). The spec critique is in specs/000-initial-plan/critique-plan.md.
 This document is the working plan for M5 through M10.

 Package layout: all code lives inside tendril/. Imports use from tendril.X import Y.
 Run tests: .venv/bin/python -m pytest tests/
 Install: pip install -e ".[dev]"

 ---
 Milestone Status

 ┌───────────────────────────────────────┬─────────────┬───────────────────────────────────────────────┐
 │               Milestone               │   Status    │                 Blocking Gap                  │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M0 — Scaffolding + 7 ABCs             │ ✅ COMPLETE │ —                                             │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M1 — VCS + CI/CD connectors           │ ✅ COMPLETE │ —                                             │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M2 — Attribution + deployed-ref       │ ✅ COMPLETE │ —                                             │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M3 — Extractors                       │ ✅ COMPLETE │ —                                             │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M4 — BFS → first real edge            │ ✅ COMPLETE │ —                                             │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M5 — Query layer + MCP server         │ ❌ 0%       │ Nothing in query/ or mcp/                     │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M6 — OSS hygiene                      │ ❌ 40%      │ LICENSE, golden fixtures, CI workflow         │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M7 — GitHub Actions + Octopus scoping │ ❌ 50%      │ github_actions.py, bitbucket_pipelines.py     │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M8 — Roslyn IntraRepoProvider         │ ❌ 0%       │ analyzers/roslyn/, subprocess bridge          │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M9 — LLM hybrid mode                  │ ❌ 0%       │ connectors/llm/, core/llm_judge.py            │
 ├───────────────────────────────────────┼─────────────┼───────────────────────────────────────────────┤
 │ M10 — Telemetry                       │ ❌ 0%       │ connectors/telemetry/, core/cross_validate.py │
 └───────────────────────────────────────┴─────────────┴───────────────────────────────────────────────┘

 ---
 M0–M4 What Was Done (for reference)

 M1: Created conformance subclasses in tests/conformance/{github,bitbucket_dc,teamcity,octopus}/ (not a single
 test_m1_connectors.py — one subdir per connector). Added fixture trees under tests/fixtures/conformance/vcs/ and
 tests/fixtures/conformance/cicd/teamcity/, plus three new Octopus fixtures (deployments_Projects-1_prod.json,
 release_Releases-50.json, variables_Projects-1.json). 29 new conformance tests.

 M4: Three sub-fixes applied:
 - DotNetExtractor now emits TokenDecl for URL-named config keys with literal values (e.g. LandingPageUrl →
   "landing-page-url") so appsettings.prod.json appears in edge evidence.
 - traversal.py collects declared_in from ALL matching TokenDecls (not just first) when building all_evidence.
 - DeployedRefResolver accepts an optional env_canonicalizer; TraversalEngine injects its own canonicalizer so
   "Production" (Octopus name) correctly matches canonical "prod". The resolver also no longer bails out early when
   deploy_owner is unset — it tries _resolve_from_deployments first.
 - resolver.py rung 4: _parse_kv_from_logs scans lines for KEY=VALUE (case-insensitive) and returns an
   AcquisitionResult(rung="deploy_log", ...).
 - test_end_to_end.py: test_first_depends_on_edge now asserts exact SC-003 values (from_id, to_id, env, provenance,
   confidence, deployed_ref == "abc123def456", len(evidence) >= 3, unknowns == []).
   Added test_rung4_parses_kv_from_logs.

 ---
 M5 — Query Layer + MCP Server

 Dependencies: M4 complete (Kùzu has edges to query).

 tendril/query/engine.py

 Five query operations against Kùzu. Every response must carry confidence, provenance, deployed_ref, and an explicit
 unknowns list — even if empty.

 class QueryEngine:
     def __init__(self, store: GraphStore): ...

     def find_relevant_repos(
         self, task: str, env: str, max_hops: int = 3, min_confidence: str = "low"
     ) -> QueryResult:
         # BFS from seed repos whose name/id matches task keywords.
         # Returns repos + their DEPENDS_ON edges within max_hops.
         # Include unknowns: edges with stale=True or unresolved candidates.

     def impact_analysis(
         self, repo_id: str, env: str, min_confidence: str = "low"
     ) -> QueryResult:
         # Reverse BFS: find all Deployables with a DEPENDS_ON path TO repo_id.
         # Recall-favoring: include ambiguous + low-confidence edges.
         # Cypher: MATCH (a)-[:DEPENDS_ON*1..5]->(b {id: $repo_id}) WHERE ...

     def dependency_path(
         self, from_id: str, to_id: str, env: str
     ) -> QueryResult:
         # Delegates to store.path(from_id, to_id, env).
         # Enriches result with provenance + confidence per hop.

     def env_diff(
         self, repo_id: str, env_a: str, env_b: str
     ) -> QueryResult:
         # Compare DEPENDS_ON edges for env_a vs env_b.
         # Also compare DEPLOYED_AS nodes (different SHAs between envs).
         # Cypher: two separate MATCH clauses, diff in Python.

     def explain_edge(self, from_id: str, to_id: str, env: str) -> QueryResult:
         # Return the full evidence chain for the DEPENDS_ON edge.
         # Include: provenance, confidence, deployed_ref, evidence[],
         #          resolved_via[], ambiguous flag, stale flag.
         # In M5: llm_trace is null (populated in M9).

 tendril/query/response.py — QueryResult dataclass:
 @dataclass
 class QueryResult:
     operation: str
     env: str
     results: list[dict[str, Any]]
     confidence: str          # weakest link across all results
     provenance: str          # most conservative provenance seen
     deployed_refs: dict[str, str]   # repo_id -> sha
     unknowns: list[dict[str, Any]]  # unresolved edges/repos
     metadata: dict[str, Any] = field(default_factory=dict)

 tendril/mcp/server.py + tendril/mcp/schema.py

 FastAPI app exposing the five query tools as MCP-compatible JSON endpoints. The MCP protocol wraps each tool call as
 {"tool": "find_relevant_repos", "input": {...}} and returns {"output": QueryResult}.

 # tendril/mcp/server.py
 from fastapi import FastAPI
 from tendril.query.engine import QueryEngine
 from tendril.store.kuzu_store import KuzuStore
 from tendril.mcp.schema import (
     FindRelevantReposInput, ImpactAnalysisInput,
     DependencyPathInput, EnvDiffInput, ExplainEdgeInput,
 )

 app = FastAPI(title="tendril-graph MCP", version="0.1.0-alpha")

 @app.post("/mcp/find_relevant_repos")
 async def find_relevant_repos(req: FindRelevantReposInput): ...

 @app.post("/mcp/impact_analysis")
 async def impact_analysis(req: ImpactAnalysisInput): ...

 @app.post("/mcp/dependency_path")
 async def dependency_path(req: DependencyPathInput): ...

 @app.post("/mcp/env_diff")
 async def env_diff(req: EnvDiffInput): ...

 @app.post("/mcp/explain_edge")
 async def explain_edge(req: ExplainEdgeInput): ...

 Schema models in tendril/mcp/schema.py — one Pydantic model per input/output.

 Wire up CLI

 tendril/cli/main.py _serve() stub → start uvicorn with the FastAPI app on the specified port.
 tendril/cli/main.py _query() stub → instantiate QueryEngine(KuzuStore(db_path)), call the appropriate method, print JSON.

 M5 acceptance

 tendril serve --mcp --port 8420 &
 curl -s -X POST http://localhost:8420/mcp/find_relevant_repos \
   -H 'Content-Type: application/json' \
   -d '{"task": "checkout", "env": "prod"}'
 # Returns: {results: [...], confidence: "...", unknowns: []}

 Tests: tests/test_m5_query.py — use the in-memory Kùzu store seeded from the golden fixture, assert each operation
 returns correct shape + non-empty results.

 ---
 M6 — OSS Hygiene + Public Fixtures

 Dependencies: M4 (to define what the golden fixture should produce).

 Files to create

 LICENSE — Apache-2.0 text at project root.

 .github/workflows/ci.yml — runs on push/PR to main:
 name: CI
 on: [push, pull_request]
 jobs:
   test:
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
         with: { python-version: "3.12" }
       - run: pip install -e ".[dev]"
       - run: pytest tests/ -v --tb=short

 tests/fixtures/golden/ — the synthetic 3-repo estate that any contributor can run against with no credentials. Structure:

 tests/fixtures/golden/
   vcs/
     bitbucket_dc/
       repos.json
       webforms-solution_tree.json     ← tree listing for webforms-solution
       webforms-solution_files.json    ← {path: content} for key files:
                                         home.aspx (iframe ref to {landing-page-url})
                                         appsettings.prod.json (landing-page-url = https://...)
                                         appsettings.staging.json
                                         web.config
     github/
       repos.json
       landing-page-ui_tree.json
       landing-page-ui_files.json      ← provider identity: https://d-ui.prod.example.com
       landing-page-api_tree.json
       landing-page-api_files.json
   cicd/
     teamcity/
       server.json
       build_types.json
       vcs_roots.json                  ← maps webforms-solution to TC build config
       parameters.json
     octopus/
       projects.json                   ← Projects-1 = webforms-solution
       environments.json               ← Environments-1 = prod
       deployments_Projects-1_prod.json  ← deploy 3217, sha=abc123def456
       release_Releases-1.json
       variables_Projects-1.json       ← LandingPageUrl with prod scoping
       variable_preview_Projects-1_prod.json  ← effective value = https://d-ui.prod.example.com
   expected/
     depends_on_prod.json              ← golden output edge for diff testing

 tests/integration/test_golden_fixture.py — end-to-end test using only golden fixture files, no live APIs, proves the full
  M4 acceptance criteria:
 def test_golden_first_edge():
     """Prove the spec acceptance criterion: one DEPENDS_ON@prod edge with full evidence chain."""
     # Wire up providers from golden fixtures
     # Run traversal from bitbucket-dc:acme/webforms-solution
     # Assert:
     #   edge.from_id == "bitbucket-dc:acme/webforms-solution"
     #   edge.to_id == "github:acme/landing-page-ui"
     #   edge.env == "prod"
     #   edge.provenance == Provenance.INJECTED
     #   edge.confidence == Confidence.HIGH
     #   edge.deployed_ref == "abc123def456"
     #   any("home.aspx" in str(e) for e in edge.evidence)
     #   any("appsettings.prod.json" in str(e) for e in edge.evidence)
     #   any("octopus" in str(e) for e in edge.evidence)
     #   edge.unknowns == []

 M6 acceptance

 Fresh checkout → pip install -e ".[dev]" → pytest tests/ passes all tests including
 tests/integration/test_golden_fixture.py with zero external credentials.

 ---
 M7 — GitHub Actions Connector + Full Octopus Scoping

 Dependencies: M1 (conformance base classes), M6 (golden fixture adds GitHub Actions workflow files).

 tendril/connectors/cicd/github_actions.py — GitHubActionsProvider

 Intrinsic-only connector (detects from .github/workflows/*.yml). GitHub Actions doesn't have a separate "deploy server" —
  environments are defined inline in workflow files.

 class GitHubActionsProvider(CICDProvider):
     def id(self) -> str: return "github-actions"

     def discover_for_repo(self, repo, repo_tree):
         # Detect presence of .github/workflows/*.yml
         # Parse YAML for `environment:` keys → PipelineBinding(env=name, roles=["deploy"])
         # Parse for uses: OctopusDeploy/* → flag as deploy step (chained to octopus)

     def read_variable_store(self, pipeline_or_project, env):
         # GitHub Environments variables via API (or fixture)
         # vars.* → readable; secrets.* → name only, value=None, is_secret=True

     def read_provider_identities(self, pipeline_or_project, env):
         # Extract URLs from env variable values

 Key detail: GitHub Actions' environment: blocks define deployment environments. Each workflow job with environment: prod
 contributes a PipelineBinding(env="prod", roles=["deploy"]).

 Full Octopus variable scoping in tendril/connectors/cicd/octopus.py

 The current read_variable_store() does simple env-name filtering but doesn't implement the full Octopus scope priority:
 Environment > Role > Tenant > Channel > unscoped. Implement _scope_matches(var_scope, env, role=None, tenant=None,
 channel=None) and _best_match(candidates):

 def _scope_matches(scope: dict, env: str, ...) -> bool:
     # A variable matches if: all specified scope dimensions match the query,
     # AND no dimension is explicitly set to a different value.
     # Unscoped (empty scope) always matches but at lowest priority.

 def _best_match(candidates: list[VarEntry]) -> VarEntry | None:
     # Priority: env-scoped > role-scoped > unscoped
     # Within same priority: most-specific (most scope dimensions set) wins

 tendril/connectors/cicd/bitbucket_pipelines.py — stub

 Detect bitbucket-pipelines.yml, parse deployment: step names as env names. Read Bitbucket Deployments variables via API.
 This is lower priority — a conformance-passing stub with fixture support is sufficient for M7.

 M7 acceptance

 End-to-end test using a GitHub-hosted fixture (repo with .github/workflows/deploy.yml containing environment: staging)
 produces a DEPENDS_ON@staging edge. Octopus env-scoped value correctly overrides project default when environment scope
 matches.

 ---
 M8 — Roslyn IntraRepoProvider

 Dependencies: M4 complete. M8 is independent of M5–M7.

 Architecture

 A C# CLI tool (tendril/analyzers/roslyn/TendrilRoslyn/) runs as a subprocess, exposing IntraRepoProvider over
 stdin/stdout JSON-RPC (tendril-rpc/v1). The Python side spawns it and proxies calls.

 Wire protocol — tendril-rpc/v1

 Newline-delimited JSON over stdin/stdout:
 // Request (Python → C#)
 {"id": "1", "method": "analyze", "params": {"repo_path": "/path/to/repo"}}

 // Response (C# → Python)
 {"id": "1", "result": {"def_use": {...}, "value_sets": {...}, "call_graph": {...}}}

 // Error
 {"id": "1", "error": {"code": -32603, "message": "build failed"}}

 Files to create

 tendril/plugins/subprocess_bridge.py — generic subprocess JSON-RPC client:
 class SubprocessBridge:
     def __init__(self, command: list[str]): ...
     def call(self, method: str, params: dict) -> dict: ...
     # Spawns process on first call, keeps alive, writes request, reads response line

 tendril/connectors/intra/roslyn_subprocess.py — RoslynIntraRepoProvider:
 class RoslynIntraRepoProvider(IntraRepoProvider):
     def __init__(self, roslyn_binary: str): ...
     def analyze(self, repo_path: str) -> IntraRepoFacts:
         result = self._bridge.call("analyze", {"repo_path": repo_path})
         return IntraRepoFacts(**result)
     def resolve_value(self, reference: str) -> ResolvedValue:
         result = self._bridge.call("resolve_value", {"reference": reference})
         return ResolvedValue(**result)

 tendril/analyzers/roslyn/TendrilRoslyn/ — C# project:
 - Program.cs — reads JSON-RPC from stdin, dispatches to analyzer, writes to stdout
 - Analyzer.cs — uses Microsoft.CodeAnalysis (Roslyn) to:
   - Build the solution with MSBuild
   - Walk the syntax tree to find string literal assignments, variable declarations
   - Build def-use chains for named variables
   - Produce value-sets for string concatenations
 - TendrilRoslyn.csproj — targets net8.0; references Microsoft.CodeAnalysis.CSharp (MIT licensed)

 License note: Roslyn itself is MIT; the analyzer code is Apache-2.0. This is license-clean for analyzing proprietary
 codebases.

 M8 acceptance

 Given VB.NET web.config with <add key="LandingPageUrl" value="https://d-ui.prod.example.com"/>, Roslyn resolves the value
  without hitting any acquisition ladder rung. resolve_value("LandingPageUrl") →
 ResolvedValue(value="https://d-ui.prod.example.com", resolved=True, def_use_chain=["web.config:LandingPageUrl"]).

 ---
 M9 — LLM Hybrid Mode

 Dependencies: M4 (structured traversal must exist as the fast path). M9 is independent of M5–M8.

 tendril/connectors/llm/openai_compat.py — OpenAICompatLLMProvider

 Wraps any OpenAI-compatible gateway (OpenAI, Azure OpenAI, Anthropic via gateway, Ollama):
 class OpenAICompatLLMProvider(LLMProvider):
     def __init__(self, base_url: str, model: str, api_key: str): ...
     def complete(self, req: LLMRequest) -> LLMResponse:
         # POST to {base_url}/chat/completions with temperature=0
         # Include req.evidence in the system prompt (within max_bytes budget)
         # Parse structured output if req.output_schema is set

 tendril/core/llm_judge.py — LLMJudge

 Wraps the LLM provider with:
 1. Pre-hook: Redact secret values from evidence before any model call. Apply residency gate (block if evidence contains
 PII markers).
 2. Grounded tools: Read-only tools the model can invoke — lookup_identity(value, env), get_provider_identities(repo_id),
 get_consumer_refs(repo_id). These call the reverse index, not the model's imagination.
 3. Prompt contracts: One prompt template per decision type — AMBIGUOUS_MATCH, UNRESOLVED_REF, IDENTITY_CLASS. Each
 specifies the required JSON output schema.
 4. Post-hook: For each candidate the model proposes, ground it: call reverse_index.lookup(candidate). If not found →
 downgrade to low-confidence + llm-judged provenance. Log the trace.
 5. Cache: Hash (req.goal, sorted(evidence_locators)) → response. Temperature-0 responses are deterministic so caching is
 safe.

 class LLMJudge:
     def __init__(self, provider: LLMProvider, index: ReverseIndex,
                  max_files: int = 20, max_bytes: int = 50_000): ...

     def judge_ambiguous_match(
         self, consumer_ref: ConsumerRef, candidates: list[IndexEntry], evidence: list[Evidence]
     ) -> JudgmentResult:
         # Returns: preferred candidate (grounded) or "remain-ambiguous" signal

     def judge_unresolved_ref(
         self, consumer_ref: ConsumerRef, evidence: list[Evidence]
     ) -> JudgmentResult:
         # Returns: proposed identity value (grounded) or "unresolvable"

 Hybrid mode in tendril/core/traversal.py

 Add mode: str = "structured" parameter to TraversalEngine.traverse(). In hybrid mode:
 - Run the structured fast path first (existing BFS)
 - After structured pass: collect all unresolved entries and all ambiguous=True edges
 - For each, call LLMJudge.judge_* — only if LLM provider is configured
 - Re-queue resolved/de-ambiguated candidates through the existing BFS continuation
 - Mark LLM-contributed edges with provenance=Provenance.LLM_JUDGED

 This keeps the structured path as the default and makes LLM strictly additive.

 M9 acceptance

 An ambiguous match (two providers with overlapping identity values) that results in two ambiguous=True edges in
 structured mode → in hybrid mode, the LLM judge grounds both via the reverse index, confirms both candidates are real,
 keeps ambiguous=True (does not auto-pick), logs the reasoning trace on both edges. The trace is retrievable via
 explain_edge.

 ---
 M10 — Telemetry (Datadog)

 Dependencies: M4 (static graph must exist to cross-validate against). M10 is independent of M5–M9.

 tendril/connectors/telemetry/datadog.py — DatadogTelemetryProvider

 class DatadogTelemetryProvider(TelemetryProvider):
     def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com",
                  fixture_dir: Path | None = None): ...

     def probe(self, env: str) -> Capabilities:
         # Check which Datadog products are enabled: APM, Logs, RUM
         # Return {"apm": True, "logs": False, "rum": True, ...}

     def service_dependencies(self, env: str) -> list[ObservedEdge]:
         # Datadog APM service map: GET /api/v1/service_dependencies
         # Returns ObservedEdge(from_service, to_service, env, capability="http")

     def edges_from_traces(self, env: str) -> list[ObservedEdge]:
         # DDtrace span search: aggregate caller→callee pairs

     def edges_from_logs(self, env: str) -> list[ObservedEdge]:
         # Log pattern: parse structured logs for outbound HTTP calls

     def edges_from_rum(self, env: str) -> list[ObservedEdge]:
         # RUM resources: extract XHR/fetch calls to external services

 tendril/core/cross_validate.py — CrossValidator

 Three-way reconciliation between static graph, CI/CD attribution, and runtime telemetry:

 class CrossValidator:
     def __init__(self, store: GraphStore, telemetry: TelemetryProvider): ...

     def reconcile(self, env: str) -> DivergenceReport:
         static = self._get_static_edges(env)       # DEPENDS_ON from Kùzu
         runtime = self.telemetry.service_dependencies(env)  # ObservedEdge[]

         static_set = {(e.from_id, e.to_id) for e in static}
         runtime_set = {(e.from_service, e.to_service) for e in runtime}

         return DivergenceReport(
             confirmed=static_set & runtime_set,          # static ∩ runtime
             static_only=static_set - runtime_set,        # declared but no traffic
             runtime_only=runtime_set - static_set,       # traffic but no declaration ← alert
             env=env,
         )

 runtime_only edges are the most actionable: undeclared dependencies that are actually in use, invisible to the static
 graph. These get persisted as DEPENDS_ON edges with provenance=Provenance.OBSERVED and confidence=Confidence.HIGH.

 M10 acceptance

 Given a Datadog fixture with 3 APM service edges (2 matching static graph, 1 unknown), reconcile(env="prod") returns a
 report with confirmed length 2, runtime_only length 1. The runtime-only edge is written to Kùzu with provenance=observed.

 ---
 Dependency Graph

 [M0 ✅] → [M1 ✅] → [M2 ✅] → [M3 ✅] → [M4 ✅]
                                               │
                               ┌───────────────┼────────────────┐
                               │               │                │
                            [M5]            [M6]            [M10]
                               │               │
                            [M7]            [M8]
                               │               │
                            [M9 depends on M4+M5 for judge loop]

 Recommended build order: M6 → M5 → M7 → M8 → M9 → M10

 M6 (golden fixtures) before M5 (query layer) because the query tests need the golden fixture as their seed data.

 ---
 Verification (full suite, no credentials)

 pip install -e ".[dev]"

 # M0-M4 — all 68 tests currently pass
 pytest tests/ -v

 # M6 golden fixture (add after creating tests/integration/)
 pytest tests/integration/test_golden_fixture.py -v

 # M5 query layer (add after creating query/engine.py)
 pytest tests/test_m5_query.py -v

 # MCP smoke test (manual, after M5)
 tendril serve --mcp --port 8420 &
 curl -s http://localhost:8420/mcp/find_relevant_repos \
   -H 'Content-Type: application/json' \
   -d '{"task": "checkout", "env": "prod"}' | python -m json.tool