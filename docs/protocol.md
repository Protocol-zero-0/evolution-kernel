# Evolution Kernel Protocol

## Purpose

Evolution Kernel defines a small control mechanism for autonomous self-evolving systems.

The kernel lets a host system receive a long-term or mid-term goal, observe itself and its environment, plan modifications, execute those modifications inside a sandbox, evaluate the result independently, then promote or roll back the version.

The core property is not "an agent that edits code." The core property is a reproducible evolution loop with isolated roles, versioned experiments, explicit rollback, and auditable evidence.

## Non-Goals

- It is not a general chat agent framework.
- It is not a prompt optimization loop.
- It is not allowed to mutate production state directly in v0.
- It does not require a specific LLM provider.
- It does not trust natural-language self-reports as proof of improvement.

## Roles

The protocol separates intelligence from authority.

### Governor

The governor is deterministic orchestration code, not an intelligent agent.

Responsibilities:

- load the goal and constraints
- create sandbox worktrees
- dispatch isolated tasks to planner, executor, and evaluator
- record commits, diffs, metrics, decisions, and rollback points
- promote accepted experiments
- discard runtime effects from failed experiments
- write the audit ledger

The governor must not invent strategy, modify host code, or judge qualitative success.

### Planner

The planner decides the next evolution experiment.

Inputs:

- goal spec
- current accepted version
- summarized historical ledger
- latest evaluation metrics
- resource budget

Outputs:

- a structured plan
- files or modules allowed to change
- expected improvement
- risks
- tests or metrics the evaluator should care about

The planner must not edit files or mark an experiment as successful.

### Executor

The executor applies one plan inside a sandbox.

Inputs:

- plan
- sandbox checkout of the accepted version
- explicit mutation scope

Outputs:

- patch or commit
- implementation notes
- commands attempted
- test commands it ran locally, if allowed

The executor must not promote its own work. It should not receive evaluator hidden rubrics or the full private scoring logic.

### Evaluator

The evaluator judges the sandbox result in a separate context.

Inputs:

- goal spec
- accepted baseline
- candidate patch or commit
- public evaluation rules
- golden set
- test commands

Outputs:

- machine-readable metrics
- pass/fail decision recommendation
- regression report
- complexity report
- reproducibility report

The evaluator must not edit files. It should not rely on executor self-explanations as evidence.

## Isolation Model

Planner, executor, and evaluator are independent entities. They communicate through files written by the governor, not through a shared free-form conversation.

The shared state is a ledger, not a memory transcript.

Allowed communication:

- `goal.yaml`
- `plan.json`
- `patch.diff`
- `evaluation.json`
- `decision.json`
- `reflection.json`

Disallowed communication in v0:

- planner and executor sharing a live chat context
- executor seeing hidden evaluator scoring details
- evaluator accepting executor's explanation without running tests
- any role mutating accepted state directly

## Version Model

The v0 version store is Git.

Abstract state:

```text
accepted_version_n
  -> sandbox_experiment_n+1
      -> candidate_commit_n+1
          -> accepted: promote to accepted_version_n+1
          -> rejected: keep failed ledger, roll back to accepted_version_n
```

Required version records:

- accepted commit before the run
- sandbox branch or worktree path
- candidate commit
- patch diff
- decision
- rollback target

Failed experiments are not erased. Their runtime effects are discarded, but their evidence remains in the ledger.

## Sandbox Model

Every experiment runs in a sandbox created from the latest accepted version.

v0 sandbox requirements:

- only repo-local file mutations are allowed
- network access is disabled unless explicitly configured by the host
- secrets are not mounted by default
- production state is not mounted
- evaluator runs from a clean checkout or clean worktree
- promotion happens only through the governor

The sandbox is a boundary around observation, modification, and testing, not only around command execution.

## Ledger Layout

Recommended filesystem layout:

```text
evolution-ledger/
  goal.yaml
  accepted/
    current_commit.txt
  runs/
    0001/
      planner_input.json
      plan.json
      executor_input.json
      patch.diff
      candidate_commit.txt
      evaluator_input.json
      evaluation.json
      decision.json
      reflection.json
  failed/
    0001-summary.json
```

The ledger must be sufficient for an external auditor to reconstruct what happened without reading private chat state.

## Goal Spec

Minimal goal fields:

```yaml
name: token-ignition-review-evolution
objective: Improve evaluator accuracy while minimizing implementation complexity.
target_metrics:
  talent_detection_accuracy: maximize
  false_positive_rate: minimize
  false_negative_rate: minimize
  reproducibility_score: maximize
  complexity_score: minimize
constraints:
  only_modify_repo_files: true
  require_sandbox: true
  require_git_versioning: true
  max_iterations: 20
  max_wall_time_minutes: 60
acceptance:
  require_existing_tests_pass: true
  require_golden_set_non_regression: true
  require_audit_log: true
```

## Promotion Rule

A candidate version can be promoted only if all hard constraints pass.

After hard constraints pass, the governor compares the candidate against the accepted baseline using the host's fitness function.

Example:

```text
fitness =
  talent_detection_accuracy
  + reproducibility_score * 0.25
  - false_positive_rate * 0.5
  - false_negative_rate * 0.75
  - complexity_penalty * 0.2
```

The exact function is host-specific, but it must be declared before evaluation.

## Reflection

Reflection is not proof. It is compressed learning for future planning.

A reflection should capture:

- what changed
- what improved
- what regressed
- why the governor accepted or rejected the candidate
- what future planners should avoid
- what follow-up experiment is suggested

Reflection must be linked to metrics and commits.

## Minimal V0 Scope

The first implementation should support:

- Git-backed versioning
- local worktree sandbox
- file-based ledger
- three role prompts or adapters
- deterministic governor
- host-provided test commands
- host-provided golden set
- rollback by deleting or abandoning failed worktree branches

It should not support production deployments, database mutation, credentialed network actions, or hidden evaluator state in v0.

