## Evidence

This directory contains **reproducible, checked-in evidence** that Evolution Kernel is real, runnable code with an auditable design — not just a README narrative.

It exists alongside the README's "See it in action" section, which describes an *illustrative* GSM8K scenario (a design target, not a checked-in run). The artifacts here are different: they describe **what's actually inside this repo today**, anchored to specific files, tests, commits, and a real end-to-end run anyone can verify in under ten minutes.

> **Reproducibility note.** The 2026-05-14 demo run used the `claude_cli` LLM provider, which is merged on `main` and will ship in **v1.2.0**. Until then, reproduce from a `git clone` of this repo. Everything else in this directory (architecture snapshot, walkthrough, ledger structure) is reproducible against v1.1.2 today.

---

## What's here

### [`demo-target-run-2026-05-14/`](demo-target-run-2026-05-14/)

A real end-to-end run of the kernel against [`examples/demo_target`](../examples/demo_target/), driven entirely through the local Claude Code CLI (`claude -p`) — **no `ANTHROPIC_API_KEY` required**. The kernel halted itself after 3 consecutive rejections, spending $0.11 of a $10 budget. The self-stop is the point: this run demonstrates the planner reading history and changing direction, the evaluator rejecting "syntactically correct but useless" patches, and the hard-stop logic firing on the kernel's own terms.

| File | What it shows |
|---|---|
| [`README.md`](demo-target-run-2026-05-14/README.md) | Narrated case study: setup, run-by-run timeline, why a self-halted run is stronger evidence than a successful one, exact reproduction commands. |
| [`evolution-cli.yml`](demo-target-run-2026-05-14/evolution-cli.yml) | The exact config used (the new `claude_cli` provider; $10 budget; src/ scope). |
| [`run.log`](demo-target-run-2026-05-14/run.log) | Raw kernel stdout/stderr from the run. |
| [`ledger/`](demo-target-run-2026-05-14/ledger/) | Complete audit trail: per-run plan/patch/evaluation/decision/reflection JSON (3 runs × 12 files each), plus `.evolution_state.json`, `halted/`, `failed/`. Total: 47 files, 232 KB. |

### [`repo-snapshot-2026-05-13/`](repo-snapshot-2026-05-13/)

A point-in-time snapshot of the repository as of 2026-05-13, after stages 0–3 were merged and v0.3.0 was tagged:

| File | What it shows |
|---|---|
| [`architecture.md`](repo-snapshot-2026-05-13/architecture.md) | The 8-module, ~1,800-LOC runtime; the 5 role scripts; the 4-stage PR history that built it. With exact file paths and line counts. |
| [`test-output.txt`](repo-snapshot-2026-05-13/test-output.txt) | Raw transcript of `python3 -m pytest tests/ -v`. **83 tests pass in ~25s, no network calls.** (Counted before PR7a/PR7b landed; latest count is 99 — re-run the suite to verify.) |
| [`walkthrough.md`](repo-snapshot-2026-05-13/walkthrough.md) | A 5-minute terminal walkthrough — commands you can copy-paste to see the kernel's anatomy directly: config schema, role protocol, scope enforcement, ledger structure. No API key required. |

---

## What about the GSM8K story in the README?

The "$34 / overnight / 51.8% → 96.2%" GSM8K story in the main README is a **design narrative** — a description of what a complete, well-targeted run on a real benchmark looks like, given the kernel's current capabilities. It is *not* a checked-in run artifact, and the math_solver_harness it references is not part of this repository. We've added an "Illustrative scenario" banner to the README's hero section to make this boundary explicit.

A real, reproducible run on a non-toy target is on the roadmap — when one is produced, its full ledger will be deposited here under a new dated subfolder, the same way [`demo-target-run-2026-05-14/`](demo-target-run-2026-05-14/) is laid out.
