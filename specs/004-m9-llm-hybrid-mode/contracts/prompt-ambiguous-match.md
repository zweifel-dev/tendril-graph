# Contract: AMBIGUOUS_MATCH Prompt (v1)

**Contract version**: `ambiguous_match/v1` | **Date**: 2026-06-15

*Used when the structured pass produced multiple plausible candidate identities for a single
consumer reference and cannot auto-pick among them (FR-009, FR-019).*

---

## Goal Description Format

```
AMBIGUOUS_MATCH:<consumer_ref_id>
```

Example: `AMBIGUOUS_MATCH:landing-page-api:ENV_API_BASE_URL`

---

## Required Inputs

All fields are required. The request MUST be built with these exact keys.

| Field | Type | Description |
|-------|------|-------------|
| `consumer_ref_id` | `str` | The consumer reference identifier being disambiguated |
| `candidates` | `list[CandidateInfo]` | List of candidate provider identities (2+) |
| `evidence` | `list[EvidenceItem]` | Contextual evidence within budget (post-redaction) |
| `contract_version` | `str` | `"ambiguous_match/v1"` — included in every request |

### `CandidateInfo` structure

```json
{
  "identity_id": "string",
  "indexed_name": "string",
  "identity_class": "string",
  "evidence": ["locator_string", ...]
}
```

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

The LLM response MUST be a JSON object with these exact fields.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `decision` | `str` | Always | `"keep-ambiguous"` or `"ground-to-candidate"` |
| `candidate_id` | `str \| null` | When `decision == "ground-to-candidate"` | Must match one of the input `identity_id` values |
| `reasoning` | `str` | Always | Non-empty; the LLM's stated rationale |

---

## System Prompt Template

```
You are a dependency graph analyst. Your task is to resolve an ambiguous consumer
reference to a provider identity.

You are given:
1. A consumer reference identifier.
2. A list of candidate provider identities that the consumer might be referring to.
3. Contextual evidence from the consumer's configuration and CI/CD variable stores
   (secrets have been replaced with [REDACTED]).

Your goal is to determine whether one candidate clearly matches, or whether the ambiguity
cannot be resolved with the available evidence.

Rules you MUST follow:
- If exactly one candidate is clearly the best match given the evidence, output
  decision=ground-to-candidate and set candidate_id to that candidate's identity_id.
- If multiple candidates remain plausible or the evidence is insufficient to distinguish
  them, output decision=keep-ambiguous and omit candidate_id.
- Never guess. If you are not confident, keep-ambiguous.
- reasoning must be a non-empty explanation of your decision.

Respond with a JSON object only. No markdown, no prose outside the JSON.
```

---

## Validation Rules (applied by `validate_response()`)

A response is **malformed** and MUST be discarded (item stays unknown, raw response logged)
if any of the following are true:

1. `decision` is absent or not one of `{"keep-ambiguous", "ground-to-candidate"}`.
2. `decision == "ground-to-candidate"` and `candidate_id` is absent, null, or not in the
   input candidate list.
3. `reasoning` is absent, null, or an empty string.
4. The response is not valid JSON or does not parse to an object.

---

## Example — Keep Ambiguous

```json
{
  "decision": "keep-ambiguous",
  "reasoning": "Both candidate-A and candidate-B have matching URL patterns in the evidence,
                and the environment variable value was redacted. Insufficient evidence to
                distinguish."
}
```

## Example — Ground to Candidate

```json
{
  "decision": "ground-to-candidate",
  "candidate_id": "myorg/landing-page-api",
  "reasoning": "The non-redacted evidence in appsettings.Production.json contains the hostname
                'api.landing-page.internal' which matches only candidate myorg/landing-page-api
                in the reverse index."
}
```
