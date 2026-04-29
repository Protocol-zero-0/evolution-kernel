# Evolution Kernel

<p align="center">
  <strong>A general-purpose evolution engine for autonomously improving software projects.</strong>
</p>

<p align="center">
  <a href="README.zh.md">中文</a>
  ·
  <a href="docs/protocol.md">Protocol</a>
  ·
  <a href="docs/token-ignition-first-task.md">First Target</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-v0%20prototype-orange" alt="Status: v0 prototype">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue" alt="Python >= 3.10">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License">
  <img src="https://img.shields.io/badge/runtime-Git%20worktree%20sandbox-purple" alt="Git worktree sandbox">
</p>

**Evolution Kernel** is a minimal protocol and runtime for autonomous, self-evolving software systems.

## Quick Start

```bash
# Install
pip install -e .

# Run the demo (uses fixture roles from tests/fixtures/)
bash examples/run_demo.sh

# Check the result
cat /tmp/ek-demo-ledger/runs/0001/decision.json
```

It is not a project-specific automation script. Its purpose is to make software evolution **controlled, reproducible, sandboxed, auditable, and reversible**. Any project can become an optimization target once it can expose a goal, a sandbox, and an evaluator.

## Why It Exists

Modern coding agents can propose and modify code, but long-running software improvement needs more than code generation. It needs a kernel that can:

- define what improvement means for a target project,
- isolate each experiment before it touches the accepted branch,
- evaluate candidate changes with repeatable criteria,
- promote only accepted candidates,
- keep a ledger of what happened and why.

Evolution Kernel provides that loop as a small, inspectable runtime.

## Evolution Loop

```mermaid
flowchart LR
    Goal[Goal] --> Governor[Governor]
    Governor --> Planner[Planner]
    Planner --> Plan[plan.json]
    Plan --> Executor[Executor]
    Executor --> Candidate[Sandbox candidate]
    Candidate --> Evaluator[Evaluator]
    Evaluator --> Eval[evaluation.json]
    Eval --> Governor
    Governor --> Accepted[evolution/accepted]
    Governor --> Ledger[Ledger]
```

## First Optimization Target

Evolution Kernel is designed to optimize **any** software project. The first project being optimized is **Token-Ignition**, specifically its backend evaluator.

Token-Ignition is therefore the first optimization target and reference adapter, not a hard dependency. It is used to prove that the kernel can safely and deterministically evolve a real codebase while keeping the runtime small.

## Current Status

The current v0 implementation provides the foundational runtime:

| Area | What exists now |
| --- | --- |
| Governor | Deterministic orchestration for planning, execution, evaluation, promotion, rollback, and ledger updates. |
| Sandbox | Git worktree-based experiment isolation. Candidate changes do not affect the accepted branch unless promoted. |
| Role handoff | `planner`, `executor`, and `evaluator` run as isolated commands and communicate through JSON files. |
| Promotion model | Accepted candidates advance the local `evolution/accepted` branch. Rejected experiments remain recorded but do not advance it. |
| First adapter | A Token-Ignition adapter with a hand-written golden set for evaluator evolution. |

## What It Does Not Do Yet

| Not yet | Why it matters |
| --- | --- |
| LLM-native planner/executor | The current tests use fixture scripts; real agent integrations are the next step. |
| Strong process/container sandboxing | Git worktrees isolate files, but executor and evaluator isolation should become stronger. |
| Multi-target adapter framework | Token-Ignition is the first target; more adapters are needed to prove generality. |
| Parallel evolution branches | v0 focuses on one accepted branch and a simple promotion path. |

## Roadmap

- [ ] Add LLM-driven planner and executor implementations.
- [ ] Add stronger sandbox isolation for executor and evaluator runs.
- [ ] Generalize the adapter interface beyond Token-Ignition.
- [ ] Add examples for multiple project types.
- [ ] Support parallel evolution branches and richer merge strategies.
- [ ] Improve reporting around ledger history, promotion decisions, and rejected candidates.

## Documents

- [Protocol](docs/protocol.md)
- [Token-Ignition First Task](docs/token-ignition-first-task.md)

## Run Tests

```bash
python3 -m unittest discover -s tests -v
python3 adapters/token_ignition/evaluate_golden_cases.py
```

## CLI

```bash
# Using a config file (recommended)
python3 -m evolution_kernel.cli \
  --config examples/evolution.yml \
  --repo /path/to/target-repo \
  --ledger /tmp/evolution-ledger

# Legacy: explicit role args (backward compatible)
python3 -m evolution_kernel.cli \
  --repo /path/to/target-repo \
  --ledger /tmp/evolution-ledger \
  --goal goal.json \
  --planner python3 my_planner.py \
  --executor python3 my_executor.py \
  --evaluator python3 my_evaluator.py

# Reset hard stop state
python3 -m evolution_kernel.cli --reset --ledger /tmp/evolution-ledger
```

Each role command receives:

```text
--input <json>
--output <json>
--worktree <sandbox path>
```

## Config format (`evolution.yml`)

```yaml
mission: "Improve the project."

evidence_sources:
  - type: file
    path: "./metrics.json"
  - type: shell
    command: "bash ./scripts/status.sh"

mutation_scope:
  allowed_paths:
    - "src/"
    - "tests/"

hard_stops:
  max_iterations: 3
  max_consecutive_failures: 2

roles:
  planner:  ["python3", "my_planner.py"]
  executor: ["python3", "my_executor.py"]
  evaluator: ["python3", "my_evaluator.py"]
```

## Ledger artifacts (per run)

Each run produces the following files in `ledger/runs/{run_id}/`:

| File | Description |
|---|---|
| `observation.json` | Evidence collected before planning |
| `plan.json` | Planner output |
| `patch.diff` | Changes made by executor |
| `candidate_commit.txt` | SHA of the candidate commit |
| `evaluation.json` | Evaluator verdict |
| `decision.json` | Accept/reject decision with reason |
| `reflection.json` | Summary for auditing |
