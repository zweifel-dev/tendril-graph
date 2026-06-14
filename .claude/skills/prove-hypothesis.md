---
name: PROVE Hypothesis Generation
description: Techniques for generating diverse, non-obvious, falsifiable hypotheses across multiple causal categories.
pattern: prove
agent: predictor
---

# Hypothesis Generation Skill

This skill enhances the PROVE Predictor agent's ability to generate high-quality, diverse competing hypotheses.

## Hypothesis Diversity Techniques

### 1. Causal Category Sweep

For any problem, generate hypotheses from at least 3 of these categories:

| Category | Template | Example |
|----------|----------|---------|
| **Configuration** | "A setting or parameter is misconfigured" | "The timeout is set to 5s but the operation needs 10s" |
| **State** | "The system is in an unexpected state" | "The cache contains stale data from before the migration" |
| **Logic** | "The code logic is incorrect for this case" | "The boundary check uses < instead of <=" |
| **Data** | "The input data doesn't match expectations" | "The user ID contains unicode characters not handled by the parser" |
| **Environment** | "The runtime environment differs from expectations" | "CI uses Node 18 but the code requires Node 20 features" |
| **Timing** | "A race condition or ordering issue" | "The event handler fires before the DOM is ready" |
| **Resource** | "A resource limit or exhaustion" | "The connection pool is exhausted under concurrent load" |
| **Dependency** | "An external dependency behaves differently" | "The API changed its response format in v3" |

**Rule**: At least one hypothesis MUST come from a different category than the most obvious explanation. If the obvious answer is "logic error," include a hypothesis from "state" or "environment."

### 2. Inversion Technique

Take the most obvious hypothesis and invert its assumption:
- Obvious: "The function is broken" → Inverted: "The function is correct but receiving wrong input"
- Obvious: "The server is slow" → Inverted: "The server is fast but the client is measuring wrong"
- Obvious: "The test is failing" → Inverted: "The test expectations are wrong, not the code"

### 3. Temporal Hypothesis

Ask "when did this start?" to generate time-based hypotheses:
- "If this broke after the last deploy, then [specific change] introduced it"
- "If this has always been broken but just discovered, then [test gap] masked it"
- "If this is intermittent, then [timing/concurrency/load] condition triggers it"

### 4. Scale Hypothesis

Ask "does this happen at all scales?" to generate scale-based hypotheses:
- "If it only fails with large inputs, then [buffer/memory/timeout] is the constraint"
- "If it only fails with specific inputs, then [validation/encoding/edge case] is the cause"
- "If it fails for all inputs, then [configuration/initialization/dependency] is broken"

## Prior Probability Assessment

Rate each hypothesis before testing:

**High** prior probability:
- Aligns with recent changes (temporal correlation)
- Matches known failure patterns in this codebase
- Symptom profile is textbook for this category of issue

**Medium** prior probability:
- Plausible but no specific evidence for or against
- Hasn't been tested but could explain the symptoms

**Low** prior probability:
- Unlikely but would explain anomalous observations
- Challenges the "obvious" explanation
- **Still worth including** — low-probability hypotheses sometimes reveal the actual root cause

## Anti-Patterns to Avoid

- **Anchoring**: Don't generate 3 variations of the same hypothesis. H2 and H3 should test fundamentally different causal mechanisms than H1.
- **Confirmation framing**: "The database is slow" is not falsifiable. "If the database is the bottleneck, the query execution plan shows a full table scan" IS falsifiable.
- **Premature narrowing**: On cycle 1, prefer breadth (hypotheses across categories) over depth (variations within one category). Narrow on subsequent cycles.
- **Ignoring the non-obvious**: If every hypothesis points to the same cause, you're not thinking broadly enough. What would a skeptic suggest?
