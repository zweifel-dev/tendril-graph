---
description: Apply PROVE at the tactical abstraction layer — hypothesis-driven task decomposition, dependency analysis, and sequencing decisions.
handoffs:
  - label: Escalate to Strategic
    agent: prove.plan
    prompt: This needs strategic-level PROVE analysis
  - label: Drop to Operational
    agent: prove.operational
    prompt: Investigate this specific detail operationally
  - label: Full Orchestrated Pipeline
    agent: prove.orchestrate
    prompt: Run full multi-agent PROVE on this problem
---

## Task

```text
$ARGUMENTS
```

## PROVE Tactical Layer

You are applying PROVE at the **tactical abstraction layer**. This layer governs how a validated strategy gets broken into executable steps. Hypotheses are about sequencing, dependencies, approach selection, and decomposition — NOT about architecture choices (strategic) or individual tool calls (operational).

## Layer Scoping Rules

### Hypothesis Scope: ALLOWED
- Task sequencing and ordering decisions
- Dependency identification between work items
- Interface boundaries between components
- Approach selection for implementing a known strategy
- Risk assessment for specific implementation choices
- Effort estimation and feasibility of decompositions

### Hypothesis Scope: NOT ALLOWED (wrong layer)
- Architecture or technology selection decisions → use `/prove.plan`
- Individual code behavior or specific API responses → use `/prove.operational`
- Whether the overall strategy is correct → use `/prove.plan`

### Experiment Types: ALLOWED
- Dependency analysis (trace imports, interfaces, data flow)
- Interface review (check contracts between components)
- Spike tests (small proof-of-concept to test feasibility)
- Sequence modeling (trace execution order, identify blocking paths)
- Risk surface analysis (identify failure points in a plan)

### Timescale
- Cycles should resolve in **minutes to hours**
- If a cycle requires days of work, the hypothesis is too broad — decompose further

## Execution

Apply the standard PROVE cycle (Predict, Run, Observe, Validate, Evolve) with the scoping constraints above. Use a reduced default cycle budget of **6 cycles**.

For each cycle, ensure:
1. **Predict**: Hypotheses are about sequencing/dependencies, not architecture
2. **Run**: Experiments analyze structure and interfaces, not strategic alternatives
3. **Observe**: Record dependency chains, interface contracts, feasibility results
4. **Validate**: Compare against predictions about ordering and decomposition
5. **Evolve**: Refine the decomposition based on what was learned

## Meta-Layer Check

After every 3 cycles, self-assess:
- Am I reasoning at the right altitude? (Not drifting to strategic or operational)
- Is the decomposition converging toward an actionable plan?
- Should I escalate to strategic (foundational assumptions questionable) or drop to operational (need to test specific details)?

## Output

Conclude with a validated tactical plan:

```
TACTICAL PLAN:
  Approach: [validated decomposition]
  Sequence: [ordered phases with dependencies]
  Confidence: [low | medium | high]
  Key dependencies: [blocking relationships identified and tested]
  Risks: [identified through falsified hypotheses]
  Cycles: [N completed]
```
