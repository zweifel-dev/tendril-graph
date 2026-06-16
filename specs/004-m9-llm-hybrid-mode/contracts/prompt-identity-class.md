# Contract: IDENTITY_CLASS Prompt (v1)

**Contract version**: `identity_class/v1` | **Date**: 2026-06-15

*Used when the LLM judge needs to classify an identity value before grounding it in the
reverse index (FR-019). This decision type helps route proposed values to the correct
index lookup path.*

---

## Goal Description Format

```
IDENTITY_CLASS:<identity_value>
```

Example: `IDENTITY_CLASS:payment-gateway.internal.example.com`

---

## Required Inputs

| Field | Type | Description |
|-------|------|-------------|
| `identity_value` | `str` | The value to be classified |
| `evidence` | `list[EvidenceItem]` | Contextual evidence within budget (post-redaction) |
| `contract_version` | `str` | `"identity_class/v1"` — included in every request |

### `EvidenceItem` structure

```json
{
  "source_type": "string",
  "locator": "string",
  "value": "string | [REDACTED]"
}
```

---

## Required Outputs

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `class_` | `str` | Always | One of `"url"`, `"package"`, `"artifact"`, `"unknown"` |
| `reasoning` | `str` | Always | Non-empty; the LLM's stated rationale |

**Classification meanings**:

| Class | Meaning |
|-------|---------|
| `url` | A network endpoint URL, hostname, or DNS name (e.g., `https://api.example.com`, `payment-gateway.internal`) |
| `package` | A package manager artifact (NuGet, npm, Maven, etc.) (e.g., `MyOrg.PaymentGateway`, `@myorg/api-client`) |
| `artifact` | A deployment artifact name or image name (not URL, not package manager) (e.g., `landing-page-api`, `docker.io/myorg/app`) |
| `unknown` | Cannot be classified with confidence from the available evidence |

---

## System Prompt Template

```
You are a dependency graph analyst. Your task is to classify an identity value so it
can be looked up in the correct section of a provider identity index.

You are given:
1. An identity value string.
2. Contextual evidence about where this value appears (secrets replaced with [REDACTED]).

Your goal is to classify the identity value as one of: url, package, artifact, unknown.

Classification rules:
- url: The value is a URL, hostname, DNS name, or network address (with or without scheme).
- package: The value is a package manager artifact name (NuGet, npm, pip, Maven, etc.).
- artifact: The value is a deployable artifact or container image name that is not a URL
  and not a package manager artifact.
- unknown: The value does not clearly fit any of the above categories, or the evidence
  is insufficient to classify it.

Rules you MUST follow:
- class must be exactly one of: url, package, artifact, unknown.
- reasoning must be a non-empty explanation of your classification.
- Prefer specific classes (url, package, artifact) over unknown when the evidence supports it.

Respond with a JSON object only. No markdown, no prose outside the JSON.
```

**Note**: The JSON field name is `class` (not `class_`). The Python model uses `class_`
to avoid the Python keyword, but the JSON wire format uses `class`.

---

## Validation Rules (applied by `validate_response()`)

A response is **malformed** and MUST be discarded (item stays unknown, raw response logged)
if any of the following are true:

1. The response is not valid JSON or does not parse to an object.
2. `class` key is absent or its value is not one of `{"url", "package", "artifact", "unknown"}`.
3. `reasoning` is absent, null, or an empty string.

---

## Example — URL Classification

```json
{
  "class": "url",
  "reasoning": "The identity value 'payment-gateway.internal.example.com' is a DNS
                hostname without a scheme. The evidence shows it appears as the value
                of 'PaymentGatewayHost' in appsettings.json alongside port 443, confirming
                it is a network endpoint."
}
```

## Example — Package Classification

```json
{
  "class": "package",
  "reasoning": "The identity value 'MyOrg.PaymentGateway' follows the NuGet package naming
                convention (dot-separated PascalCase with an org prefix). The evidence
                includes a .csproj file with a PackageReference to this name."
}
```

## Example — Unknown

```json
{
  "class": "unknown",
  "reasoning": "The identity value 'svc-pgw-03' is a short opaque identifier. Without
                additional evidence it is not possible to determine whether this is a
                hostname, artifact name, or package reference."
}
```
