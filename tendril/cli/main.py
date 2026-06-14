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
    query_parser = subparsers.add_parser("query", help="Query the graph")
    query_sub = query_parser.add_subparsers(dest="query_command")
    query_sub.add_parser("dependency_path", help="Find dependency path between repos")
    query_sub.add_parser("impact_analysis", help="Analyze downstream impact")
    query_sub.add_parser("find_relevant_repos", help="Find repos relevant to a task")
    query_sub.add_parser("env_diff", help="Compare environments")
    query_sub.add_parser("explain_edge", help="Explain a specific edge")

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
    cmd = args.query_command
    if cmd:
        print(f"Query: {cmd}")
    print("  [Not yet implemented — M5 milestone]")
    return 0


def _serve(args: argparse.Namespace) -> int:
    if args.mcp:
        print(f"Starting MCP server on port {args.port}...")
    print("  [Not yet implemented — M5 milestone]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
