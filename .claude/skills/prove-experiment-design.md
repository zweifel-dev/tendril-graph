---
name: PROVE Experimental Design
description: Techniques for designing high-diagnostic-value experiments that differentiate between competing hypotheses with maximum information gain.
pattern: prove
agent: experimenter
---

# Experimental Design Skill

This skill enhances the PROVE Experimenter agent's ability to design experiments that maximize diagnostic value — producing informative results regardless of outcome.

## Diagnostic Value Scoring

Rate every candidate experiment on three dimensions before choosing:

### 1. Differentiation (most important)

**High**: Different hypotheses predict clearly different outcomes from this action.
- "If H1, the log shows error A. If H2, the log shows error B. If H3, no error at all."

**Low**: All hypotheses would produce similar results.
- "If H1, the test fails. If H2, the test also fails. If H3, the test still fails."

**Rule**: Never run an experiment where all hypotheses predict the same outcome. This is a zero-information test.

### 2. Cost

Rate the cost of the action:

| Cost Level | Characteristics | Examples |
|------------|----------------|----------|
| **Minimal** | Read-only, instant, no side effects | Read a file, check a config, inspect logs |
| **Low** | Read-only but may take time | Run a query, profile a function, search codebase |
| **Medium** | May modify state, but reversible | Run a test suite, restart a service, change a config |
| **High** | Modifies state, hard to reverse | Deploy code, modify production data, delete resources |

**Rule**: Always prefer the lowest-cost experiment that achieves the same differentiation. Reading the source code is almost always cheaper than running it.

### 3. Signal-to-Noise

**High signal**: The result directly answers the question.
- "Decode the JWT and check the expiry timestamp" directly tests "is the token expired?"

**Low signal**: The result requires interpretation or has many possible explanations.
- "Run the full test suite and see if anything fails" doesn't isolate any specific hypothesis.

## Experiment Design Techniques

### Single-Variable Testing

Change or test exactly ONE thing per cycle. If you modify two variables simultaneously, you can't determine which one caused the observed outcome.

**Bad**: "Change the timeout AND add a retry, then test"
**Good**: "Change the timeout only, test. If inconclusive, add the retry separately."

### Elimination Design

Design experiments that eliminate hypotheses rather than confirm them:

**Confirmation-seeking** (weak): "If H1 is correct, I should see X" → seeing X is consistent with H1 but doesn't rule out H2 or H3.

**Elimination-seeking** (strong): "If I see X, it rules out H2 and H3, leaving only H1" → regardless of the outcome, you've learned something.

### Boundary Testing

When hypotheses involve thresholds or conditions:
- Test AT the boundary, not well within it
- "Does it fail at exactly 100 concurrent connections?" is more informative than "Does it work with 10?"

### Absence as Evidence

Design experiments where LACK of a result is informative:
- "If the error is NOT in the logs, the logging path is broken or the error is happening elsewhere"
- Record what you expected to find but didn't — this is data.

## Anti-Patterns to Avoid

### 1. Confirmation-Seeking Tests
Running an action because "it would confirm H1" when H2 and H3 would produce the same result. This wastes a cycle.

**Fix**: Before running, ask "what would I learn if this produces the OPPOSITE of what H1 predicts?"

### 2. Compound Experiments
Running multiple actions in one cycle ("check the logs AND restart the service AND run the tests"). If the situation changes, you don't know which action caused it.

**Fix**: One action per cycle. The 5-minute cost of an extra cycle is less than the debugging cost of a confounded result.

### 3. Shotgun Debugging
"Let me just try a bunch of things and see what sticks" — this is the opposite of hypothesis-driven. Every action should be chosen BECAUSE it tests a specific prediction.

**Fix**: If you can't articulate which hypothesis an action tests, don't run it.

### 4. Overkill Testing
Running a full integration test suite when a targeted unit check would answer the question. Broader tests have more noise and take longer.

**Fix**: What is the MINIMUM action that differentiates between hypotheses?

## Experiment Decision Matrix

When choosing between candidate experiments:

```
For each candidate action:
  1. Which hypotheses does it differentiate? → score 0-3
  2. What is the cost? → minimal (0), low (1), medium (2), high (3)
  3. How clear is the signal? → high (3), medium (2), low (1)

  Score = differentiation * 3 + signal - cost

  Choose the highest-scoring action.
```
