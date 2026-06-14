"""Tendril-Graph package entry point.

The implementation lives in flat top-level packages (cli/, core/, models/, etc.)
that are all installed alongside this package. This shim exposes the package
version so that `importlib.metadata.version("tendril-graph")` works.
"""

__version__ = "0.1.0-alpha"
