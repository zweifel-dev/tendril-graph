Tendril-Graph: Full Implementation Plan
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌

 Context

 M0–M10 are complete with all known gaps resolved. All 210 tests pass (175 prior M0–M9 + 35 new M10 telemetry cross-validation tests).
 Includes conformance suites for GitHub, Bitbucket DC, TeamCity, Octopus, GitHub Actions, Bitbucket Pipelines, Roslyn
 IntraRepo, and LLM provider/redactor; rung 4 deploy-log harvesting; SC-003-exact end-to-end assertions; golden
 fixture integration test; full query engine + MCP server; CLI graph build wired to TraversalEngine; M8 Roslyn
 IntraRepoProvider with SubprocessBridge; M9 LLM hybrid mode with LLMJudge post-processor, secret redaction,
 residency gate, disk response cache, and three prompt contracts; M10 Datadog telemetry cross-validation with
 CrossValidator three-way reconciliation, DatadogTelemetryProvider (APM/traces/logs/RUM), SERVICE_TAG identity
 class, FR-023 two-step resolution, evidence deduplication, secret redaction, fixture-mode zero-credential CI,
 and `tendril telemetry reconcile` CLI command. The spec critique is in
 specs/000-initial-plan/critique-plan.md.

 Package layout: all code lives inside tendril/. Imports use from tendril.X import Y.
 Run tests: .venv/bin/python -m pytest tests/
 Install: pip install -e ".[dev]"

 ---
 Milestone Status

 ┌───────────────────────────────────────┬──────────────────┬───────────────────────────────────────────────────────────────┐
 │               Milestone               │      Status      │                         Blocking Gap                         │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M0 — Scaffolding + 7 ABCs             │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M1 — VCS + CI/CD connectors           │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M2 — Attribution + deployed-ref       │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M3 — Extractors                       │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M4 — BFS → first real edge            │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M5 — Query layer + MCP server         │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M6 — OSS hygiene                      │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M7 — GitHub Actions + Octopus scoping │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M8 — Roslyn IntraRepoProvider         │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M9 — LLM hybrid mode                  │ ✅ COMPLETE      │ —                                                             │
 ├───────────────────────────────────────┼──────────────────┼───────────────────────────────────────────────────────────────┤
 │ M10 — Telemetry                       │ ✅ COMPLETE      │ —                                                             │
 └───────────────────────────────────────┴──────────────────┴───────────────────────────────────────────────────────────────┘

 ---
 M0–M7 What Was Done (for reference)

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

 M5: Created tendril/query/response.py (QueryResult + UnknownsEntry dataclasses, aggregate_confidence/provenance
 helpers), tendril/query/engine.py (QueryEngine with five BFS query methods against KuzuStore), tendril/mcp/server.py
 (FastAPI app, lifespan store init, five POST endpoints, GET /mcp discovery manifest, 503/400 handlers),
 tendril/mcp/schema.py (Pydantic v2 input models for all 5 tools). Updated tendril/cli/main.py to wire _query() to
 QueryEngine and _serve() to uvicorn. 11 new tests in tests/test_m5_query.py.

 M6: Created LICENSE (Apache-2.0), .github/workflows/ci.yml (push + PR to main; python 3.12; pip install -e "[dev]";
 pytest -v --tb=short), tests/fixtures/golden/expected/depends_on_prod.json (canonical golden edge), tests/conftest.py
 (golden_fixture_paths() fixture), tests/integration/test_golden_fixture.py (full pipeline from fixture to
 DEPENDS_ON@prod edge with exact field assertions).

 M7: Created tendril/connectors/cicd/github_actions.py (GitHubActionsProvider: discover via .github/workflows/*.yml,
 both string and object environment: forms → PipelineBinding; no-env blocks → build-only binding + note),
 tendril/connectors/cicd/bitbucket_pipelines.py (BitbucketPipelinesProvider stub: deployment: steps from all pipeline
 sections). Updated tendril/connectors/cicd/octopus.py: added _scope_matches() (4-dimension scope check with comma-
 separated value support) and _best_match() (env>role>tenant>channel>unscoped priority; tie → list of candidates for
 ambiguous=True). New conformance suites: tests/conformance/github_actions/ (6 tests) and
 tests/conformance/bitbucket_pipelines/ (3 tests). New integration test: tests/integration/test_m7_github_actions.py
 (GHA staging edge, Octopus env-scope override, exact-tie ambiguous detection). Total: 107 tests (+39).

 Gap resolutions (post-M7 review):

 M5 gap fixed — MCP 404 response body: Added @app.exception_handler(StarletteHTTPException) in
 tendril/mcp/server.py that returns {"error": {"code": 404, "message": "Not Found"}} for all unmatched routes.
 Consolidated all HTTP error handling into one handler (404/503/others) to also cover the Starlette routing layer.

 M7 gap fixed — GHA vars.* reading: GitHubActionsProvider.read_variable_store() now loads
 {fixture_dir}/vars_{env}.json (format: {vars:{K:V}, secrets:[NAME]}) producing readable VarEntry for vars and
 masked (value="[MASKED]") VarEntry for secrets. Created tests/fixtures/conformance/cicd/github_actions/vars_staging.json.

 M4 gap fixed — CLI graph build: _graph_build() in tendril/cli/main.py is fully implemented. Loads golden fixture
 layout ({fixture_dir}/vcs/repos.json, {name}_tree.json, {name}_files.json; {fixture_dir}/cicd/octopus/
 deployments_{slug}_{env}.json, variables_{slug}.json), wires TraversalEngine, persists DEPENDS_ON edges to KuzuStore.
 Added --db flag to graph build subcommand. Created tests/fixtures/golden/{vcs,cicd/octopus}/ fixture files and
 tests/integration/test_cli_graph_build.py (4 tests). Total: 111 tests (+4).

 M8: Created tendril/connectors/intra/roslyn_subprocess.py (RoslynIntraRepoProvider: IntraRepoProvider ABC impl; calls
 SubprocessBridge for "analyze" and "resolve_value" JSON-RPC methods; returns IntraRepoFacts / ResolvedValue).
 Created tendril/connectors/intra/subprocess_bridge.py (SubprocessBridge: spawns child process on first call, keeps
 alive via stdin/stdout, newline-delimited JSON-RPC protocol tendril-rpc/v1). Created C# project stubs under
 tendril/analyzers/roslyn/TendrilRoslyn/ (Program.cs, Analyzer.cs, TendrilRoslyn.csproj). Wired RoslynIntraRepoProvider
 as rung-0 in TraversalEngine. Added tests/integration/test_roslyn_bridge.py (conformance suite for the subprocess
 bridge with a Python echo-bridge fixture). Total: 137 tests (+26).

 M9: Created tendril/llm/ package (judge.py: LLMJudge post-processor; redactor.py: SecretRedactor + ResidencyGate;
 cache.py: DiskResponseCache with SHA-256 keying; grounding.py: GroundingStep against reverse index) and
 tendril/llm/contracts/ (base.py: PromptContract ABC + MalformedResponseError; ambiguous_match.py,
 unresolved_ref.py, identity_class.py: three versioned prompt contracts with Pydantic response models).
 Created tendril/connectors/llm/openai_provider.py (OpenAICompatibleProvider: LLMProvider ABC impl; base_url
 override supports Ollama, vLLM, Azure, Bedrock; temperature=0 enforced; LLMErrorKind enum).
 Created tendril/config.py (LLMConfig with env-var > TOML > default resolution; is_complete() gate).
 Extended tendril/models/ir.py (five new Unresolved.reason literals: llm-error, rate-limited, budget-exceeded,
 grounding-failed, unresolvable-redacted). Extended tendril/models/graph.py (llm_trace: str | None on DependsOn).
 Extended tendril/cli/main.py (--mode hybrid; graceful fallback when LLMConfig.is_complete() == False).
 Extended tendril/query/engine.py (explain_edge surfaces llm_trace ReasoningTrace JSON).
 Created tests/fixtures/conformance/llm/complete_responses.json (canned responses for all 3 contracts).
 Created tests/fixtures/golden/m9-hybrid/ (2-repo fixture with unresolvable ENV_SIDECAR_URL token in structured mode).
 Created tests/conformance/llm/test_llm_provider.py (15 contract conformance tests) and
 tests/conformance/llm/test_redactor.py (11 SecretRedactor + ResidencyGate tests).
 Created tests/integration/test_hybrid_mode.py (12 integration tests covering SC-001–SC-007: unknowns reduced,
 secret redaction, provenance labels, cache hit, graceful degradation, explain_edge trace, M0–M8 regression guard).
 Total: 175 tests (+38).

 M10: Created tendril/connectors/telemetry/datadog_provider.py (DatadogTelemetryProvider: TelemetryProvider ABC
 impl; fixture_dir mode; probe() with capability tracking and ProbeRequiredError enforcement;
 service_dependencies() for APM service map; edges_from_traces() with span_kind=client filtering and
 peer_service/out_host extraction; edges_from_logs() with structured JSON log parsing (peer.service, http.url
 hostname, out.host); edges_from_rum() with browser-to-API resource URL extraction; configurable lookback_hours,
 timeout_seconds, max_results with truncation metadata). Created tendril/connectors/telemetry/tendril-plugin.toml
 (plugin manifest: id=datadog, family=telemetry, capabilities apm/traces/logs/rum=true).
 Created tendril/core/cross_validate.py (CrossValidator: three-way static/runtime reconciliation engine;
 reconcile() 10-step flow: probe → fetch → resolve → deduplicate → static edges → set ops → redact → write →
 log → return DivergenceReport; _resolve_service_name() FR-023 two-step lookup: SERVICE_TAG exact match then
 NETWORK hostname-suffix scan; _fetch_static_edges() Cypher query; _write_runtime_edge() upsert with existence
 check; _deduplicate_edges() merges by (from_id, to_id, env) with evidence sorting; _redact_runtime_edges()
 applies SecretRedactor patterns; _redact_sensitive_in_string() for Bearer/Basic/api_key/token; evidence locator
 format validation per FR-021; store-write-error handling per FR-022; >10,000 edge warning per FR-026; INFO
 reconcile summary per FR-027).
 Extended tendril/models/ir.py (SERVICE_TAG = "service-tag" in IdentityClass enum; 7 new dataclasses:
 ResolvedObservedEdge, ConfirmedEdge, StaticOnlyEdge, RuntimeOnlyEdge, UnknownService, DegradationNotice,
 DivergenceReport with to_dict() serialization). Extended tendril/core/index.py (SERVICE_TAG normalization:
 strip whitespace, preserve case; SERVICE_TAG confidence: HIGH). Extended tendril/plugins/base.py
 (ProbeRequiredError exception class). Extended tendril/config.py (DatadogConfig dataclass with api_key,
 app_key, site, timeout_seconds, lookback_hours, max_results; is_complete()/missing_fields(); load_datadog_config()
 factory: DD_API_KEY/DD_APP_KEY/DD_SITE env vars > [telemetry.datadog] TOML > defaults).
 Extended tendril/cli/main.py (tendril telemetry reconcile --env <env> [--db <path>] [--fixture-dir <path>]
 subcommand with JSON stdout output; automatic telemetry reconcile at end of graph build when DD creds present or
 telemetry/datadog fixture subdir exists).
 Created 9 fixture files in tests/fixtures/conformance/telemetry/datadog/: capabilities_prod.json (all true),
 capabilities_logs_only.json, capabilities_none.json, service_dependencies_prod.json (3 APM edges),
 edges_from_traces_prod.json (2 client spans), edges_from_logs_prod.json (2 structured log entries),
 edges_from_rum_prod.json (2 browser-to-API RUM resources), service_dependencies_staging.json (2 edges),
 edges_from_logs_prod_with_pii.json (PII redaction test data).
 Created tests/conformance/telemetry/test_datadog_conformance.py (6 tests extending ConformanceTelemetryProvider).
 Created tests/unit/test_datadog_provider.py (11 unit tests: identity, probe variants, service_dependencies,
 ProbeRequiredError, edges_from_traces/logs/rum, missing fixture, config validation).
 Created tests/unit/test_cross_validator.py (9 unit tests: SC-001 reconcile, SC-005 unknown service, SC-006
 dedup/evidence sorting, FR-024 empty static graph, FR-005/017 static_only preservation, missing credentials,
 evidence redaction, PII log lines skipped, ambiguous match). Created tests/integration/test_telemetry_reconcile.py
 (9 integration tests: runtime edge store write, explain_edge observed provenance, logs-only capability, all four
 signals, find_relevant_repos with runtime edge, no-credentials fixture mode, CLI telemetry reconcile, graph build
 auto-reconcile, all-capabilities-error degradation).
 Updated docs/architecture.md (CrossValidation subgraph in Mermaid diagram; telemetry cross-validation description
 in How to read it section). Total: 210 tests (+35).

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
 M10 — Telemetry Cross-Validation (Datadog) — ✅ COMPLETE

 Dependencies: M4 (static graph), M5 (QueryEngine for US4 explain_edge integration).

 tendril/connectors/telemetry/datadog_provider.py — DatadogTelemetryProvider

 class DatadogTelemetryProvider(TelemetryProvider):
     def __init__(self, fixture_dir: Path | None = None,
                  lookback_hours: int = 24, timeout_seconds: int = 60,
                  max_results: int = 1000): ...
     def id(self) -> str: return "datadog"
     def probe(self, env: str) -> Capabilities:
         # Loads capabilities_{env}.json in fixture mode; tracks probed envs;
         # ProbeRequiredError enforced if data methods called without probe
     def service_dependencies(self, env: str) -> list[ObservedEdge]:
         # APM service map → ObservedEdge with capability="apm"
     def edges_from_traces(self, env: str) -> list[ObservedEdge]:
         # Filters span_kind=client; extracts peer_service/out_host → capability="traces"
     def edges_from_logs(self, env: str) -> list[ObservedEdge]:
         # Parses peer.service, http.url hostname, out.host → capability="logs"
     def edges_from_rum(self, env: str) -> list[ObservedEdge]:
         # Extracts browser-to-API pairs from RUM resource URLs → capability="rum"

 tendril/core/cross_validate.py — CrossValidator

 Three-way reconciliation: probe → fetch from active capabilities → resolve service names to repo_ids
 (FR-023 two-step: SERVICE_TAG exact match, then NETWORK hostname-suffix) → deduplicate edges (FR-010)
 → compute confirmed/static_only/runtime_only sets → redact evidence (FR-013) → write runtime_only
 to graph store with provenance=observed → return DivergenceReport.

 class CrossValidator:
     def __init__(self, store: GraphStore, provider: TelemetryProvider,
                  reverse_index: ReverseIndex, redactor: Any | None = None): ...
     def reconcile(self, env: str) -> DivergenceReport: ...

 Key implementation details:
 - Probe-failure → all capabilities inactive, WARNING log, continue (FR-003)
 - Per-capability error handling → DegradationNotice in metadata (FR-008)
 - Evidence locator format: datadog:{capability}:{env}:{api_path}@{iso_timestamp} (FR-021)
 - Idempotent upsert: checks for existing observed edge before writing (FR-020)
 - Store-write errors logged at ERROR, recorded in metadata, don't fail run (FR-022)
 - Secret redaction: Bearer tokens, API keys, PII patterns stripped from evidence (FR-013)

 CLI: `tendril telemetry reconcile --env <env> [--db <path>] [--fixture-dir <path>]`
 Auto-reconcile at end of `tendril graph build` when DD creds present.

 Models added to tendril/models/ir.py: SERVICE_TAG identity class, ResolvedObservedEdge, ConfirmedEdge,
 StaticOnlyEdge, RuntimeOnlyEdge, UnknownService, DegradationNotice, DivergenceReport.

 Config: DatadogConfig in tendril/config.py (DD_API_KEY/DD_APP_KEY/DD_SITE env vars > TOML > defaults).

 Tests: 6 conformance + 11 unit (provider) + 9 unit (cross-validator) + 9 integration = 35 new tests.
 All SC-001 through SC-011 pass. All 175 existing M0–M9 tests unaffected. Total: 210 tests.

 ---
 Dependency Graph

 [M0 ✅] → [M1 ✅] → [M2 ✅] → [M3 ✅] → [M4 ✅]
                                               │
                               ┌───────────────┼────────────────┐
                               │               │                │
                            [M5 ✅]         [M6 ✅]         [M10 ✅]
                               │               │
                            [M7 ✅]         [M8 ✅]
                               │               │
                            [M9 ✅ depends on M4+M5 for judge loop]

 Build order used: M6 → M5 → M7 → M8 → M9 → M10

 All milestones complete. 210 tests pass with zero credentials required.

 ---
 Verification (full suite, no credentials)

 pip install -e ".[dev]"

 # All M0–M10 — 210 tests, zero credentials required
 pytest tests/ -v

 # M10 telemetry cross-validation only
 pytest tests/unit/test_datadog_provider.py tests/unit/test_cross_validator.py \
   tests/conformance/telemetry/ tests/integration/test_telemetry_reconcile.py -v

 # CLI telemetry reconcile (fixture mode)
 tendril telemetry reconcile --env prod \
   --fixture-dir tests/fixtures/conformance/telemetry/datadog

 # MCP smoke test (manual)
 tendril serve --mcp --port 8420 &
 curl -s http://localhost:8420/mcp/find_relevant_repos \
   -H 'Content-Type: application/json' \
   -d '{"task": "checkout", "env": "prod"}' | python -m json.tool