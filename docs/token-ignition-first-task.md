# Token-Ignition First Evolution Task

## Host

Token-Ignition backend evaluator.

Repository:

```text
https://github.com/Protocol-zero-0/token-ignition-backend
```

Local target path after checkout:

```text
/home/ubuntu/token-ignition-backend
```

Evolution kernel project path:

```text
/home/ubuntu/evolution-kernel
```

## Mission

Use the least practical amount of code to improve the backend evaluator's ability to identify genuinely high-potential AI-native builders.

The evaluator should detect real self-evolution ability, not polished storytelling, prompt wrapping, or unverifiable demos.

## Primary Objective

Maximize talent detection quality under strict complexity and reproducibility constraints.

This is a multi-objective task:

- improve true positive detection for strong self-evolving systems
- reduce false positives for fake or unverifiable submissions
- reduce false negatives for minimal but real high-signal submissions
- keep implementation small
- keep decisions reproducible
- keep audit evidence explicit

## First-Version Scope

Allowed mutations:

- repository-local source files
- repository-local tests
- repository-local prompts or rubric files
- repository-local config
- repository-local documentation required to explain the evaluator

Disallowed mutations:

- production deployment
- database writes outside the repository
- hidden manual labels
- secret-dependent behavior
- network-only evaluation
- changes outside the checked-out backend repository

## Evaluation Philosophy

The evaluator must not reward projects for sounding intelligent. It should reward evidence that a system can evolve itself across iterations.

High-signal evidence:

- declared goal and constraints
- observable iteration history
- versioned changes
- measurable improvement
- failed attempts and rollbacks
- reproducible micro-run
- machine-readable artifacts
- clear separation between system output and human claims

Low-signal or negative evidence:

- only a prompt template changed
- no reproducible run
- no artifact hash or commit record
- claims of autonomy without logs
- impressive UI with no evolution trace
- manual edits between iterations
- benchmark overfitting

## Golden Set

The first golden set should be hand-written, small, and adversarial.

### Case 1: Strong Minimal Evolution System

Expected label: accept.

Signals:

- small codebase
- goal config
- three iteration logs
- each iteration has baseline, mutation, metric, and commit hash
- final score improves over baseline
- failed experiment is recorded and rolled back

Purpose:

Ensure the evaluator recognizes real self-evolution even when the project is not flashy.

### Case 2: Prompt-Only Wrapper

Expected label: reject.

Signals:

- describes itself as autonomous
- only changes prompt wording
- no independent evaluator
- no versioned experiment history
- no reproducible artifact

Purpose:

Prevent polished prompt engineering from passing as self-evolution.

### Case 3: Non-Reproducible Demo

Expected label: reject.

Signals:

- has a video or webpage
- no runnable micro-run
- no fixed input
- no output hash
- no test command

Purpose:

Reject submissions that cannot be independently audited.

### Case 4: Over-Complex Agent Swarm

Expected label: reject or downgrade.

Signals:

- many agents and tools
- unclear authority boundaries
- no deterministic governor
- no rollback
- no measurable improvement
- heavy dependency graph

Purpose:

Penalize complexity without verifiable evolution.

### Case 5: Real But Initially Weak System

Expected label: conditional accept or needs-review.

Signals:

- has versioned iterations
- has evaluator
- has partial metrics
- improvement is small but reproducible
- audit trail is incomplete in one place

Purpose:

Avoid false negatives against promising builders whose first artifact is rough but real.

### Case 6: Benchmark Overfit Submission

Expected label: reject.

Signals:

- passes public examples
- hardcodes expected benchmark outputs
- no general evolution loop
- no independent reflection or rollback

Purpose:

Force the evaluator to detect gaming behavior.

## Metrics

Recommended first metrics:

```text
true_positive_score
false_positive_penalty
false_negative_penalty
reproducibility_score
auditability_score
complexity_penalty
```

Candidate fitness:

```text
fitness =
  true_positive_score
  + reproducibility_score * 0.25
  + auditability_score * 0.25
  - false_positive_penalty * 0.50
  - false_negative_penalty * 0.75
  - complexity_penalty * 0.20
```

False negatives should be penalized more heavily than false positives if Token-Ignition's mission is talent discovery. This is a product decision, not a universal rule.

## First Evolution Loop

```text
accepted backend commit
  -> governor creates sandbox worktree
  -> planner reviews current evaluator and golden set failures
  -> executor modifies only backend repo files
  -> evaluator runs tests and golden set
  -> governor compares candidate fitness with baseline
  -> promote or roll back
  -> ledger records plan, diff, metrics, decision, reflection
```

## Tests Required Before Promotion

Hard gates:

- existing backend tests pass
- golden set tests pass or improve without critical regression
- evaluator emits machine-readable audit reasons
- no mutation outside repo
- candidate has a commit or patch
- ledger entry is complete

Soft gates:

- fewer lines of code is better
- fewer dependencies are better
- simpler scoring rules are better if accuracy does not drop
- evaluator explanations should be short and evidence-linked

## Open Design Questions

- Should the evaluator optimize for high recall first, then precision later?
- Should "conditional accept" exist as a first-class label?
- Should golden set labels be binary or graded?
- How much hidden adversarial data should be withheld from the planner and executor?
- Should the first kernel run one experiment at a time or multiple sandbox experiments in parallel?

## Proposed First Implementation Order

1. Clone or locate `token-ignition-backend`.
2. Read its current evaluator, test structure, and audit output format.
3. Create the hand-written golden set inside the backend repo or under this kernel's fixtures.
4. Implement deterministic governor with Git worktree sandboxing.
5. Implement file-based role handoff.
6. Run one full local evolution cycle.
7. Inspect the ledger manually before enabling repeated autonomous runs.

