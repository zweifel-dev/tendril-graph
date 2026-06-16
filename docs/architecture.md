# Tendril-Graph — Architecture

The canonical architecture diagram, committed as source (FR-20). Renders on GitHub. See `SPEC.md` for the component detail and `PRD.md` for requirements.

## Three planes, one plugin boundary

Tendril-Graph reconstructs the inter-repo dependency graph from three data planes — **source**, **build/deploy**, and (optional) **runtime** — with everything platform-specific behind the provider plugin contract (`SPEC.md §4`).

```mermaid
flowchart TB
    subgraph Providers["Providers — plugins behind the contract"]
        direction LR
        VCS["VCSProvider<br/>github · bitbucket-cloud · bitbucket-dc"]
        CICD["CICDProvider<br/>github-actions · octopus · teamcity<br/>circleci · bitbucket-pipelines"]
        TEL["TelemetryProvider — optional<br/>datadog · grafana · honeycomb · otel<br/>capability-probed"]
    end

    subgraph IntraRepo["IntraRepo Analysis — Rung 0 (capability-probed)"]
        direction TB
        IRP["IntraRepoProvider ABC<br/>roslyn · (future: jvm · python)"]
        BRIDGE["SubprocessBridge<br/>tendril-rpc/v1 JSON-RPC over stdin/stdout"]
        DOTNET["TendrilRoslyn subprocess<br/>Layer 1: web.config · appsettings*.json<br/>Layer 2: Roslyn AST · MSBuild semantic"]
        IRP -->|"spawn + call()"| BRIDGE
        BRIDGE -->|"newline-delimited JSON"| DOTNET
    end

    VCS -->|"RepoIR"| EXT["Extractor plugins<br/>dotnet · jsts · iac · composition"]
    CICD -->|"PipelineIR / VariableStore"| ATTR["CI/CD Attribution<br/>per-repo provider discovery + profile"]

    EXT -->|"consumer refs + provider identities"| RES
    ATTR -->|"which store, per env"| RES

    RES["Variable Resolution + Reverse Index + Resolver<br/>via the Value Acquisition Ladder"]
    RES <-->|"rung-0: ResolvedValue or Unresolved<br/>(skips ladder on success)"| IRP
    RES -->|"declared / injected edges<br/>confidence + evidence"| STORE["GraphStore<br/>kuzu · neo4j"]

    RES -->|"declared / injected edges<br/>confidence + evidence"| JUDGE

    subgraph HybridMode["LLM Hybrid Mode — optional / hybrid mode only"]
        direction TB
        JUDGE["LLMJudge post-processor<br/>(runs after structured pass)"]
        REDACT["SecretRedactor<br/>replace secret values with [REDACTED]"]
        GATE["ResidencyGate<br/>block on PII — email · phone · identity fields"]
        CONTRACT["PromptContract<br/>AMBIGUOUS_MATCH · UNRESOLVED_REF · IDENTITY_CLASS"]
        LLM["OpenAICompatibleProvider<br/>BYOK · any OpenAI-compatible endpoint<br/>temperature=0 · timeout-bounded"]
        GROUND["GroundingStep<br/>validate proposal vs. reverse index<br/>ungrounded → rejected"]
        JUDGE --> REDACT
        REDACT --> GATE
        GATE -->|"allowed"| CONTRACT
        CONTRACT --> LLM
        LLM -->|"raw response"| CONTRACT
        CONTRACT -->|"validated response"| GROUND
    end

    GROUND -->|"grounded llm-judged edge<br/>confidence=low · llm_trace"| STORE["GraphStore<br/>kuzu · neo4j"]
    JUDGE -.->|"unresolvable / skipped items<br/>back to unresolved list"| STORE

    subgraph CrossValidation["Telemetry Cross-Validation (M10)"]
        direction TB
        XVAL["CrossValidator<br/>three-way reconciliation per env"]
        XVAL -->|"probe capabilities"| TEL
        XVAL -->|"fetch static edges"| STORE
        XVAL -->|"resolve service name to repo via SERVICE_TAG"| RES
        XVAL -->|"runtime_only edges<br/>provenance=observed · confidence=high"| STORE
    end

    TEL -->|"observed edges<br/>APM · traces · logs · RUM"| XVAL
    XVAL -->|"DivergenceReport<br/>confirmed · static_only · runtime_only · unknowns"| QUERY

    STORE --> QUERY["Query Layer + MCP Server<br/>explain_edge surfaces llm_trace + observed provenance"]
    QUERY --> AGENTS["Coding agents<br/>find_relevant_repos · impact_analysis<br/>dependency_path · env_diff · explain_edge"]
```

## How to read it

1. **Providers (plugins)** ingest each plane. Source = repos and files. Build/deploy = pipelines and variable stores. Runtime = observed telemetry (probed for capabilities; never required).
2. **Extractors** derive each repo's *consumer references* and *provider identities*; **Attribution** discovers which CI/CD system owns each repo, per environment, and therefore which variable store resolves its tokens.
3. **IntraRepo Analysis (Rung 0)** is an optional capability-probed step that runs *before* the acquisition ladder. The `IntraRepoProvider` ABC (e.g. `RoslynIntraRepoProvider`) uses a language-specific subprocess via `SubprocessBridge` (tendril-rpc/v1 JSON-RPC over stdin/stdout) to resolve config-file and AST-level values directly within a repo. On success it returns a high-confidence `ResolvedValue` that short-circuits the ladder; on miss or failure it degrades gracefully and the acquisition ladder continues.
4. **Resolution** evaluates tokens (via the acquisition ladder), builds the global **reverse index** of provider identities, and **joins** consumer references to providers — producing per-environment `DEPENDS_ON` edges with confidence and evidence.
5. **LLM Hybrid Mode** (optional, `--mode hybrid`) is a post-processor that runs *after* the structured pass. `LLMJudge` picks up items the structured pass left unresolved or ambiguous, routes them through `SecretRedactor → ResidencyGate → PromptContract → OpenAICompatibleProvider`, then validates every proposal via `GroundingStep` before writing an edge. Ungrounded proposals are discarded. LLM-judged edges carry `provenance=llm-judged`, `confidence=low`, and a `llm_trace` reference to the persisted reasoning trace. Structured-mode edges are never modified.
6. **Telemetry Cross-Validation** (M10) runs the `CrossValidator` reconciliation pipeline per environment: probe Datadog capabilities (APM/traces/logs/RUM), fetch observed edges, resolve service names to repos via `SERVICE_TAG` identities in the reverse index, deduplicate edges (merging evidence), then compute three sets — **confirmed** (static + runtime agree), **static_only** (declared but no traffic observed), **runtime_only** (undeclared but actively communicating). Runtime-only edges are written to the graph store with `provenance=observed`, `confidence=high`, and Datadog evidence locators. Missing capabilities degrade gracefully without failing the run.
7. **GraphStore → Query/MCP** serves the result to coding agents, every answer carrying provenance (`declared` / `injected` / `observed` / `llm-judged`) and confidence. `explain_edge` surfaces the `llm_trace` reasoning for any LLM-judged edge, and `provenance=observed` for runtime-discovered edges.

## The two load-bearing ideas

- **The projection join.** An edge exists where one service's consumer reference ("I call X") matches another's provider identity ("I am reachable as Y"), scoped to an environment.
- **Index globally, traverse from the anchor.** Provider-identity indexing spans the whole configured scope (you can't know up front who provides a URL); consumer traversal is bounded to what's reachable from the anchor.
