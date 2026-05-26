## 5-minute walkthrough

A copy-pasteable terminal session that lets anyone see Evolution Kernel's anatomy in five minutes. **No API key required** — every command here reads source code, runs the test suite, or inspects the protocol.

If you want to see the closed loop actually execute against an LLM, use [`examples/demo_target`](../../examples/demo_target/) with `ANTHROPIC_API_KEY` set — that's a separate ~30-minute exercise documented in the main [`README.md`](../../README.md#quick-start).

---

### 0. Clone and install (~30s)

```bash
git clone https://github.com/Protocol-zero-0/evolution-kernel.git
cd evolution-kernel
pip install -e .
```

Single runtime dependency: PyYAML. Python ≥ 3.10.

---

### 1. Verify the kernel works — run the test suite (~25s)

```bash
python3 -m pytest tests/ -v
```

Expected last line:

```
============================= 83 passed in ~25s ==============================
```

Full transcript: [`test-output.txt`](test-output.txt).

The suite mocks all LLM endpoints — no API key, no network. If 83 tests pass, the kernel's logic (Governor, scope, hard stops, ledger, role dispatch, k-branch parallel, goal evaluator) is verified end-to-end.

---

### 2. Look at the Governor — confirm it has no LLM calls

```bash
wc -l evolution_kernel/governor.py
grep -c "anthropic\|openai" evolution_kernel/governor.py
```

Expected:

```
673 evolution_kernel/governor.py
0
```

673 lines of pure orchestration. Zero LLM imports. All intelligence is delegated to the role scripts.

---

### 3. Look at the role protocol — confirm roles are external processes

```bash
ls roles/
cat roles/planner.py | head -40
```

Five role scripts. Each is launched as a subprocess and reads/writes JSON files. Swap any one of them with a script that respects the same protocol and the kernel doesn't care.

```bash
cat docs/protocol.md | head -60
```

The protocol document explicitly separates "Governor / Planner / Executor / Evaluator" into four roles, each with a "must do" and "must not do" list.

---

### 4. Look at the config — confirm goals are declarative

```bash
cat examples/evolution.yml
```

A real, runnable config. `mission` defines the goal in natural language; `evidence_sources` is how the kernel measures progress; `mutation_scope.allowed_paths` is enforced (the kernel rejects any change outside it); `hard_stops` is the budget guard.

---

### 5. Look at the demo target — confirm it's self-contained

```bash
ls examples/demo_target/
cat examples/demo_target/metrics.json
cat examples/demo_target/scripts/status.sh
```

A toy target repository bundled with the kernel. Its evaluator is a local Python script reading `metrics.json` — **no external LLM needed for the target itself**, only the kernel's planner/evaluator/executor call Anthropic.

---

### 6. Look at the build history — confirm the staged delivery

```bash
git log --oneline | head -10
git tag
```

Expected:

```
818860b chore: bump version to 0.3.0 (#16)
cd4aa06 feat: k-branch parallel exploration (closes #14) (#15)
683ec6e feat: goal evaluator + strategist (closes #10) (#13)
...
4658aa6 feat: MVP closed loop — observer, scope, hard stops, ledger (PR #2)

v0.3.0
```

Four merged stages over four days; v0.3.0 cut on 2026-05-13. Detail in [`architecture.md`](architecture.md).

---

## What you've now verified, without spending a cent on API calls

- ✅ The kernel installs from a clean clone with one dependency
- ✅ 83 tests pass — Governor, scope, hard stops, ledger, k-branch parallel, goal evaluator
- ✅ The Governor genuinely has no LLM imports — separation of routing from intelligence is real, not aspirational
- ✅ Roles are external processes with a documented JSON protocol — pluggable, not hard-coded
- ✅ The config schema, mutation scope enforcement, and hard-stop budget guards are concrete code
- ✅ A self-contained demo target is in the repo — you can run the real loop next, with one Anthropic API key

Total time: under 5 minutes.
