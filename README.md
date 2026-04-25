# Evolution Kernel

English | [中文](README.zh.md)

Evolution Kernel is a minimal protocol and runtime design for autonomous self-evolving software systems.

The first host system is Token-Ignition's backend evaluator: an autonomous review system that should improve its ability to identify high-potential AI-native builders while keeping the implementation small, reproducible, sandboxed, and auditable.

The current v0 includes a deterministic governor, Git-backed sandbox versioning, file-based role handoff, and a hand-written Token-Ignition golden set.

## Documents

- [Protocol](docs/protocol.md)
- [Token-Ignition First Task](docs/token-ignition-first-task.md)

## V0 Runtime

The runtime has four parts:

- `governor`: deterministic orchestration, Git worktrees, ledger, promotion, rollback
- `planner`: isolated command that writes `plan.json`
- `executor`: isolated command that mutates only the sandbox worktree
- `evaluator`: isolated command that writes `evaluation.json`

Promotion does not move the target repository's main branch. It moves the local `evolution/accepted` branch to the candidate commit. Rejected experiments keep their ledger records but do not advance `evolution/accepted`.

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

## Token-Ignition Adapter

The first adapter is intentionally small:

- `adapters/token_ignition/golden_cases.json`
- `adapters/token_ignition/evaluate_golden_cases.py`

It defines six adversarial cases for evaluator evolution: strong minimal evolution, prompt-only wrapper, non-reproducible demo, over-complex swarm, real-but-weak system, and benchmark overfit.
