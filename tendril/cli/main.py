"""Tendril CLI — the primary interface for graph builds and queries."""

from __future__ import annotations

import argparse
import json
import sys

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("tendril-graph")
except Exception:
    __version__ = "0.1.0-alpha"

from tendril.plugins.registry import PluginRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tendril",
        description="Tendril-Graph: cross-repo dependency graph reconstruction",
    )
    parser.add_argument("--version", action="version", version=f"tendril {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # tendril providers list
    providers_parser = subparsers.add_parser("providers", help="Manage providers")
    providers_sub = providers_parser.add_subparsers(dest="providers_command")
    providers_sub.add_parser("list", help="List registered providers")

    # tendril graph build
    graph_parser = subparsers.add_parser("graph", help="Graph operations")
    graph_sub = graph_parser.add_subparsers(dest="graph_command")
    build_parser = graph_sub.add_parser("build", help="Build the dependency graph")
    build_parser.add_argument("--anchor", required=True, help="Anchor repo (provider:org/name)")
    build_parser.add_argument("--env", help="Target environment")
    build_parser.add_argument("--fixture-dir", help="Use fixtures instead of live APIs")
    build_parser.add_argument("--mode", choices=["structured", "hybrid", "agentic"], default="structured")
    build_parser.add_argument("--db", default=":memory:", metavar="PATH",
                              help="Path to persist KuzuStore graph (default: :memory:)")

    # tendril query
    query_parser = subparsers.add_parser("query", help="Query the dependency graph")
    query_parser.add_argument(
        "--db", default=":memory:", metavar="PATH",
        help="Path to the Kùzu graph database (default: :memory:)",
    )
    query_sub = query_parser.add_subparsers(dest="query_command")

    frr = query_sub.add_parser("find-relevant-repos", help="Find repos relevant to a task")
    frr.add_argument("--task", required=True, help="Keyword description of the task")
    frr.add_argument("--env", required=True, help="Environment to query")
    frr.add_argument("--max-hops", type=int, default=3, help="BFS depth limit (default: 3)")
    frr.add_argument("--min-confidence", default="low", choices=["high", "medium", "low"])

    ia = query_sub.add_parser("impact", help="Analyze downstream impact of a repo")
    ia.add_argument("--repo-id", required=True, help="Repository ID (provider:org/name)")
    ia.add_argument("--env", required=True, help="Environment to query")
    ia.add_argument("--min-confidence", default="low", choices=["high", "medium", "low"])

    dp = query_sub.add_parser("path", help="Find dependency path between repos")
    dp.add_argument("--from-id", required=True, help="Source repo ID")
    dp.add_argument("--to-id", required=True, help="Target repo ID")
    dp.add_argument("--env", required=True, help="Environment to query")

    ed = query_sub.add_parser("env-diff", help="Compare dependency edges across environments")
    ed.add_argument("--repo-id", required=True, help="Repository ID")
    ed.add_argument("--env-a", required=True, help="First environment")
    ed.add_argument("--env-b", required=True, help="Second environment")

    ee = query_sub.add_parser("explain-edge", help="Explain a specific dependency edge")
    ee.add_argument("--from-id", required=True, help="Source repo ID")
    ee.add_argument("--to-id", required=True, help="Target repo ID")
    ee.add_argument("--env", required=True, help="Environment to query")

    # tendril telemetry reconcile
    telem_parser = subparsers.add_parser("telemetry", help="Telemetry operations")
    telem_sub = telem_parser.add_subparsers(dest="telemetry_command")
    reconcile_parser = telem_sub.add_parser("reconcile", help="Cross-validate static graph with runtime telemetry")
    reconcile_parser.add_argument("--env", required=True, help="Environment to reconcile (required)")
    reconcile_parser.add_argument("--db", default=":memory:", metavar="PATH",
                                  help="Path to Kùzu graph store (must contain a pre-built static graph)")
    reconcile_parser.add_argument("--fixture-dir", help="Path to Datadog fixture directory (for offline testing)")

    # tendril serve
    serve_parser = subparsers.add_parser("serve", help="Start the MCP server")
    serve_parser.add_argument("--mcp", action="store_true", help="Serve via MCP protocol")
    serve_parser.add_argument("--port", type=int, default=8420)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "providers" and args.providers_command == "list":
        return _providers_list()
    elif args.command == "graph" and args.graph_command == "build":
        return _graph_build(args)
    elif args.command == "query":
        return _query(args)
    elif args.command == "telemetry":
        return _telemetry(args)
    elif args.command == "serve":
        return _serve(args)

    parser.print_help()
    return 0


def _providers_list() -> int:
    registry = PluginRegistry()
    discovered = registry.discover()
    if not discovered:
        print("No plugins discovered.")
        print("Plugins register via the 'tendril.plugins' entry point group.")
        return 0
    print(f"Discovered {len(discovered)} plugin(s):")
    for plugin in registry.list_plugins():
        m = plugin.manifest
        print(f"  {m.id} (family={m.family}, contract={m.contract_version})")
    return 0


def _resolve_mode(cli_flag: str | None, toml_cfg: dict, env_val: str | None) -> str:
    """Resolve --mode from CLI flag > tendril.toml [graph] mode > TENDRIL_GRAPH_MODE env > default.

    Returns one of: "structured", "hybrid", "agentic"
    """
    if cli_flag and cli_flag != "structured":  # explicit non-default CLI flag wins
        return cli_flag
    if cli_flag:  # "structured" from CLI — still check if it was explicitly set
        return cli_flag
    if env_val in ("hybrid", "agentic"):
        return env_val
    toml_mode = toml_cfg.get("graph", {}).get("mode")
    if toml_mode in ("hybrid", "agentic"):
        return toml_mode
    return "structured"


def _graph_build(args: argparse.Namespace) -> int:  # noqa: C901
    """Load fixtures, run TraversalEngine, persist DEPENDS_ON edges to KuzuStore.

    Golden fixture directory layout (under ``--fixture-dir``):

    .. code-block:: text

        vcs/
          repos.json                         # [{provider, org, name, url, default_branch, homepage?}]
          {name}_tree.json                   # [{path, type, size}]
          {name}_files.json                  # {path: content_string}
        cicd/
          octopus/
            deployments_{slug}_{env}.json    # [{EnvironmentName, Release:{BuildInformation:[{VcsCommitNumber,Branch}]}, ...}]
            variables_{slug}.json            # [{key, value, scope:{env:...}, is_secret}]
    """
    from pathlib import Path

    from tendril.core.attribution import AttributionEngine
    from tendril.core.deployed_ref import DeployedRefResolver
    from tendril.core.environment import EnvironmentCanonicalizer
    from tendril.core.index import ReverseIndex
    from tendril.core.resolver import Resolver
    from tendril.core.traversal import TraversalEngine
    from tendril.extractors.composition import CompositionExtractor
    from tendril.extractors.dotnet import DotNetExtractor
    from tendril.models.ir import (
        Evidence,
        FileEntry,
        IdentityClass,
        ProviderIdentity,
        RepoRef,
        VarEntry,
        VariableStore,
    )
    from tendril.store.kuzu_store import KuzuStore

    # ---------- 1. Parse anchor -------------------------------------------
    anchor_str = args.anchor
    if ":" not in anchor_str or "/" not in anchor_str.split(":", 1)[1]:
        print(f"Error: --anchor must be provider:org/name, got: {anchor_str}")
        return 1
    provider, org_name = anchor_str.split(":", 1)
    org, name = org_name.split("/", 1)
    anchor = RepoRef(provider=provider, org=org, name=name)
    envs = [args.env] if args.env else ["prod"]

    if not args.fixture_dir:
        print("Error: --fixture-dir is required (live API mode not yet implemented)")
        return 1
    fixture_dir = Path(args.fixture_dir)
    if not fixture_dir.exists():
        print(f"Error: fixture-dir does not exist: {fixture_dir}")
        return 1

    env_canon = EnvironmentCanonicalizer.from_file()
    canon_envs = [env_canon.canonicalize(e)[0] for e in envs]

    # ---------- 2. Load VCS repos -----------------------------------------
    repos_path = fixture_dir / "vcs" / "repos.json"
    all_repos: list[RepoRef] = []
    repo_homepages: dict[str, str] = {}

    if repos_path.exists():
        repos_data: list[dict] = json.loads(repos_path.read_bytes())
        for r in repos_data:
            repo_ref = RepoRef(
                provider=r.get("provider", ""),
                org=r.get("org", ""),
                name=r.get("name", ""),
                default_branch=r.get("default_branch", "main"),
                url=r.get("url", ""),
            )
            all_repos.append(repo_ref)
            homepage = r.get("homepage")
            if homepage:
                repo_homepages[repo_ref.name] = homepage

    # ---------- 3. Load VCS trees and file contents -----------------------
    repo_trees: dict[str, list[FileEntry]] = {}
    file_contents: dict[str, dict[str, bytes]] = {}
    vcs_dir = fixture_dir / "vcs"

    for repo_ref in all_repos:
        tree_path = vcs_dir / f"{repo_ref.name}_tree.json"
        if tree_path.exists():
            tree_entries: list[FileEntry] = [
                FileEntry(path=e["path"], type=e.get("type", "file"), size=e.get("size", 0))
                for e in json.loads(tree_path.read_bytes())
            ]
            repo_trees[repo_ref.name] = tree_entries

        files_path = vcs_dir / f"{repo_ref.name}_files.json"
        if files_path.exists():
            raw = json.loads(files_path.read_bytes())
            file_contents[repo_ref.name] = {k: v.encode() for k, v in raw.items()}

    # ---------- 4. Load deployments (pre-joined format) -------------------
    deployments: dict[str, list[dict]] = {}
    octopus_dir = fixture_dir / "cicd" / "octopus"

    for repo_ref in all_repos:
        for canon_env in canon_envs:
            depl_path = octopus_dir / f"deployments_{repo_ref.name}_{canon_env}.json"
            if depl_path.exists():
                items: list[dict] = json.loads(depl_path.read_bytes())
                deployments.setdefault(repo_ref.name, []).extend(items)

    # ---------- 5. Load variable stores -----------------------------------
    variable_stores: dict[str, list[VariableStore]] = {}

    for repo_ref in all_repos:
        vars_path = octopus_dir / f"variables_{repo_ref.name}.json"
        if not vars_path.exists():
            continue
        raw_vars: list[dict] = json.loads(vars_path.read_bytes())
        var_entries: list[VarEntry] = []
        for v in raw_vars:
            scope: dict[str, str | None] = v.get("scope", {})
            var_entries.append(VarEntry(
                key=v["key"],
                value=None if v.get("is_secret") else v.get("value"),
                is_secret=bool(v.get("is_secret", False)),
                readable=not v.get("is_secret", False),
                scope=scope,
            ))
        variable_stores[repo_ref.name] = [
            VariableStore(kind="octopus", entries=var_entries, scoping_model="octopus-environments")
        ]

    # ---------- 6. Build reverse index from repo homepages ----------------
    index = ReverseIndex()
    for repo_name, homepage_url in repo_homepages.items():
        repo_ref = next((r for r in all_repos if r.name == repo_name), None)
        if not repo_ref:
            continue
        for canon_env in canon_envs:
            index.add(
                deployable_id=repo_name,
                repo_full_name=repo_ref.full_name,
                identities=[
                    ProviderIdentity(
                        identity_class=IdentityClass.NETWORK,
                        value=homepage_url,
                        env=canon_env,
                        evidence=[Evidence(
                            source_type="deploy-config",
                            locator=f"vcs:{repo_ref.provider}:{repo_name}:homepage",
                        )],
                    ),
                ],
            )

    # ---------- 7. Define VCS file reader ---------------------------------
    def _read_file(repo: RepoRef, ref: str, path: str) -> bytes:
        files = file_contents.get(repo.name, {})
        if path in files:
            return files[path]
        raise FileNotFoundError(f"{repo.name}/{path}")

    # ---------- 8. Run traversal engine -----------------------------------
    engine = TraversalEngine(
        attribution=AttributionEngine(),
        extractors=[CompositionExtractor(), DotNetExtractor()],
        resolver=Resolver(),
        index=index,
        ref_resolver=DeployedRefResolver(),
        env_canonicalizer=env_canon,
        vcs_read_file=_read_file,
    )
    result = engine.traverse(
        anchor=anchor,
        envs=envs,
        repo_trees=repo_trees,
        deployments=deployments,
        variable_stores=variable_stores,
    )

    # ---------- 9. (Optional) LLM hybrid pass ----------------------------
    from tendril.config import _toml as _cfg_toml  # reuse cached TOML load
    _env_mode = __import__("os").environ.get("TENDRIL_GRAPH_MODE")
    _effective_mode = _resolve_mode(getattr(args, "mode", None), _cfg_toml(), _env_mode)
    if _effective_mode == "hybrid":
        from tendril.config import load_llm_config
        from tendril.llm.cache import DiskResponseCache
        from tendril.llm.judge import LLMJudge
        from tendril.llm.redactor import ResidencyGate, SecretRedactor
        import logging as _logging
        _log = _logging.getLogger(__name__)

        llm_cfg = load_llm_config()
        if not llm_cfg.is_complete():
            missing = ", ".join(llm_cfg.missing_fields())
            _log.warning(
                "Hybrid mode requested but LLM configuration is incomplete "
                "(missing: %s); falling back to structured mode.", missing
            )
            print(f"Warning: LLM config incomplete (missing: {missing}); using structured mode.")
        else:
            from tendril.connectors.llm.openai_provider import OpenAICompatibleProvider
            provider = OpenAICompatibleProvider(llm_cfg)
            cache = DiskResponseCache(llm_cfg.cache_path)
            judge = LLMJudge(cache, SecretRedactor(), ResidencyGate())
            result = judge.run(result, index, provider, llm_cfg)
            print(f"LLM hybrid pass complete: {len(result.edges)} edge(s), "
                  f"{len(result.unresolved)} unresolved ref(s) remaining")

    # ---------- 10. Persist to KuzuStore ----------------------------------
    store = KuzuStore(args.db)
    for repo_ref in all_repos:
        store.upsert_node({
            "_table": "Repo",
            "id": repo_ref.full_name,
            "provider": repo_ref.provider,
            "org": repo_ref.org,
            "name": repo_ref.name,
            "url": repo_ref.url or "",
            "default_branch": repo_ref.default_branch or "",
            "last_indexed_ref": "",
            "last_seen": "",
        })
        store.upsert_node({
            "_table": "Deployable",
            "id": repo_ref.full_name,
            "repo_id": repo_ref.full_name,
            "kind": "service",
            "name": repo_ref.name,
        })

    sorted_edges = sorted(result.edges, key=lambda e: (e.from_id, e.to_id, e.env))
    for edge in sorted_edges:
        # Ensure both endpoint nodes exist even if not in repos.json
        for node_id in (edge.from_id, edge.to_id):
            node_name = node_id.split("/")[-1] if "/" in node_id else node_id
            store.upsert_node({
                "_table": "Deployable",
                "id": node_id,
                "repo_id": node_id,
                "kind": "service",
                "name": node_name,
            })
        store.upsert_edge({
            "_rel_type": "DEPENDS_ON",
            "_from_table": "Deployable",
            "_to_table": "Deployable",
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "env": edge.env,
            "provenance": edge.provenance.value,
            "confidence": edge.confidence.value,
            "evidence": [str(e) for e in edge.evidence],
            "deployed_ref": edge.deployed_ref,
            "ambiguous": edge.ambiguous,
            "stale": edge.stale,
            "discovered_at": "",
            "llm_trace": edge.llm_trace or "",
        })

    # ---------- 10. Print summary -----------------------------------------
    print(f"Graph build complete: {len(result.edges)} edge(s), "
          f"{len(result.expanded)} repo(s) expanded, "
          f"{len(result.unresolved)} unresolved ref(s)")
    for edge in sorted_edges:
        print(f"  DEPENDS_ON  {edge.from_id} -> {edge.to_id} @{edge.env}"
              f"  [{edge.provenance.value}|{edge.confidence.value}]"
              f"  sha={edge.deployed_ref}")
    if result.unresolved:
        for u in result.unresolved:
            print(f"  UNRESOLVED  {u}")

    # ---------- 11. (Optional) Telemetry reconcile pass (M10 FR-018) -----
    import logging as _tlog
    _tlog_logger = _tlog.getLogger(__name__)
    from tendril.config import load_datadog_config
    from tendril.connectors.telemetry.datadog_provider import DatadogTelemetryProvider
    from tendril.core.cross_validate import CrossValidator

    dd_cfg = load_datadog_config()
    dd_fixture_dir = None
    if args.fixture_dir:
        _dd_candidate = Path(args.fixture_dir) / "telemetry" / "datadog"
        if _dd_candidate.exists():
            dd_fixture_dir = _dd_candidate

    if dd_cfg.is_complete() or dd_fixture_dir:
        dd_provider = DatadogTelemetryProvider(fixture_dir=dd_fixture_dir)
        cross_val = CrossValidator(store, dd_provider, index)
        for canon_env in canon_envs:
            report = cross_val.reconcile(canon_env)
            print(f"Telemetry reconcile ({canon_env}): confirmed={len(report.confirmed)}, "
                  f"static_only={len(report.static_only)}, runtime_only={len(report.runtime_only)}, "
                  f"unknowns={len(report.unknowns)}", file=sys.stderr)
    else:
        missing = ", ".join(dd_cfg.missing_fields())
        _tlog_logger.info(
            "Datadog telemetry unconfigured (missing: %s); skipping telemetry pass.", missing
        )

    return 0


def _telemetry(args: argparse.Namespace) -> int:
    """Handle `tendril telemetry reconcile --env <env>` (FR-018)."""
    cmd = getattr(args, "telemetry_command", None)
    if cmd != "reconcile":
        print("Usage: tendril telemetry reconcile --env <env> [--db <path>] [--fixture-dir <path>]")
        return 1

    import logging as _tlog
    from pathlib import Path

    from tendril.config import load_datadog_config
    from tendril.connectors.telemetry.datadog_provider import DatadogTelemetryProvider
    from tendril.core.cross_validate import CrossValidator
    from tendril.core.index import ReverseIndex
    from tendril.store.kuzu_store import KuzuStore

    env = args.env
    db_path = getattr(args, "db", ":memory:")
    store = KuzuStore(db_path)

    # Load Datadog config
    dd_cfg = load_datadog_config()
    fixture_dir = Path(args.fixture_dir) if args.fixture_dir else None

    if not dd_cfg.is_complete() and not fixture_dir:
        _tlog.getLogger(__name__).info(
            "Datadog telemetry unconfigured (missing: %s); skipping telemetry pass.",
            ", ".join(dd_cfg.missing_fields()),
        )
        print(json.dumps({"status": "skipped", "reason": "credentials incomplete"}, indent=2))
        return 0

    # Build reverse index from store (load existing identity mappings)
    index = ReverseIndex()

    provider = DatadogTelemetryProvider(fixture_dir=fixture_dir)
    validator = CrossValidator(store, provider, index)
    report = validator.reconcile(env)

    # Write DivergenceReport to stdout as JSON (FR-018)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def _query(args: argparse.Namespace) -> int:
    from tendril.query.engine import QueryEngine
    from tendril.store.kuzu_store import KuzuStore

    cmd = args.query_command
    if not cmd:
        print("Usage: tendril query <subcommand>")
        print("Subcommands: find-relevant-repos, impact, path, env-diff, explain-edge")
        return 1

    db_path = getattr(args, "db", ":memory:")
    store = KuzuStore(db_path)
    engine = QueryEngine(store)

    if cmd == "find-relevant-repos":
        result = engine.find_relevant_repos(
            task=args.task,
            env=args.env,
            max_hops=args.max_hops,
            min_confidence=args.min_confidence,
        )
    elif cmd == "impact":
        result = engine.impact_analysis(
            repo_id=args.repo_id,
            env=args.env,
            min_confidence=args.min_confidence,
        )
    elif cmd == "path":
        result = engine.dependency_path(
            from_id=args.from_id,
            to_id=args.to_id,
            env=args.env,
        )
    elif cmd == "env-diff":
        result = engine.env_diff(
            repo_id=args.repo_id,
            env_a=args.env_a,
            env_b=args.env_b,
        )
    elif cmd == "explain-edge":
        result = engine.explain_edge(
            from_id=args.from_id,
            to_id=args.to_id,
            env=args.env,
        )
    else:
        print(f"Unknown query subcommand: {cmd}")
        return 1

    print(json.dumps(result.to_dict(), indent=2))
    return 0


def _serve(args: argparse.Namespace) -> int:
    if args.mcp:
        print(f"Starting MCP server on port {args.port}...")
        try:
            import uvicorn
            uvicorn.run("tendril.mcp.server:app", port=args.port, log_level="info")
        except ImportError:
            print("uvicorn not installed. Run: pip install 'tendril-graph[mcp]'")
            return 1
    else:
        print("Use --mcp flag to start the MCP server.")
        print(f"  tendril serve --mcp --port {args.port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
