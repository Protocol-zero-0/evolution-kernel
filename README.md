# Evolution Kernel

English | [中文](README.zh.md)

**Evolution Kernel** is a minimal protocol and runtime design for autonomous, self-evolving software systems.

Its core positioning is a **general-purpose evolution engine** capable of optimizing **any** software project. It provides a standardized loop for proposing, executing, and evaluating code changes autonomously.

## First Optimization Target

While designed to be universal, the first system being optimized by Evolution Kernel is **Token-Ignition** (specifically its backend evaluator). Token-Ignition serves as the first use case to prove the kernel's ability to safely and deterministically evolve a codebase.

## Current Status (v0)

The current v0 implementation provides the foundational runtime:
- **Deterministic Governor**: Orchestrates the evolution loop, manages the ledger, and handles promotion/rollback of experiments.
- **Git-backed Sandbox Versioning**: Uses Git worktrees to isolate experiments without affecting the main repository until explicitly accepted.
- **File-based Role Handoff**: Clean separation of concerns via isolated commands (`planner`, `executor`, `evaluator`) communicating via JSON files (`plan.json`, `evaluation.json`).
- **Token-Ignition Adapter**: A minimal adapter with a hand-written golden set to evaluate the evolution of the Token-Ignition system.

## Next Steps (Roadmap)

- [ ] **LLM Integration**: Implement actual LLM-driven Planners and Executors (currently using mock/fixture scripts for testing).
- [ ] **Enhanced Sandboxing**: Stronger isolation for the `executor` and `evaluator` beyond Git worktrees (e.g., Docker/containerized execution).
- [ ] **More Adapters**: Expand beyond Token-Ignition to optimize other types of projects and workflows.
- [ ] **Advanced Rollback & Branching**: Support for parallel evolution branches and more complex merge strategies.

## Documents

- [Protocol](docs/protocol.md)
- [Token-Ignition First Task](docs/token-ignition-first-task.md)

## Run Tests

```bash
python3 -m unittest discover -s tests -v
python3 adapters/token_ignition/evaluate_golden_cases.py
```

## CLI Shape

```bash
python3 -m evolution_kernel.cli \
  --repo /path/to/target-repo \
  --ledger /path/to/evolution-ledger \
  --goal /path/to/goal.json \
  --planner python3 /path/to/planner.py \
  --executor python3 /path/to/executor.py \
  --evaluator python3 /path/to/evaluator.py
```

Each role command receives:

```text
--input <json>
--output <json>
--worktree <sandbox path>
```
