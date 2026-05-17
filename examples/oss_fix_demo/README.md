# OSS Fix Demo — Claude editing a real open-source repo

> **Real OSS target. Real LLM-driven edits. Real `evolution/accepted` commit. ~50 seconds. No API key.**

This is the companion to `examples/quickstart/`. Where quickstart shows the closed loop with deterministic role scripts (zero LLM, zero cost), this example wires `claude -p` in as the executor and points the kernel at a real third-party repository — [python-slugify](https://github.com/un33k/python-slugify) v8.0.4, 1,106 LoC, MIT.

The mission: drive ruff to zero violations on `slugify/`. The setup script clones the upstream tag, drops a small ruff config in (rules `E/F/I/W`), and commits — that gives the kernel a fresh git history it owns, with 10 real ruff diagnostics waiting to be cleaned up. Claude is invoked via `claude -p --permission-mode acceptEdits`, which uses your local Claude Pro / Max session — there is **no API key**, the work is billed against your subscription's flat fee.

## Why this example exists

A common worry about long-horizon agents: "shows nice demos on toy repos, falls over on real code." This demo points the runtime at a real published OSS package and shows the loop:

1. Observe ruff state.
2. Plan (canned, deterministic — the planner's job here is to give claude *concrete diagnostics*, not to think).
3. Execute (claude reads the diagnostics, decides "use explicit `as` re-exports" for the unused-import warnings, edits the file). The executor also runs `ruff check --fix && ruff format` afterwards to mop up the deterministic autofixes — split of work that mirrors real teams.
4. Evaluate (re-run ruff; accept iff exit 0).
5. Commit on `evolution/accepted` — real git sha, real diff.

## Prereqs

- `pip install -e .` from the repo root.
- `pip install ruff` (only test-time dependency beyond the runtime).
- `claude` CLI signed in to a Claude Pro / Max account. (Verify: `claude --version` prints a version.)

## Run it

```bash
bash examples/oss_fix_demo/setup.sh
evolution-kernel \
  --config examples/oss_fix_demo/evolution.yml \
  --repo /tmp/ek-oss-fix-target \
  --ledger /tmp/ek-oss-fix-ledger \
  --loop
```

## Measured (2026-05-17, this machine)

| Step | Wall-clock | Cost |
|---|---|---|
| `setup.sh` (clones slugify, commits bots, init repo) | ~1 s + clone bandwidth | \$0 |
| Run 1 — claude executor + ruff postprocess + evaluator | **34 s** (claude alone) / **~48 s** total wall-clock for the 3-round loop | Claude Pro subscription, flat fee — no per-token charge |
| Run 2 — halt: ruff already clean, no changes to make | <1 s | \$0 |
| **Total** | **~48 s for the full 3-iteration loop** | **\$0 marginal** |

`Claude executor elapsed: 34.11 s` is the wall-clock from the executor JSON output. The kernel's overhead (worktree create/destroy, planner, evaluator, ledger writes) is the difference vs the 48 s total.

## What the loop actually did

`runs/0001/evaluation.json` — the run that landed:

```json
{
  "hard_gates_passed": true,
  "recommendation": "promote",
  "metrics": {"ruff_clean": 1.0, "ruff_violations_remaining": 0, "fitness": 1.0}
}
```

`runs/0001/executor_output.json` — claude's summary of its edits (captured verbatim from `claude -p`):

```
Fixed both files: added explicit `as` re-exports for all version metadata
imports in slugify/__init__.py, and sorted the from .slugify import names
alphabetically in slugify/__main__.py.
```

Real commit on `evolution/accepted`:

```bash
git -C /tmp/ek-oss-fix-target log --oneline evolution/accepted
# bae97a8 evolution experiment 0001
# 9ca8fc1 oss_fix_demo target: python-slugify v8.0.4 + bots
```

The diff (355 lines, mostly auto-formatting ruff applied as postprocess) is in `runs/0001/patch.diff` — every change a strict superset of "the LLM did the semantic part, deterministic tooling did the structural part," which is the realistic division of labor.

## What to look at in the ledger

Each accepted run leaves:

| File | What it tells you |
|---|---|
| `goal.json` | Mission + scope passed in |
| `observation.json` | Ruff snapshot the planner saw |
| `plan.json` | Canned plan + verbatim ruff diagnostics |
| `executor_input.json` / `executor_output.json` | Prompt and claude's report |
| `patch.diff` | Exact diff applied |
| `evaluation.json` | Ruff result after, fitness metric |
| `decision.json` | accept/reject + candidate sha + rollback target |
| `reflection.json` | What the next planner round will see in history |

## Knobs

- `EK_CLAUDE_BIN` — path to `claude` if not on `$PATH`.
- `EK_CLAUDE_ARGS` — extra args passed to `claude -p` (default `--permission-mode acceptEdits`).
- `EK_CLAUDE_TIMEOUT` — seconds (default 300).
- Edit `evolution.yml` for `hard_stops.max_iterations`, `max_consecutive_failures`. The example caps at 3 iterations because the goal is reachable in one round.

## Want to point this at *your* OSS repo?

Replace the `git clone` line in `setup.sh` with your own URL/tag, point `mutation_scope.allowed_paths` in `evolution.yml` at the right subtree, and rewrite the planner's `summary`/`steps` to describe your goal. The bots are <50 LoC each — easy to fork.
