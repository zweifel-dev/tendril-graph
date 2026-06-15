# MCP HTTP Endpoint Contracts

**Version**: 0.1.0-alpha
**Base path**: `/mcp`
**Content-Type**: `application/json` (all requests and responses)

All endpoints use HTTP POST. Successful responses return HTTP 200 with a `QueryResult` body. Error responses return the appropriate HTTP status code with an `ErrorResponse` body.

---

## Common Response Shape: QueryResult

```json
{
  "operation": "string",
  "env": "string",
  "results": [
    {
      "repo_id": "string",
      "confidence": "high|medium|low",
      "provenance": "declared|injected|observed|llm-judged",
      "deployed_ref": "string|null"
    }
  ],
  "confidence": "high|medium|low",
  "provenance": "declared|injected|observed|llm-judged",
  "deployed_refs": { "repo_id": "sha_string" },
  "unknowns": [
    {
      "kind": "unresolved-ref|unresolved-secret|no-source|stale-data|ambiguous-match|no-match",
      "description": "string",
      "repo_id": "string|null",
      "token": "string|null",
      "candidates": ["string"]
    }
  ],
  "metadata": {}
}
```

**Rules**:
- `deployed_refs` is always `{}` (never `null`) when no deployments exist
- `unknowns` is always `[]` (never `null`) when nothing is unresolved
- `confidence` is the weakest across all results (`high > medium > low`)
- `provenance` is the least trustworthy across all results (`declared > injected > observed > llm-judged`)

## Common Error Shape

```json
{
  "error": {
    "code": 400,
    "message": "string"
  }
}
```

| Code | Trigger |
|---|---|
| 400 | Missing required field or invalid parameter value |
| 404 | Unknown tool endpoint (e.g., `POST /mcp/unknown_tool`) |
| 500 | Unexpected server error |
| 503 | Graph store uninitialized or unreachable |

---

## POST /mcp/find_relevant_repos

Find repositories relevant to a task description.

**Request**:
```json
{
  "task": "string (required) — keyword description of the task",
  "env": "string (required) — environment to query",
  "max_hops": "integer (optional, default: 3) — BFS depth limit",
  "min_confidence": "string (optional, default: \"low\") — minimum confidence to include"
}
```

**Response** (`results` entry additional fields):
```json
{
  "repo_id": "string",
  "confidence": "high|medium|low",
  "provenance": "declared|injected|observed|llm-judged",
  "deployed_ref": "string|null",
  "hop_depth": "integer — 0 for keyword-matched seed repos"
}
```

**Data-level non-error cases** (returns 200):
- No repos match keywords → empty `results`, `unknowns[{kind: "no-match", ...}]`
- LLM not configured → structured mode only, `llm-judged` provenance never appears

---

## POST /mcp/impact_analysis

Find all repositories that depend on a given repository.

**Request**:
```json
{
  "repo_id": "string (required) — the target repository ID",
  "env": "string (required) — environment to query",
  "min_confidence": "string (optional, default: \"low\")"
}
```

**Response** (`results` entry additional fields):
```json
{
  "repo_id": "string — the dependent repo",
  "confidence": "high|medium|low",
  "provenance": "declared|injected|observed|llm-judged",
  "deployed_ref": "string|null",
  "path_to_target": ["string"] 
}
```

**Data-level non-error cases** (returns 200):
- No inbound edges → empty `results`, `unknowns[{kind: "no-match", description: "No repositories depend on {repo_id} in {env}"}]`

---

## POST /mcp/dependency_path

Find the dependency path between two repositories.

**Request**:
```json
{
  "from_id": "string (required)",
  "to_id": "string (required)",
  "env": "string (required)"
}
```

**Response** (`results` — ordered list of hops):
```json
{
  "repo_id": "string — each hop on the path",
  "confidence": "high|medium|low",
  "provenance": "declared|injected|observed|llm-judged",
  "deployed_ref": "string|null",
  "hop_index": "integer — 0-based position in path"
}
```

**Data-level non-error cases** (returns 200):
- No path exists → empty `results`, `unknowns[{kind: "no-source", description: "No path found from {from_id} to {to_id} in {env}"}]`

---

## POST /mcp/env_diff

Compare dependency edges for a repository between two environments.

**Request**:
```json
{
  "repo_id": "string (required)",
  "env_a": "string (required)",
  "env_b": "string (required)"
}
```

**Response** (`results` — one entry per changed edge):
```json
{
  "repo_id": "string — the downstream repo",
  "confidence": "high|medium|low",
  "provenance": "declared|injected|observed|llm-judged",
  "deployed_ref": "string|null",
  "diff_type": "added|removed|changed",
  "env_a_value": "string|null",
  "env_b_value": "string|null"
}
```

**Data-level non-error cases** (returns 200):
- One or both environments have no edges → valid response with empty or partial results, no unknowns unless resolution failures occurred

---

## POST /mcp/explain_edge

Return the full evidence chain for a specific dependency edge.

**Request**:
```json
{
  "from_id": "string (required)",
  "to_id": "string (required)",
  "env": "string (required)"
}
```

**Response** (`results` — single entry):
```json
{
  "repo_id": "string — the to_id repo",
  "confidence": "high|medium|low",
  "provenance": "declared|injected|observed|llm-judged",
  "deployed_ref": "string|null",
  "evidence": ["string — each evidence locator e.g. 'home.aspx:12'"],
  "ambiguous": "boolean",
  "stale": "boolean",
  "llm_trace": null
}
```

Note: `llm_trace` is always `null` in M5. It will be populated in M9 (LLM hybrid mode).

**Data-level non-error cases** (returns 200):
- Edge does not exist → empty `results`, `unknowns[{kind: "no-source", ...}]`
