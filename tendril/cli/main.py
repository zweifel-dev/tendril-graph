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


def _graph_build(args: argparse.Namespace) -> int:
    print(f"Graph build: anchor={args.anchor}, env={args.env}, mode={args.mode}")
    if args.fixture_dir:
        print(f"  Using fixtures from: {args.fixture_dir}")
    print("  [Not yet implemented — M4 milestone]")
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
