## Repository snapshot — 2026-05-13

This document inventories what's actually inside `evolution-kernel` as of 2026-05-13, after stages 0–3 are merged and v0.3.0 is tagged. Every claim is anchored to a file path or git commit that anyone can verify in their own clone.

---

## Runtime — 8 Python modules, ~1,800 LOC total

```
evolution_kernel/__init__.py        4 LOC
evolution_kernel/cli.py           327 LOC   — argument parsing, --loop dispatch
evolution_kernel/config.py        368 LOC   — evolution.yml schema + validation
evolution_kernel/governor.py      673 LOC   — closed-loop orchestrator (zero LLM calls)
evolution_kernel/hard_stops.py    132 LOC   — max_iterations / max_total_usd / max_total_tokens
evolution_kernel/observer.py      100 LOC   — runs evidence_sources, normalizes output
evolution_kernel/sandbox.py       100 LOC   — process sandbox (PR7a, work-in-progress)
evolution_kernel/scope.py          70 LOC   — allowed_paths enforcement
                                ─────────
                                1,774 LOC
```

Single runtime dependency: **PyYAML**. Python ≥ 3.10.

The Governor (`governor.py`) is the only orchestration code. It contains **zero LLM calls** — all intelligence is in the role scripts below. This is the protocol's central separation: the kernel routes intelligence, it does not embed it.

---

## Role scripts — 5 external processes, JSON-mediated

The kernel never imports a role. It executes each as a subprocess and exchanges JSON files at `roles/*.{input,output}.json`. Any role can be swapped for an equivalent reading the same protocol.

```
roles/planner.py          — LLM call: produces a concrete plan from goal + observation + history
roles/executor.sh         — wraps aider or claude-code to apply the plan inside a git worktree
roles/evaluator.py        — LLM call: judges accept/reject on the new metric + diff
roles/goal_evaluator.py   — LLM call: judges whether the overall mission is complete (PR13)
roles/strategist.py       — LLM call: injects stage/next_milestone/taboo every N rounds (PR13)
```

Protocol spec: [`docs/protocol.md`](../../docs/protocol.md) — RFC-style, lists what each role must do and must not do.

---

## Test suite — 83 tests, ~25s, no network

```
tests/test_acceptance.py            6   — end-to-end loop on a synthetic target
tests/test_cli.py                   1   — CLI smoke
tests/test_governor.py              3   — closed-loop dispatch logic
tests/test_issue10.py              15   — goal_evaluator + strategist (PR13, stage 2)
tests/test_issue14.py              13   — k-branch parallel exploration (PR15, stage 3)
tests/test_pr4.py                  20   — LLM roles, multi-round, history injection, cost guard
tests/test_pr7a.py                 16   — process sandbox (work-in-progress)
tests/test_scope.py                 8   — allowed_paths enforcement
tests/test_token_ignition_goldens.py 1   — handwritten golden cases
                                  ───
                                   83
```

Raw transcript: [`test-output.txt`](test-output.txt).

CI runs on Python 3.10 and 3.12. The full suite mocks LLM endpoints — no API key or network is required to verify the kernel's logic.

---

## Build history — 4 merged stages, 1 in-flight

| Stage | PR | Merged | Adds |
|---|---|---|---|
| 0 — MVP closed loop | [#2](https://github.com/Protocol-zero-0/evolution-kernel/pull/2) | 2026-05-10 | Observer, scope, hard stops, ledger |
| 1 — LLM + multi-round + memory | [#4](https://github.com/Protocol-zero-0/evolution-kernel/pull/4) | 2026-05-10 | 3-role LLM, `run_until_done`, history injection, cost guard → **v0.2** |
| 2 — Goal evaluator + strategist | [#13](https://github.com/Protocol-zero-0/evolution-kernel/pull/13) | 2026-05-13 | Mission-completion judgment; strategic guidance every N rounds |
| 3 — k-branch parallel | [#15](https://github.com/Protocol-zero-0/evolution-kernel/pull/15) | 2026-05-13 | `run_once_parallel(goal, k)` — FunSearch / AlphaEvolve-style population search → **v0.3** |
| 4 — Process sandbox | (PR7a, in-flight) | — | OS-level isolation of executor; escape-attempt fixture in `tests/fixtures/` |

Raw git log:

```
818860b chore: bump version to 0.3.0 (#16)
cd4aa06 feat: k-branch parallel exploration (closes #14) (#15)
683ec6e feat: goal evaluator + strategist (closes #10) (#13)
3cee524 docs: replace SWE-Bench example with GSM8K math tutoring (en + zh) (#12)
1f29bd7 docs: SWE-Bench example + fix 5 Copilot review issues (#11)
5846b6c docs: replace coverage example with game AI example; full zh-CN rewrite (#8)
cf06eee PR4: LLM roles + multi-round loop + history injection + cost guard + README rewrite
4658aa6 feat: MVP closed loop — observer, scope, hard stops, ledger (PR #2)
```

---

## Ledger structure — every decision reconstructable from disk

After any run, `<ledger-dir>/runs/0001/` contains:

```
config.json             — full snapshot of evolution.yml at this iteration
observation.json        — raw output of evidence_sources commands
planner_input.json      — goal + observation + history fed to planner
plan.json               — planner's output: summary, steps, expected improvement
executor_input.json     — plan + worktree path fed to executor
executor_output.json    — executor result, diagnostics
evaluator_input.json    — goal + patch + observation fed to evaluator
patch.diff              — actual diff the executor applied
candidate_commit.txt    — git SHA of the sandboxed commit
evaluation.json         — metrics + cost_usd + tokens_used + accept/reject reasoning
decision.json           — final accept/reject + governor's reason
reflection.json         — one-line summary injected into next round's history
```

State across runs (`<ledger-dir>/.evolution_state.json`) survives process restarts — kill the process, restart it, the loop resumes from where it stopped.

Every accepted change is a real git commit on the `evolution/accepted` branch. To roll back an entire session:

```bash
git checkout evolution/accepted
git reset --hard <baseline-sha>
```

---

## Self-imposed boundaries

What the kernel **does not** do, and where you'll find that intentional gap in the source:

| Boundary | Where it's enforced |
|---|---|
| Governor cannot call an LLM | `governor.py` has no `anthropic` or `openai` import |
| Roles cannot share memory directly | All inter-role I/O is files in the run dir |
| Executor cannot escape its worktree | `scope.py` rejects any change outside `allowed_paths`; PR7a adds OS-level isolation |
| A failed iteration cannot leak budget | `hard_stops.py` accumulates `cost_usd` + `tokens_used` per role-call; checked before every dispatch |
