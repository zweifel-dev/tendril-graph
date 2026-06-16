"""SecretRedactor and ResidencyGate for LLM hybrid mode (M9 FR-004, FR-005).

SecretRedactor — replaces secret values with [REDACTED] before any LLM
request is constructed. Handles both keyed secrets and secrets embedded
within non-secret fields (e.g. tokens in URL strings).

ResidencyGate — scans post-redacted evidence and the goal string for PII
patterns (email, phone, identity field names). Blocks the LLM call entirely
if any PII signal is found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tendril.config import is_secret_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"

_PII_FIELD_NAMES: frozenset[str] = frozenset({
    "user", "author", "owner", "email", "name", "contact",
    "username", "firstname", "lastname", "fullname",
    "phone", "mobile", "person", "identity",
})

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
_PHONE_PATTERN = re.compile(
    r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
)


# ---------------------------------------------------------------------------
# Evidence-like dict helpers
# ---------------------------------------------------------------------------

def _get_value(item: dict[str, Any]) -> str | None:
    return item.get("value") if isinstance(item, dict) else None


def _get_key(item: dict[str, Any]) -> str | None:
    return item.get("key") if isinstance(item, dict) else None


# ---------------------------------------------------------------------------
# SecretRedactor
# ---------------------------------------------------------------------------

class SecretRedactor:
    """Redact secret values from an evidence list before LLM request assembly.

    Evidence items are plain dicts with at least {"key": str, "value": str}.
    Returns a new list — never mutates the input.
    """

    def redact(
        self,
        evidence: list[dict[str, Any]],
        known_secrets: set[str],
    ) -> list[dict[str, Any]]:
        """Apply two-pass redaction.

        Pass 1: replace value with REDACTED for any item whose key matches
                the secret-key patterns (is_secret_key()).
        Pass 2: scan every evidence value and replace any occurrence of a
                known secret string with REDACTED (handles embedded tokens).
        """
        # Pass 1: key-based redaction
        result: list[dict[str, Any]] = []
        for item in evidence:
            key = _get_key(item) or ""
            if is_secret_key(key):
                item = {**item, "value": REDACTED}
            result.append(item)

        # Pass 2: value-based redaction of known secrets embedded anywhere
        if not known_secrets:
            return result

        final: list[dict[str, Any]] = []
        for item in result:
            value = _get_value(item)
            if value and isinstance(value, str):
                new_value = value
                for secret in known_secrets:
                    if secret and secret in new_value:
                        new_value = new_value.replace(secret, REDACTED)
                if new_value != value:
                    item = {**item, "value": new_value}
            final.append(item)

        return final


# ---------------------------------------------------------------------------
# ResidencyGate
# ---------------------------------------------------------------------------

@dataclass
class ResidencyGateResult:
    allowed: bool
    reason_code: str | None
    trigger: str | None


class ResidencyGate:
    """Block LLM calls when post-redacted evidence or goal contains PII.

    Scans all evidence field values AND the goal string for:
    - Email address patterns
    - Phone number patterns
    - Identity field names (key names only, case-insensitive)
    """

    def evaluate(
        self,
        post_redacted_evidence: list[dict[str, Any]],
        goal: str,
    ) -> ResidencyGateResult:
        # Collect all text to scan
        texts: list[tuple[str, str]] = []  # (text, source_label)
        texts.append((goal, "goal"))
        for item in post_redacted_evidence:
            key = _get_key(item) or ""
            value = _get_value(item)
            texts.append((key, f"evidence_key:{key}"))
            if value and isinstance(value, str):
                texts.append((value, f"evidence_value:{key}"))

        for text, label in texts:
            # Email pattern check
            if _EMAIL_PATTERN.search(text):
                return ResidencyGateResult(
                    allowed=False,
                    reason_code="pii-detected",
                    trigger=f"email-pattern in {label}",
                )
            # Phone pattern check
            if _PHONE_PATTERN.search(text):
                return ResidencyGateResult(
                    allowed=False,
                    reason_code="pii-detected",
                    trigger=f"phone-pattern in {label}",
                )

        # PII field name check (key names only)
        for item in post_redacted_evidence:
            key = (_get_key(item) or "").lower()
            if key in _PII_FIELD_NAMES:
                return ResidencyGateResult(
                    allowed=False,
                    reason_code="pii-detected",
                    trigger=f"pii-field-name:{key}",
                )

        # Goal string field-name-like token check
        goal_lower = goal.lower()
        for field_name in _PII_FIELD_NAMES:
            if re.search(r"\b" + re.escape(field_name) + r"\b", goal_lower):
                return ResidencyGateResult(
                    allowed=False,
                    reason_code="pii-detected",
                    trigger=f"pii-field-name-in-goal:{field_name}",
                )

        return ResidencyGateResult(allowed=True, reason_code=None, trigger=None)
