"""FastAPI MCP server — five HTTP POST endpoints (M5-4, contracts/mcp-endpoints.md).

Start with: uvicorn tendril.mcp.server:app --port 8420
Or via CLI: tendril serve --mcp --port 8420

The graph store is initialized once at startup via the lifespan context manager
and the QueryEngine is injected into each endpoint via FastAPI Depends().
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from tendril.mcp.schema import (
    DependencyPathInput,
    EnvDiffInput,
    ExplainEdgeInput,
    FindRelevantReposInput,
    ImpactAnalysisInput,
)
from tendril.query.engine import QueryEngine
from tendril.store.kuzu_store import KuzuStore

log = logging.getLogger(__name__)

_store: KuzuStore | None = None
_engine: QueryEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _store, _engine
    db_path = os.environ.get("TENDRIL_DB_PATH", ":memory:")
    log.info("Initializing KuzuStore at %s", db_path)
    try:
        _store = KuzuStore(db_path)
        _engine = QueryEngine(_store)
    except Exception as exc:
        log.error("Failed to initialize graph store: %s", exc)
        _store = None
        _engine = None
    yield
    if _store is not None:
        _store.close()


app = FastAPI(
    title="tendril-graph MCP",
    version="0.1.0-alpha",
    lifespan=lifespan,
)


def get_engine() -> QueryEngine:
    if _engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": 503, "message": "Graph store unavailable"}},
        )
    return _engine


# ---------------------------------------------------------------------------
# GET /mcp — tool discovery manifest
# ---------------------------------------------------------------------------

@app.get("/mcp")
async def mcp_manifest() -> JSONResponse:
    """Return the MCP tool discovery manifest."""
    from tendril.mcp.schema import (
        FindRelevantReposInput,
        ImpactAnalysisInput,
        DependencyPathInput,
        EnvDiffInput,
        ExplainEdgeInput,
    )
    tools = [
        {"name": "find_relevant_repos", "schema": FindRelevantReposInput.model_json_schema()},
        {"name": "impact_analysis", "schema": ImpactAnalysisInput.model_json_schema()},
        {"name": "dependency_path", "schema": DependencyPathInput.model_json_schema()},
        {"name": "env_diff", "schema": EnvDiffInput.model_json_schema()},
        {"name": "explain_edge", "schema": ExplainEdgeInput.model_json_schema()},
    ]
    return JSONResponse({"tools": tools})


# ---------------------------------------------------------------------------
# POST /mcp/find_relevant_repos
# ---------------------------------------------------------------------------

@app.post("/mcp/find_relevant_repos")
async def find_relevant_repos(
    body: FindRelevantReposInput,
    engine: QueryEngine = Depends(get_engine),
) -> JSONResponse:
    try:
        result = engine.find_relevant_repos(
            task=body.task,
            env=body.env,
            max_hops=body.max_hops,
            min_confidence=body.min_confidence,
        )
        return JSONResponse(result.to_dict())
    except Exception as exc:
        log.exception("find_relevant_repos failed")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": 500, "message": str(exc)}},
        ) from exc


# ---------------------------------------------------------------------------
# POST /mcp/impact_analysis
# ---------------------------------------------------------------------------

@app.post("/mcp/impact_analysis")
async def impact_analysis(
    body: ImpactAnalysisInput,
    engine: QueryEngine = Depends(get_engine),
) -> JSONResponse:
    try:
        result = engine.impact_analysis(
            repo_id=body.repo_id,
            env=body.env,
            min_confidence=body.min_confidence,
        )
        return JSONResponse(result.to_dict())
    except Exception as exc:
        log.exception("impact_analysis failed")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": 500, "message": str(exc)}},
        ) from exc


# ---------------------------------------------------------------------------
# POST /mcp/dependency_path
# ---------------------------------------------------------------------------

@app.post("/mcp/dependency_path")
async def dependency_path(
    body: DependencyPathInput,
    engine: QueryEngine = Depends(get_engine),
) -> JSONResponse:
    try:
        result = engine.dependency_path(
            from_id=body.from_id,
            to_id=body.to_id,
            env=body.env,
        )
        return JSONResponse(result.to_dict())
    except Exception as exc:
        log.exception("dependency_path failed")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": 500, "message": str(exc)}},
        ) from exc


# ---------------------------------------------------------------------------
# POST /mcp/env_diff
# ---------------------------------------------------------------------------

@app.post("/mcp/env_diff")
async def env_diff(
    body: EnvDiffInput,
    engine: QueryEngine = Depends(get_engine),
) -> JSONResponse:
    try:
        result = engine.env_diff(
            repo_id=body.repo_id,
            env_a=body.env_a,
            env_b=body.env_b,
        )
        return JSONResponse(result.to_dict())
    except Exception as exc:
        log.exception("env_diff failed")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": 500, "message": str(exc)}},
        ) from exc


# ---------------------------------------------------------------------------
# POST /mcp/explain_edge
# ---------------------------------------------------------------------------

@app.post("/mcp/explain_edge")
async def explain_edge(
    body: ExplainEdgeInput,
    engine: QueryEngine = Depends(get_engine),
) -> JSONResponse:
    try:
        result = engine.explain_edge(
            from_id=body.from_id,
            to_id=body.to_id,
            env=body.env,
        )
        return JSONResponse(result.to_dict())
    except Exception as exc:
        log.exception("explain_edge failed")
        raise HTTPException(
            status_code=500,
            detail={"error": {"code": 500, "message": str(exc)}},
        ) from exc


# ---------------------------------------------------------------------------
# Custom 503 exception handler
# ---------------------------------------------------------------------------

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse as _JSONResponse


@app.exception_handler(503)
async def service_unavailable_handler(request: Any, exc: Any) -> _JSONResponse:
    return _JSONResponse(
        status_code=503,
        content={"error": {"code": 503, "message": "Graph store unavailable"}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Any, exc: RequestValidationError) -> _JSONResponse:
    return _JSONResponse(
        status_code=400,
        content={"error": {"code": 400, "message": str(exc)}},
    )
