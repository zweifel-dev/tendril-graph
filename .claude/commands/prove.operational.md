---
description: Apply PROVE at the operational abstraction layer — hypothesis-driven debugging of individual tool calls, specific code behavior, and API responses.
handoffs:
  - label: Escalate to Tactical
    agent: prove.tactical
    prompt: This needs tactical-level decomposition
  - label: Escalate to Strategic
    agent: prove.plan
    prompt: This needs strategic-level PROVE analysis
  - label: Full Orchestrated Pipeline
    agent: prove.orchestrate
    prompt: Run full multi-agent PROVE on this problem
---

## Issue

```text
$ARGUMENTS
```

## PROVE Operational Layer

You are applying PROVE at the **operational abstraction layer**. This is the most granular level — individual tool calls, specific code behavior, API responses, single test failures. Hypotheses are precise, experiments are fast, cycles are measured in seconds to minutes.

## Layer Scoping Rules

### Hypothesis Scope: ALLOWED
- Why a specific function returns a specific value
- Why a specific API call fails with a specific error
- Why a specific test case passes or fails
- What a specific code path does with specific input
- Why a specific configuration produces specific behavior

### Hypothesis Scope: NOT ALLOWED (wrong layer)
- How to sequence multiple tasks → use `/prove.tactical`
- Which technology or approach to use → use `/prove.plan`
- Whether the overall design is correct → use `/prove.plan`

### Experiment Types: ALLOWED
- Direct code execution (run the function, check the output)
- File reads (check configuration, source code, logs)
- Test runs (execute specific test cases)
- API calls (hit the endpoint, check the response)
- State inspection (check variable values, database contents, file system)

### Timescale
- Cycles should resolve in **seconds to minutes**
- If a cycle requires hours of work, the hypothesis is too broad — escalate to tactical

## Execution

Apply the standard PROVE cycle with a reduced default cycle budget of **6 cycles** and emphasis on speed:

1. **Predict**: Form narrow, precise hypotheses about specific behavior. "If X, then line N returns Y."
2. **Run**: Execute the minimum action to test. Prefer reading code/logs over running full suites.
3. **Observe**: Record exact values — status codes, return values, error messages, line numbers.
4. **Validate**: Binary comparison — did the specific prediction match the specific observation?
5. **Evolve**: If falsified, what does the specific evidence tell us about the next hypothesis?

## Meta-Layer Check

After 3 cycles:
- Am I investigating the right level? (Not a systemic issue hiding behind a symptom)
- Should I escalate to tactical (need to understand component interactions) or strategic (foundational assumption may be wrong)?

## Output

```
OPERATIONAL FINDING:
  Issue: [precise description of what was found]
  Evidence: [specific data points that confirm]
  Root cause: [if identified — precise mechanism]
  Fix: [if applicable — specific change]
  Confidence: [low | medium | high]
  Cycles: [N]
```
