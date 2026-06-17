# Contract: HTTP Resilience Utility

**Module**: `tendril/connectors/_http.py`

## Interface

```python
@dataclass
class HTTPResult:
    status: int
    body: bytes
    headers: dict[str, str]
    ok: bool            # True if 2xx
    error: str | None   # Human-readable error description, None on success

def resilient_get(
    url: str,
    headers: dict[str, str] | None = None,
    config: HTTPConfig | None = None,  # defaults to HTTPConfig() if None
) -> HTTPResult:
    """
    GET request with timeout, retry, and error handling.

    Behavior:
    - Timeout: urllib.request.urlopen(timeout=config.timeout_seconds)
    - Retry: up to config.max_retries on 429, 503, 5xx, and connection errors
    - Backoff: exponential (base * factor^attempt), capped at 30s
    - Retry-After: if 429 response includes Retry-After header, use it
    - Content-Type: if response is not application/json, set ok=False
    - Connection errors: URLError, TimeoutError → ok=False with error message

    Does NOT raise exceptions on HTTP errors — always returns HTTPResult.
    """
```

## Usage by Connectors

Each connector replaces its `_get()` / `_get_json()` with calls to `resilient_get()`:

```python
# Before (bitbucket_dc.py)
def _get(self, url):
    req = urllib.request.Request(url, headers=self._headers)
    return urllib.request.urlopen(req)

# After
def _get(self, url) -> HTTPResult:
    return resilient_get(url, headers=self._headers, config=self._http_config)
```

## Error Behavior

| Condition | Behavior | HTTPResult |
|---|---|---|
| 2xx JSON | Return parsed | `ok=True, error=None` |
| 2xx non-JSON | Return raw | `ok=False, error="unexpected content type: text/html"` |
| 4xx (not 429) | No retry | `ok=False, error="HTTP 403: Forbidden"` |
| 429 | Retry with Retry-After or backoff | `ok=False` after max retries |
| 5xx | Retry with backoff | `ok=False` after max retries |
| Timeout | Retry with backoff | `ok=False, error="timeout after 30s"` |
| Connection error | Retry with backoff | `ok=False, error="connection refused"` |
