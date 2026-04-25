# Evolution Kernel

[English](README.md) | 中文

Evolution Kernel 是一个面向“自主自我进化软件系统”的最小协议与运行时设计。

第一个宿主系统是 Token-Ignition 的后端评估器：一个自主评审系统，目标是在保持实现小、可复现、可沙箱化、可审计的前提下，持续提升识别高潜力 AI-native Builder 的能力。

当前 v0 包含确定性 governor、基于 Git 的沙箱版本管理、基于文件的角色交接，以及手写的 Token-Ignition golden set。

## 文档

- [协议](docs/protocol.md)
- [Token-Ignition 首个任务](docs/token-ignition-first-task.md)

## V0 运行时

运行时由四个部分组成：

- `governor`: 确定性编排、Git worktree、ledger、晋升与回滚
- `planner`: 隔离执行，输出 `plan.json`
- `executor`: 隔离执行，仅修改沙箱 worktree
- `evaluator`: 隔离执行，输出 `evaluation.json`

晋升不会移动目标仓库的 main 分支，而是将本地 `evolution/accepted` 分支指向候选提交。被拒绝的实验仍保留在 ledger 中，但不会推进 `evolution/accepted`。

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

## Token-Ignition 适配器

第一个适配器刻意保持极简：

- `adapters/token_ignition/golden_cases.json`
- `adapters/token_ignition/evaluate_golden_cases.py`

它定义了 6 类对抗样例，用于评估器进化：强但极简的进化、仅提示词包装、不可复现的 Demo、过度复杂的 swarm、真实但偏弱的系统、对基准过拟合。
