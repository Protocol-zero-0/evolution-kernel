# Evolution Kernel

<p align="center">
  <strong>Give an LLM a goal. Watch your codebase improve itself. Stop when the budget runs out.</strong>
</p>

<p align="center">
  A ~1,200-line Python runtime that runs an autonomous, multi-round improvement loop on any codebase —<br>
  sandboxed in git worktrees, every decision logged, every change reversible.
</p>

<p align="center">
  <a href="README.zh.md">中文</a>
  ·
  <a href="docs/protocol.md">Protocol</a>
</p>

<p align="center">
  <a href="https://github.com/Protocol-zero-0/evolution-kernel/actions/workflows/tests.yml">
    <img src="https://github.com/Protocol-zero-0/evolution-kernel/actions/workflows/tests.yml/badge.svg" alt="tests">
  </a>
  <img src="https://img.shields.io/badge/status-v0.2-blue" alt="v0.2">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue" alt="Python ≥ 3.10">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/dep-PyYAML%20only-lightgrey" alt="Single dependency">
</p>

---

<p align="center">
  <em>Think of it as AlphaEvolve — but pointed at your own repository.</em><br>
  <em>You define what "better" means. The kernel figures out how to get there.</em>
</p>

---

## What it does

Point Evolution Kernel at any git repository and give it a measurable goal. It runs a closed loop:

| Step | What happens |
|:---:|---|
| 🔍 **Observe** | Run your metric command — collect the current state (win rate, latency, error count, …) |
| 🧠 **Plan** | LLM reads the metric + history of prior attempts, produces a concrete plan |
| 🔨 **Execute** | Coding agent (Aider or Claude Code) applies the plan inside an isolated git worktree |
| ⚖️ **Evaluate** | Re-run your metric; LLM decides accept or reject |
| ✅ **Commit / rollback** | Accepted → real git commit on `evolution/accepted`. Rejected → worktree discarded |
| 🔁 **Loop** | Repeat until `max_iterations`, `max_total_usd`, or `max_total_tokens` fires |

Every attempt is written to a **ledger**: goal, observation, plan, diff, evaluation, decision. Nothing is held in memory. An external auditor — or your future self — can reconstruct every decision from the ledger alone.

---

## Quick Start

```bash
# 1. Install
pip install evolution-kernel

# 2. Describe your goal
cat > evolution.yml << 'EOF'
mission: "Evolve the game AI to win at least 60% of games against the built-in opponent"

evidence_sources:
  - type: shell
    command: "python3 scripts/tournament.py --games 20 --json"

mutation_scope:
  allowed_paths: ["ai/"]

hard_stops:
  max_iterations: 30
  max_consecutive_failures: 4
  max_total_usd: 3.00

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY

coding_agent:
  tool: aider

roles:
  planner:   ["python3", "roles/planner.py"]
  executor:  ["bash",    "roles/executor.sh"]
  evaluator: ["python3", "roles/evaluator.py"]
EOF

# 3. Run — walk away
evolution-kernel --config evolution.yml --repo /path/to/game --ledger /tmp/ledger --loop
```

---

## See it in action

### Evolving a game AI from 35% to 72% win rate — overnight, unattended

```
before   ███░░░░░░░░░  35% win rate   (loses 13 of 20 games)
after    ███████░░░░░  72% win rate   (wins 14 of 20 games)

9 rounds · $2.14 · 0 minutes of your time
```

Here is what the loop actually does, round by round:

```
Round 1   observe: win_rate 35%
  plan    → "Greedy score maximization with no lookahead — add 2-ply minimax"
  execute → aider rewrites ai/strategy.py (68 lines changed)
  eval    → win_rate 51%  ▲+16 pts — ACCEPT
  commit    a3f1c9e  "ai: add minimax (35→51% win rate)"

Round 2   observe: win_rate 51%
  plan    → "Minimax ignores endgame positions; add positional evaluation weights"
  execute → aider adds ai/eval_weights.py
  eval    → win_rate 58%  ▲+7 pts — ACCEPT
  commit    8b2de01  "ai: positional weights (51→58%)"

Round 3   observe: win_rate 58%
  plan    → "Deepen search with alpha-beta pruning"
  execute → aider modifies ai/strategy.py
  eval    → win_rate 56%  ▼-2 pts — REJECT   consecutive_failures: 1
  rollback  worktree discarded · main branch unchanged

Round 4   observe: win_rate 58%  ← history shows Round 3 failed with alpha-beta
  plan    → "Alpha-beta caused regression; tune endgame weights using loss-pattern analysis"
  execute → aider adjusts ai/eval_weights.py
  eval    → win_rate 67%  ▲+9 pts — ACCEPT
  commit    2c9af44  "ai: endgame weight tuning (58→67%)"

...

Round 9   observe: win_rate 72%
  eval    → 72% — target 60% exceeded — ACCEPT
  commit    9d7b321  "ai: final tuning pass (70→72%)"

{"halted": true, "reason": "max_iterations reached", "iterations": 30, "total_usd": 2.14, "total_tokens": 634000}
```

> **Round 3 is the key moment.** Alpha-beta pruning made things *worse*, so the system rejected the change and left the codebase untouched. Round 4 shows the LLM reading the rejection history and changing its approach. This is what "memory" means in practice — not guessing the same wrong answer twice.

---

## Ledger: the complete audit trail

```
ledger/
  .evolution_state.json       ← budget counters; survives restarts
  runs/
    0001/
      config.json             ← full snapshot of your evolution.yml
      observation.json        ← raw output of your evidence_sources commands
      plan.json               ← LLM plan: summary · steps · expected_improvement
      patch.diff              ← exact diff the executor applied
      candidate_commit.txt    ← git SHA of the sandbox commit
      evaluation.json         ← verdict + metrics + cost_usd + tokens_used
      decision.json           ← accept / reject + reason
      reflection.json         ← one-line summary injected into the next round
    0002/  ...
  halted/
    20260501T120000Z.json     ← written when any hard stop fires
```

To undo every change from a session:

```bash
git checkout evolution/accepted
git reset --hard <baseline-sha>   # every accepted change is a named commit
```

---

## Architecture

```mermaid
flowchart LR
    Config[evolution.yml] --> Governor

    subgraph loop ["↻  Loop until hard stop fires"]
        direction LR
        Governor -->|"planner_input.json\ngoal · observation · history"| Planner["🧠 Planner\nLLM"]
        Planner -->|plan.json| Executor["🔨 Executor\nAider / Claude Code"]
        Executor -->|patch in git worktree| Evaluator["⚖️ Evaluator\nLLM + shell"]
        Evaluator -->|evaluation.json| Governor
    end

    Governor -->|"accept → git commit"| Branch["evolution/accepted"]
    Governor -->|"reject → discard"| Ledger[📁 Ledger]
    Governor --> Ledger
```

**The Governor is intentionally dumb.** It is pure orchestration — zero LLM calls. All intelligence lives in the three role scripts. Swap any role for your own implementation; the Governor only cares about the JSON each role reads and writes.

**Roles communicate through files, not shared memory.** The planner never talks to the executor. The evaluator never sees the executor's self-assessment. The only shared state is the ledger.

---

## What works today

| Feature | Status |
|---|:---:|
| Multi-round LLM loop with memory (history injection) | ✅ |
| Budget guards: `max_total_usd`, `max_total_tokens` | ✅ |
| Iteration / consecutive-failure hard stops | ✅ |
| Full ledger audit trail (survives process restarts) | ✅ |
| Git worktree sandbox — every attempt isolated | ✅ |
| Scope enforcement — rejects changes outside `allowed_paths` | ✅ |
| Config-driven: swap LLM provider, model, coding agent | ✅ |
| Aider and Claude Code executor support | ✅ |
| Anthropic and OpenAI planner/evaluator support | ✅ |
| Goal evaluator — stops when mission is "won" | 🔧 PR #5 |
| k-branch parallel exploration (FunSearch / AlphaEvolve style) | 🔧 PR #6 |
| Process sandbox (firejail / bwrap) for production safety | 🔧 PR #7 |

---

## Configuration reference

```yaml
# Required — what "better" means for your project
mission: "Evolve the game AI to win at least 60% of games"

# How to measure the current state
evidence_sources:
  - type: shell         # stdout goes into observation.json
    command: "python3 scripts/tournament.py --games 20 --json"
  - type: file          # file contents go into observation.json
    path: "metrics.json"

# Only files under these paths may be changed
mutation_scope:
  allowed_paths:
    - "ai/"             # changes outside this list are auto-rejected

# When to stop
hard_stops:
  max_iterations: 30            # total rounds
  max_consecutive_failures: 4   # consecutive rejections before halt
  max_total_usd: 3.00           # 0 = unlimited
  max_total_tokens: 0           # 0 = unlimited

# LLM for planner and evaluator
llm:
  provider: anthropic           # anthropic | openai
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY

# Coding agent for executor
coding_agent:
  tool: aider                   # aider | claude-code

# How many past rounds the planner sees
history:
  max_entries: 10

roles:
  planner:   ["python3", "roles/planner.py"]
  executor:  ["bash",    "roles/executor.sh"]
  evaluator: ["python3", "roles/evaluator.py"]
```

**Switch to OpenAI:**
```yaml
llm:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
```

**Switch to Claude Code:**
```yaml
coding_agent:
  tool: claude-code
```

---

## CLI

```bash
# Loop until a hard stop fires  (recommended)
evolution-kernel --config evolution.yml --repo /path/to/repo --ledger /tmp/ledger --loop

# Single round
evolution-kernel --config evolution.yml --repo /path/to/repo --ledger /tmp/ledger

# Reset budget counters after a halt
evolution-kernel --ledger /tmp/ledger --reset
```

Exit codes: `0` clean finish · `3` halted by a hard stop.

---

## Install

```bash
pip install evolution-kernel
```

From source (only runtime dependency: PyYAML):

```bash
git clone https://github.com/Protocol-zero-0/evolution-kernel.git
cd evolution-kernel
pip install -e .
```

Python 3.10 or later.

---

## Tests

```bash
python3 -m pytest tests/ -v
```

39 tests · no network calls · roles replaced by lightweight fixture scripts.

---

## Writing your own roles

Each role is an executable that receives:

```
--input    <path>    JSON the governor wrote for this role
--output   <path>    JSON the role must write before exiting
--worktree <path>    path to the isolated git sandbox checkout
```

`roles/planner.py`, `roles/executor.sh`, and `roles/evaluator.py` are the reference implementation. Copy, modify, or replace them entirely — with a shell script, a Docker call, or anything that reads `--input` and writes `--output`.

---

## Project layout

```
evolution_kernel/   ~1,200-line runtime  (Governor · Observer · HardStops · Config · CLI)
roles/              reference planner, executor, evaluator
examples/           demo target + working evolution.yml
docs/               protocol spec
tests/              39 unit + acceptance tests
```

---

## License

MIT — see [LICENSE](LICENSE).
