# Evolution Kernel

[English](README.md) | 中文

**Evolution Kernel** 是一个面向“自主自我进化软件系统”的最小协议与运行时设计。

它的核心定位是一个**通用的进化引擎**，旨在持续优化**任何**软件项目。它提供了一个标准化的闭环，用于自主地提出、执行和评估代码变更。

## 首个优化对象

虽然 Evolution Kernel 被设计为通用的，但它优化的第一个目标系统是 **Token-Ignition**（具体为其后端评估器）。Token-Ignition 作为首个用例，用于验证该内核安全、确定性地进化代码库的能力。

## 目前做到了什么 (v0 现状)

当前的 v0 版本实现了基础的运行时能力：
- **确定性 Governor**：编排进化循环，管理账本（ledger），并处理实验的晋升与回滚。
- **基于 Git 的沙箱版本管理**：使用 Git worktree 隔离实验，在明确接受前不会影响主仓库。
- **基于文件的角色交接**：通过隔离的命令（`planner`、`executor`、`evaluator`）和 JSON 文件（`plan.json`、`evaluation.json`）实现清晰的职责分离。
- **Token-Ignition 适配器**：一个极简的适配器，包含手写的黄金测试集（golden set），用于评估 Token-Ignition 系统的进化结果。

## 下一步需要做什么 (Roadmap)

- [ ] **LLM 接入**：实现真正基于大语言模型的 Planner 和 Executor（目前测试中使用的是 mock 脚本）。
- [ ] **强化沙箱隔离**：为 `executor` 和 `evaluator` 提供超越 Git worktree 的更强隔离机制（如 Docker/容器化执行）。
- [ ] **更多项目适配器**：扩展 Token-Ignition 之外的用例，支持优化更多类型的项目和工作流。
- [ ] **高级回滚与分支策略**：支持并行的进化分支和更复杂的合并策略。

## 文档

- [协议](docs/protocol.md)
- [Token-Ignition 首个任务](docs/token-ignition-first-task.md)

## 运行测试

```bash
python3 -m unittest discover -s tests -v
python3 adapters/token_ignition/evaluate_golden_cases.py
```

## CLI 形状

```bash
python3 -m evolution_kernel.cli \
  --repo /path/to/target-repo \
  --ledger /path/to/evolution-ledger \
  --goal /path/to/goal.json \
  --planner python3 /path/to/planner.py \
  --executor python3 /path/to/executor.py \
  --evaluator python3 /path/to/evaluator.py
```

每个角色命令都会收到：

```text
--input <json>
--output <json>
--worktree <sandbox path>
```
