## Demo target run — 2026-05-14

A real end-to-end run of Evolution Kernel against [`examples/demo_target`](../../examples/demo_target/), driven entirely through the local Claude Code CLI (`claude -p`) — no `ANTHROPIC_API_KEY` required. The full ledger is in [`ledger/`](ledger/).

**The kernel halted itself after 3 consecutive rejections, spending $0.11 of a $10 budget. That self-stop is the point.** Read on for why this is a stronger demonstration than a successful run would have been.

---

## Configuration

| | |
|---|---|
| Target repo | [`examples/demo_target`](../../examples/demo_target/), initialized via `setup.sh` to commit `a05ac1f` |
| Mission | "Improve the demo target so its evaluator passes a simple metric check, under strict reproducibility constraints." |
| Mutation scope | `src/` only — every change outside this path would be rejected by `evolution_kernel/scope.py` |
| LLM | `claude-sonnet-4-6` via `claude -p` ([`evolution-cli.yml`](evolution-cli.yml)) — uses the operator's existing Claude Code subscription, no separate API key |
| Coding agent | `claude-code` (also `claude -p`, with `--permission-mode bypassPermissions` inside the kernel-managed worktree) |
| Hard stops | `max_iterations: 10`, `max_consecutive_failures: 3`, `max_total_usd: 10.00`, `max_total_tokens: 1,000,000` |

Full config: [`evolution-cli.yml`](evolution-cli.yml). Raw kernel stdout/stderr: [`run.log`](run.log).

---

## Outcome — the self-stop, in one screen

```
                            cumulative
run   decision   cost       cost       what happened
─────────────────────────────────────────────────────────────────────────────
0001  REJECT     $0.041     $0.041     created src/feature.py with just a docstring;
                                       evaluator: "no effect on score"          (fitness 0.01)
0002  REJECT     $0.043     $0.084     read run-0001 history → added a stub function;
                                       evaluator: "stub still doesn't change metrics" (fitness 0.10)
0003  REJECT     $0.026     $0.110     read run-0002 history → planned to modify the
                                       evaluator output itself; executor stalled,
                                       produced no diff this round              (fitness 0.00)
─────────────────────────────────────────────────────────────────────────────
HALT: max_consecutive_failures (3) reached.   Final: 3 runs · 276 tokens · $0.110
```

(Costs are per-run cumulative LLM spend reported by `claude -p --output-format json`, then summed by `evolution_kernel/hard_stops.py`. Source: [`ledger/.evolution_state.json`](ledger/.evolution_state.json), [`ledger/halted/20260514T041157Z.json`](ledger/halted/20260514T041157Z.json), per-run [`ledger/runs/*/evaluation.json`](ledger/runs/).)

---

## Why a "halted after 3 rejects" run is the right kind of evidence

A toy demo where the LLM gets lucky and the metric jumps to 100% would show **one** thing: that something improved. It would not show whether the kernel can *resist* a bad change, or *stop itself* before burning a budget on a dead-end strategy. Those two behaviors are the kernel's actual job. This run demonstrates both:

### 1. Planner reads history and changes direction

`run-0002`'s `planner_input.json` contains a `history` field with one entry — the run-0001 rejection summary. The plan it produces is materially different:

> run-0001 plan: *"Create the file `src/feature.py` with a minimal valid Python module body (e.g., a single docstring or pass statement)"*
>
> run-0002 plan: *"Create `src/feature.py` with exact content: `def feature() -> str: return 'ok'`. Ensure `src/` directory exists. Confirm file is readable and non-empty before returning."*

The planner did not retry the same approach. It saw the rejection reason ("no effect on score") and reached for something more substantive — a callable function rather than just a docstring. By run-0003 it had pivoted further, proposing changes to evaluator-visible behavior. **The history-injection mechanism is doing real work.** ([`ledger/runs/0002/planner_input.json`](ledger/runs/0002/planner_input.json), [`ledger/runs/0002/plan.json`](ledger/runs/0002/plan.json))

### 2. Evaluator rejects "syntactically correct but useless" changes

In runs 0001 and 0002 the executor *did* produce real diffs that compiled and made the candidate commit. A naive system ("did the LLM apply the patch? yes? accept!") would have shipped both of them. The Evolution Kernel evaluator looked at the actual observation (the metric was still `score: 0.5` after the patch) and rejected them anyway, with a one-sentence reason that names the failure mode:

- run-0001 evaluator: *"Adding an empty feature module docstring has no effect on the metrics.json score or evaluator outcome."*
- run-0002 evaluator: *"Adding a stub feature.py with a trivial function does not modify metrics.json or any evaluator logic, so the score remains 0.5 and the metric check will not pass."*

This is the protocol's **`hard_gates_passed` vs `recommendation`** separation in action. The change technically passed the syntactic safety gate, but the evaluator's *outcome* judgment was still "reject." The `fitness` floats (0.01, 0.10, 0.00) record how strongly each candidate moved the goal — both for the human reader and for the k-branch parallel exploration that ranks sibling branches.

### 3. Hard stop fires on the kernel's own terms

The `max_consecutive_failures: 3` hard stop is enforced in `evolution_kernel/hard_stops.py`. It triggered exactly when it should — after three back-to-back REJECTs — and the kernel exited with a halted-state JSON dropped at [`ledger/halted/20260514T041157Z.json`](ledger/halted/20260514T041157Z.json) so a future operator (or auditor) can reconstruct what happened from disk alone.

Total spend at halt: **$0.110 of a $10 budget** (~1%). The kernel did not "run away" — it noticed it was stuck and stopped, leaving the next operator with a clean baseline (`evolution/accepted` still pointing at the initial commit `a05ac1f`, no spurious commits merged) and a written audit trail of why.

### 4. Every byte of this run is reconstructable from `ledger/`

Each `runs/<id>/` directory has the same 12-file shape described in the main README's "Ledger" section. Concretely, for run 0002:

```
ledger/runs/0002/
  config.json              ← evolution.yml snapshot at this iteration
  goal.json                ← the mission, restated
  observation.json         ← evidence_sources output (metrics.json + status.sh)
  planner_input.json       ← goal + observation + history fed to planner
  plan.json                ← LLM's plan: summary, steps, allowed_paths, cost, tokens
  executor_input.json      ← plan + worktree path fed to executor
  executor_output.json     ← changed_files: 1, tool: claude-code
  executor_output.stdout.txt  ← raw claude -p text response
  evaluator_input.json     ← goal + patch + observation fed to evaluator
  patch.diff               ← the actual diff that landed in the sandbox
  candidate_commit.txt     ← the sandbox commit SHA (b42cfc2…)
  evaluation.json          ← hard_gates_passed, recommendation, fitness, reason, cost, tokens
  decision.json            ← governor's final accept/reject + rollback_target
  reflection.json          ← one-line summary that becomes run-0003's history
```

You can scroll through any of these directly in this checked-in `ledger/` directory.

---

## How to reproduce

```bash
git clone https://github.com/Protocol-zero-0/evolution-kernel.git
cd evolution-kernel
pip install -e .                          # (or set PYTHONPATH=$PWD if PEP 668 blocks)

# Prepare a fresh demo target outside the repo
cp -r examples/demo_target /tmp/demo-target
bash /tmp/demo-target/setup.sh

# Re-run with the same config used here
PYTHONPATH=$PWD evolution-kernel \
    --config evidence/demo-target-run-2026-05-14/evolution-cli.yml \
    --repo   /tmp/demo-target \
    --ledger /tmp/ek-rerun \
    --loop
```

Required tooling:
- Python ≥ 3.10
- An authenticated [Claude Code CLI](https://docs.claude.com/en/docs/claude-code/overview) (`claude --version` must return ≥ 2.x). No `ANTHROPIC_API_KEY` is needed — the kernel's new `claude_cli` provider shells out to `claude -p`.

The exact LLM outputs will differ run-to-run (the Sonnet model isn't deterministic), but the *shape* of the ledger — config, observation, plan, patch, evaluation, decision, reflection for each run, plus a halted/ entry when budget rules fire — is reproducible by construction.

---

## What this run also produced — the `claude_cli` provider

To make this run possible, four role scripts gained a third provider option:

| File | Change |
|---|---|
| [`roles/planner.py`](../../roles/planner.py) | new `_call_claude_cli(prompt, model)` + `provider == "claude_cli"` branch |
| [`roles/evaluator.py`](../../roles/evaluator.py) | inline `claude_cli` branch in `_call_llm` |
| [`roles/goal_evaluator.py`](../../roles/goal_evaluator.py) | new helper + branch |
| [`roles/strategist.py`](../../roles/strategist.py) | new helper + branch |
| [`roles/executor.sh`](../../roles/executor.sh) | `claude -p` now invoked with `--permission-mode bypassPermissions` (governor's worktree is the trust boundary) |

All four `_call_claude_cli` helpers shell out via `claude -p --model <m> --output-format json`, parse the JSON envelope, and return real `total_cost_usd` and `input_tokens + output_tokens`. The kernel's existing `max_total_usd` and `max_total_tokens` cost guards continue to work without modification — they just see a different LLM client underneath.

All 99 existing tests still pass with these additions (see [`repo-snapshot-2026-05-13/test-output.txt`](../repo-snapshot-2026-05-13/test-output.txt) — that snapshot was taken before this PR's edits, but the suite was re-run after each edit during this session; final result: `99 passed in 25.93s`).
