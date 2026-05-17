# Quickstart — see the loop close in 30 seconds

> **10-minute promise, actually 1.4 seconds. \$0. No API key.**

This example exists for one reason: prove that a stranger can clone the repo and watch a real `evolution/accepted` commit appear in under a minute. The mission is deliberately small — *drive ruff to zero violations on `src/messy.py`* — so the whole closed loop fits in one terminal scroll.

There is **no LLM** in this example. The planner / executor / evaluator are 30-line Python scripts checked into the demo target itself. The point is to demonstrate the *runtime*: worktree sandboxing, scope enforcement, ledger writes, the `evolution/accepted` branch advancing — not LLM smarts. When you want LLM-driven evolution, see `examples/oss_fix_demo/` (separate example, requires `claude` CLI or an API key).

## Run it

From a fresh clone of `evolution-kernel`:

```bash
pip install -e .
pip install ruff               # only test dep beyond the runtime
bash examples/quickstart/setup.sh
evolution-kernel \
  --config examples/quickstart/evolution.yml \
  --repo /tmp/ek-quickstart-target \
  --ledger /tmp/ek-quickstart-ledger \
  --loop
```

Expected output (last 8 lines):

```
{
  "accepted": true,
  "candidate_commit": "<sha>",
  "reason": "hard gates passed and evaluator recommended promotion",
  ...
}
```

## Measured (2026-05-17, this machine)

| Step | Wall-clock | Cost |
|---|---|---|
| `setup.sh` | 57 ms | \$0 |
| `evolution-kernel --loop` (2 rounds — 1 accept + 1 halt) | **1.4 s** | \$0 |
| Total | **~1.5 s** | **\$0** |

Compared to the "10 minutes" headline this is a 400× margin. The headline number is what we promise a stranger on a slow laptop with cold caches; the actual e2e is well inside it.

## What the loop did

`runs/0001/` contains the complete forensic record:

- `plan.json` — canned plan: "run ruff check --fix, then ruff format on src/"
- `executor_output.json` — exit codes and stdout tails from both ruff invocations
- `patch.diff` — the actual diff ruff applied (removes unused imports, fixes `== None` → `is None`, fixes whitespace)
- `evaluation.json` — `hard_gates_passed: true`, `ruff_output_tail: "All checks passed!"`
- `decision.json` — `accepted: true`, with the candidate sha that landed on `evolution/accepted`
- `reflection.json` — what the governor records about this run for the next planner call

You can inspect the real commit:

```bash
git -C /tmp/ek-quickstart-target log --oneline evolution/accepted
# 33a92a4 evolution experiment 0001
# 433ebdd quickstart target initial commit
```

Round 2 (the `halt`) is the natural stopping signal: ruff is already clean, the executor has nothing to change, the governor records `executor produced no repo changes` and stops.

## Want the LLM version?

See `examples/oss_fix_demo/` — same shape, real OSS target, `claude` CLI as executor.
