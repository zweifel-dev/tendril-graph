---
description: Generate a structured audit trail report from the current PROVE session's evidence, suitable for compliance review and decision traceability.
handoffs:
  - label: Full PROVE Analysis
    agent: prove
    prompt: Continue PROVE analysis based on audit findings
  - label: Review Conclusions
    agent: prove.review
    prompt: Review the conclusions in this audit trail
---

## PROVE Audit Trail Generator

You are generating a compliance-ready audit report from the current PROVE session. This report provides full traceability of the reasoning process: what was believed, what was tested, what was observed, and how understanding changed.

## Report Structure

Generate the following structured report from the session's evidence trail:

```markdown
# PROVE Audit Report

**Session**: [problem statement]
**Date**: [current date]
**Layer**: [strategic | tactical | operational]
**Status**: [concluded | escalated]
**Confidence**: [low | medium | high]

---

## Executive Summary

[2-3 sentence summary of: what was investigated, what was concluded, and the confidence level. Written for a non-technical reviewer.]

---

## Reasoning Trace

### Cycle 1

**Prediction Phase**
- Hypotheses formed: [list with H-ids]
- Falsification criteria: [what would disprove each]
- Rationale: [why these hypotheses were chosen]

**Experiment Phase**
- Action taken: [what was done]
- Action rationale: [why THIS action over alternatives — must link to a specific hypothesis]
- Diagnostic value: [what we learn regardless of outcome]

**Observation Phase**
- Raw result: [factual observation]
- Key data points: [specific values, codes, outputs]

**Validation Phase**
- Verdicts: [H-id: Supported/Falsified/Inconclusive for each]
- Evidence cited: [specific data points from observation]
- Confidence after cycle: [level]

**Evolution Phase**
- Decision: [Build/Pivot/Sharpen/Conclude/Escalate]
- Rationale: [citing which evidence informed the decision]

[Repeat for each cycle]

---

## Hypothesis Lifecycle

| ID  | Claim | Proposed | Final Status | Evidence For | Evidence Against |
|-----|-------|----------|--------------|--------------|------------------|
[complete registry with all hypotheses and their lifecycle]

---

## Action Traceability

Every action taken during this session is traceable to a specific hypothesis:

| Cycle | Action | Testing Hypothesis | Expected Outcome | Actual Outcome | Verdict |
|-------|--------|--------------------|------------------|----------------|---------|
[one row per experiment]

---

## Governance History

| Evaluation | After Cycle | Convergence | Recommendation | Outcome |
|------------|-------------|-------------|----------------|---------|
[governance evaluations, or "No governance evaluations triggered" if session concluded before cycle 3]

---

## Conclusion

**Final Result**: [what was determined]
**Confidence**: [level] based on [N] supporting predictions across [N] cycles
**Termination Reason**: [confidence reached | governance escalation | budget exhausted]

**Evidence Chain**: [narrative summary of the critical path from initial hypotheses through the evidence that led to the conclusion]
```

## Instructions

1. Read the current session's PROVE evidence trail, hypothesis registry, and governance history
2. If no PROVE session is active or no evidence trail exists, report: "No PROVE session evidence found. Run `/prove.orchestrate` or `/prove` first."
3. Format all data into the report structure above
4. Ensure 100% of actions are traceable to hypotheses (no unexplained actions)
5. Write the executive summary LAST, after compiling all evidence
6. Use factual, neutral language suitable for compliance or audit review
