"""Shared HTTP resilience utility for Tendril connectors.

Provides ``resilient_get()`` — a GET wrapper with configurable timeout,
exponential-backoff retry, Retry-After header support, and Content-Type
validation.  Used by all VCS and CI/CD connectors in live mode.

Never raises on HTTP errors; always returns an ``HTTPResult``.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from tendril.config import HTTPConfig

logger = logging.getLogger(__name__)

_MAX_BACKOFF = 30.0  # cap backoff at 30 seconds


@dataclass
class HTTPResult:
    """Structured result from ``resilient_get()``."""
    status: int = 0
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    ok: bool = False
    error: str | None = None


def resilient_get(
    url: str,
    headers: dict[str, str] | None = None,
    config: HTTPConfig | None = None,
) -> HTTPResult:
    """GET *url* with timeout, retry, and error handling.

    Retry policy:
    - Retries on 429, 503, and any 5xx status, plus connection/timeout errors.
    - Exponential backoff: ``base * factor ** attempt``, capped at 30 s.
    - Respects ``Retry-After`` header on 429 responses.
    - Non-retryable 4xx returns immediately.

    Content-Type validation:
    - If the response body is not ``application/json``, ``ok`` is ``False``
      and ``error`` describes the unexpected type.

    Never raises — always returns an ``HTTPResult``.
    """
    if config is None:
        config = HTTPConfig()

    last_result = HTTPResult()

    for attempt in range(config.max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
                status = resp.status
                body = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.getheaders()}
                content_type = resp_headers.get("content-type", "")

                if 200 <= status < 300:
                    if "application/json" in content_type:
                        return HTTPResult(
                            status=status,
                            body=body,
                            headers=resp_headers,
                            ok=True,
                            error=None,
                        )
                    else:
                        return HTTPResult(
                            status=status,
                            body=body,
                            headers=resp_headers,
                            ok=False,
                            error=f"unexpected content type: {content_type}",
                        )

                # Should not normally reach here (urlopen raises on non-2xx)
                last_result = HTTPResult(
                    status=status,
                    body=body,
                    headers=resp_headers,
                    ok=False,
                    error=f"HTTP {status}",
                )

        except urllib.error.HTTPError as exc:
            status = exc.code
            resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
            body = b""
            try:
                body = exc.read()
            except Exception:
                pass

            last_result = HTTPResult(
                status=status,
                body=body,
                headers=resp_headers,
                ok=False,
                error=f"HTTP {status}: {exc.reason}",
            )

            # Retryable statuses: 429, 503, 5xx
            if status == 429 or status == 503 or status >= 500:
                if attempt < config.max_retries:
                    delay = _backoff_delay(attempt, config, resp_headers)
                    logger.debug(
                        "Retrying %s (attempt %d/%d, status %d, delay %.1fs)",
                        url, attempt + 1, config.max_retries, status, delay,
                    )
                    time.sleep(delay)
                    continue
            # Non-retryable 4xx
            return last_result

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error_msg = str(exc)
            if isinstance(exc, TimeoutError) or "timed out" in error_msg.lower():
                error_msg = f"timeout after {config.timeout_seconds}s"
            elif "refused" in error_msg.lower():
                error_msg = "connection refused"

            last_result = HTTPResult(
                status=0,
                body=b"",
                headers={},
                ok=False,
                error=error_msg,
            )

            if attempt < config.max_retries:
                delay = _backoff_delay(attempt, config, {})
                logger.debug(
                    "Retrying %s (attempt %d/%d, error: %s, delay %.1fs)",
                    url, attempt + 1, config.max_retries, error_msg, delay,
                )
                time.sleep(delay)
                continue

    return last_result


def _backoff_delay(
    attempt: int,
    config: HTTPConfig,
    headers: dict[str, str],
) -> float:
    """Compute retry delay, respecting Retry-After if present."""
    retry_after = headers.get("retry-after", "")
    if retry_after:
        try:
            return min(float(retry_after), _MAX_BACKOFF)
        except ValueError:
            pass
    return min(config.backoff_base * (config.backoff_factor ** attempt), _MAX_BACKOFF)
