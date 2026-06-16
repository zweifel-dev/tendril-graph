"""Conformance tests for SecretRedactor and ResidencyGate (M9 US2).

Tests:
  T013 — SecretRedactor replaces secret-keyed values and embedded secret strings
  T014 — ResidencyGate blocks on email, phone, PII field names; allows clean evidence
"""

from __future__ import annotations

import pytest

from tendril.llm.redactor import REDACTED, ResidencyGate, SecretRedactor


# ---------------------------------------------------------------------------
# T013 — SecretRedactor
# ---------------------------------------------------------------------------

class TestSecretRedactor:
    def setup_method(self) -> None:
        self.redactor = SecretRedactor()

    def test_secret_redactor_replaces_secret_values(self) -> None:
        """Pass 1: evidence item whose key matches a secret pattern is redacted."""
        evidence = [
            {"key": "API_KEY", "value": "sk-supersecret"},
            {"key": "SIDECAR_URL", "value": "https://sidecar.internal"},
        ]
        result = self.redactor.redact(evidence, known_secrets=set())
        # API_KEY matches *apikey* / *key* pattern via is_secret_key
        assert result[0]["value"] == REDACTED
        # Non-secret field is unchanged
        assert result[1]["value"] == "https://sidecar.internal"

    def test_secret_redactor_replaces_embedded_secrets(self) -> None:
        """Pass 2: a known secret value embedded inside a URL string is replaced."""
        secret_val = "tok_live_abc123"
        evidence = [
            {
                "key": "DOWNSTREAM_ENDPOINT",
                "value": f"https://api.example.com?auth={secret_val}",
            },
            {
                "key": "SERVICE_NAME",
                "value": "my-service",
            },
        ]
        result = self.redactor.redact(evidence, known_secrets={secret_val})
        assert secret_val not in result[0]["value"]
        assert REDACTED in result[0]["value"]
        # Unrelated value is untouched
        assert result[1]["value"] == "my-service"

    def test_secret_redactor_does_not_mutate_input(self) -> None:
        """Input list and dicts are never mutated."""
        evidence = [{"key": "SECRET_TOKEN", "value": "raw_secret"}]
        original_value = evidence[0]["value"]
        self.redactor.redact(evidence, known_secrets={"raw_secret"})
        assert evidence[0]["value"] == original_value

    def test_secret_redactor_empty_known_secrets(self) -> None:
        """Empty known_secrets set: only key-based pass runs."""
        evidence = [{"key": "DB_PASSWORD", "value": "hunter2"}]
        result = self.redactor.redact(evidence, known_secrets=set())
        assert result[0]["value"] == REDACTED  # DB_PASSWORD matches *password*

    def test_secret_redactor_no_secret_value_in_output(self) -> None:
        """No secret value appears anywhere in the redacted evidence."""
        secret = "ultra_secret_value"
        evidence = [
            {"key": "SECRET_TOKEN", "value": secret},
            {"key": "DESCRIPTION", "value": f"Token is {secret} and lives here"},
        ]
        result = self.redactor.redact(evidence, known_secrets={secret})
        for item in result:
            assert secret not in (item.get("value") or "")


# ---------------------------------------------------------------------------
# T014 — ResidencyGate
# ---------------------------------------------------------------------------

class TestResidencyGate:
    def setup_method(self) -> None:
        self.gate = ResidencyGate()

    def test_residency_gate_blocks_email(self) -> None:
        """Gate returns allowed=False when an email address appears in evidence."""
        evidence = [{"key": "CONTACT", "value": "deploy@example.com"}]
        result = self.gate.evaluate(evidence, goal="UNRESOLVED_REF:some-service")
        assert result.allowed is False
        assert result.reason_code == "pii-detected"
        assert result.trigger is not None

    def test_residency_gate_blocks_email_in_goal(self) -> None:
        """Gate blocks when email appears in the goal string."""
        evidence: list = []
        result = self.gate.evaluate(evidence, goal="AMBIGUOUS_MATCH:user@corp.com")
        assert result.allowed is False
        assert "email-pattern" in (result.trigger or "")

    def test_residency_gate_blocks_phone(self) -> None:
        """Gate returns allowed=False when a phone number appears in evidence."""
        evidence = [{"key": "SUPPORT_LINE", "value": "Call us at 555-867-5309"}]
        result = self.gate.evaluate(evidence, goal="UNRESOLVED_REF:support-service")
        assert result.allowed is False
        assert result.reason_code == "pii-detected"

    def test_residency_gate_blocks_pii_field_name(self) -> None:
        """Gate returns allowed=False when a PII field name appears as an evidence key."""
        evidence = [{"key": "username", "value": "jsmith"}]
        result = self.gate.evaluate(evidence, goal="IDENTITY_CLASS:some-ref")
        assert result.allowed is False
        assert "pii-field-name:username" in (result.trigger or "")

    def test_residency_gate_allows_clean(self) -> None:
        """Gate returns allowed=True when evidence and goal contain no PII."""
        evidence = [
            {"key": "SIDECAR_URL", "value": "https://sidecar.internal"},
            {"key": "BUILD_NUMBER", "value": "42"},
        ]
        result = self.gate.evaluate(evidence, goal="UNRESOLVED_REF:SIDECAR_URL")
        assert result.allowed is True
        assert result.reason_code is None
        assert result.trigger is None

    def test_residency_gate_allows_redacted_secret_field(self) -> None:
        """A secret field that was already redacted does not trigger the gate."""
        # Post-redaction: value is [REDACTED], key is 'SECRET_TOKEN'
        # Key doesn't match PII field names, so gate allows it
        evidence = [{"key": "SECRET_TOKEN", "value": REDACTED}]
        result = self.gate.evaluate(evidence, goal="UNRESOLVED_REF:SECRET_TOKEN")
        assert result.allowed is True
