# Contract: UNRESOLVED_REF Prompt (v1)

**Contract version**: `unresolved_ref/v1` | **Date**: 2026-06-15

*Used when the structured pass could not resolve a consumer reference — the token's value
could not be found in any readable variable store (FR-019).*

---

## Goal Description Format

```
UNRESOLVED_REF:<consumer_ref_id>
```

Example: `UNRESOLVED_REF:webforms-solution:ENV_PAYMENT_GATEWAY_URL`

---

## Required Inputs

| Field | Type | Description |
|-------|------|-------------|
| `consumer_ref_id` | `str` | The consumer reference identifier that could not be resolved |
| `evidence` | `list[EvidenceItem]` | Contextual evidence within budget (post-redaction) |
| `contract_version` | `str` | `"unresolved_ref/v1"` — included in every request |

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
| `proposed_value` | `str \| null` | Always | The proposed identity value, or `null` if unresolvable |
| `reasoning` | `str` | Always | Non-empty; the LLM's stated rationale |

**`proposed_value`** should be a specific identity value that can be looked up in the
provider identity reverse index — typically a URL, package name, or deployable name.
If the reference is genuinely unresolvable from the available evidence, output `null`.

---

## System Prompt Template

```
You are a dependency graph analyst. Your task is to infer a provider identity value
for a consumer reference that the structured analysis system could not resolve.

You are given:
1. A consumer reference identifier (e.g., an environment variable name used in the source).
2. Contextual evidence from the consumer's configuration and CI/CD variable stores
   (secrets have been replaced with [REDACTED]).

Your goal is to propose a specific provider identity value (such as a URL, package name,
or service name) that the consumer is likely referencing, based on the evidence.

Rules you MUST follow:
- proposed_value must be a concrete value that could exist in a provider identity index
  (e.g., a URL like "https://api.example.com" or a package name like "MyOrg.PaymentGateway").
- If the evidence is insufficient to propose a specific value, output proposed_value=null.
- Do not guess beyond what the evidence supports.
- reasoning must be a non-empty explanation of your decision.
- Do not include values that were marked [REDACTED] in proposed_value; you cannot know them.

Respond with a JSON object only. No markdown, no prose outside the JSON.
```

---

## Validation Rules (applied by `validate_response()`)

A response is **malformed** and MUST be discarded (item stays unknown, raw response logged)
if any of the following are true:

1. The response is not valid JSON or does not parse to an object.
2. `proposed_value` key is absent (explicit `null` is valid and means "unresolvable").
3. `reasoning` is absent, null, or an empty string.
4. `proposed_value` is an empty string (must be a non-empty string or `null`).

---

## Example — Proposal Made

```json
{
  "proposed_value": "https://payment-gateway.internal.example.com",
  "reasoning": "The evidence includes appsettings.json with key 'PaymentGatewayBase'
                referencing 'payment-gateway.internal.example.com'. This is the only
                non-redacted URL pattern in the evidence corpus that matches the
                consumer reference name 'ENV_PAYMENT_GATEWAY_URL'."
}
```

## Example — Unresolvable

```json
{
  "proposed_value": null,
  "reasoning": "All relevant variable store entries for 'ENV_PAYMENT_GATEWAY_URL' were
                marked [REDACTED]. The source file only contains the variable name, not
                a default value. Insufficient evidence to propose a specific identity value."
}
```
