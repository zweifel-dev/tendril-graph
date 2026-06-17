"""Unit tests for tendril.connectors._http — resilient_get()."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from email.message import Message
from http.client import HTTPResponse
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from tendril.config import HTTPConfig
from tendril.connectors._http import HTTPResult, resilient_get


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(
    body: bytes = b'{}',
    status: int = 200,
    content_type: str = "application/json",
) -> MagicMock:
    """Create a mock that behaves like an ``http.client.HTTPResponse``."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.getheaders.return_value = [("Content-Type", content_type)]
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


_FAST_CONFIG = HTTPConfig(timeout_seconds=1, max_retries=2, backoff_base=0.0, backoff_factor=0.0)


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

class TestSuccess:
    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_simple_json_get(self, mock_urlopen: MagicMock) -> None:
        payload = {"key": "value"}
        mock_urlopen.return_value = _mock_response(json.dumps(payload).encode())

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is True
        assert result.error is None
        assert result.status == 200
        assert json.loads(result.body) == payload

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_passes_headers(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response()

        resilient_get(
            "https://example.com/api",
            headers={"Authorization": "Bearer tok"},
            config=_FAST_CONFIG,
        )

        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer tok"


# ---------------------------------------------------------------------------
# Content-Type validation
# ---------------------------------------------------------------------------

class TestContentType:
    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_html_response_returns_not_ok(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            body=b"<html>Error</html>",
            content_type="text/html",
        )

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is False
        assert "text/html" in (result.error or "")
        assert result.status == 200


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------

class TestRetry:
    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_retries_on_429(self, mock_urlopen: MagicMock) -> None:
        err_429 = urllib.error.HTTPError(
            "https://example.com", 429, "Too Many Requests", Message(), BytesIO(b""),
        )
        mock_urlopen.side_effect = [err_429, err_429, _mock_response()]

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is True
        assert mock_urlopen.call_count == 3

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_retries_on_500(self, mock_urlopen: MagicMock) -> None:
        err_500 = urllib.error.HTTPError(
            "https://example.com", 500, "Internal Server Error", Message(), BytesIO(b""),
        )
        mock_urlopen.side_effect = [err_500, _mock_response()]

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is True
        assert mock_urlopen.call_count == 2

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_exhausts_retries(self, mock_urlopen: MagicMock) -> None:
        err_503 = urllib.error.HTTPError(
            "https://example.com", 503, "Service Unavailable", Message(), BytesIO(b""),
        )
        mock_urlopen.side_effect = [err_503, err_503, err_503]

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is False
        assert result.status == 503
        assert mock_urlopen.call_count == 3

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_respects_retry_after_header(self, mock_urlopen: MagicMock) -> None:
        headers = MagicMock()
        headers.items.return_value = [("Retry-After", "0")]
        err_429 = urllib.error.HTTPError(
            "https://example.com", 429, "Too Many Requests", headers, BytesIO(b""),
        )
        mock_urlopen.side_effect = [err_429, _mock_response()]

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is True

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_no_retry_on_403(self, mock_urlopen: MagicMock) -> None:
        err_403 = urllib.error.HTTPError(
            "https://example.com", 403, "Forbidden", Message(), BytesIO(b""),
        )
        mock_urlopen.side_effect = err_403

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is False
        assert result.status == 403
        assert mock_urlopen.call_count == 1

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_no_retry_on_404(self, mock_urlopen: MagicMock) -> None:
        err_404 = urllib.error.HTTPError(
            "https://example.com", 404, "Not Found", Message(), BytesIO(b""),
        )
        mock_urlopen.side_effect = err_404

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is False
        assert result.status == 404
        assert mock_urlopen.call_count == 1


# ---------------------------------------------------------------------------
# Connection errors
# ---------------------------------------------------------------------------

class TestConnectionErrors:
    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_timeout_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = TimeoutError("timed out")

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is False
        assert "timeout" in (result.error or "").lower()
        # Should have retried
        assert mock_urlopen.call_count == _FAST_CONFIG.max_retries + 1

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_connection_refused(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is False
        assert "refused" in (result.error or "").lower()
        assert mock_urlopen.call_count == _FAST_CONFIG.max_retries + 1

    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_url_error_retries_then_recovers(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = [
            urllib.error.URLError("Connection refused"),
            _mock_response(),
        ]

        result = resilient_get("https://example.com/api", config=_FAST_CONFIG)

        assert result.ok is True
        assert mock_urlopen.call_count == 2


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

class TestDefaultConfig:
    @patch("tendril.connectors._http.urllib.request.urlopen")
    def test_uses_default_config_when_none(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response()

        result = resilient_get("https://example.com/api")

        assert result.ok is True
        # Verify timeout was passed
        _, kwargs = mock_urlopen.call_args
        assert kwargs.get("timeout") == 30  # default HTTPConfig().timeout_seconds
