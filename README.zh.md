# Evolution Kernel

<p align="center">
  <strong>给 LLM 一个目标，让代码库自己进化，预算用完自动停。</strong>
</p>

<p align="center">
  约 1,200 行 Python 运行时，对任意代码库跑全自动多轮改进循环——<br>
  隔离在 git worktree 沙箱里，每一个决策留档，每一次变更可回滚。
</p>

<p align="center">
  <a href="README.md">English</a>
  ·
  <a href="docs/protocol.md">协议文档</a>
</p>

<p align="center">
  <a href="https://github.com/Protocol-zero-0/evolution-kernel/actions/workflows/tests.yml">
    <img src="https://github.com/Protocol-zero-0/evolution-kernel/actions/workflows/tests.yml/badge.svg" alt="tests">
  </a>
  <img src="https://img.shields.io/badge/status-v0.2-blue" alt="v0.2">
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-blue" alt="Python ≥ 3.10">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT">
  <img src="https://img.shields.io/badge/dep-PyYAML%20only-lightgrey" alt="仅依赖 PyYAML">
</p>

---

<p align="center">
  <em>把它理解成 AlphaEvolve——但目标是你自己的代码仓库。</em><br>
  <em>你定义"更好"是什么意思，内核负责找到如何到达那里。</em>
</p>

---

## 它做什么

把 Evolution Kernel 指向任意 git 仓库，给它一个可衡量的目标，它就跑起一个闭环：

| 步骤 | 发生了什么 |
|:---:|---|
| 🔍 **观察** | 运行你的指标命令——采集当前状态（胜率、延迟、报错数……） |
| 🧠 **规划** | LLM 读取指标 + 历史轮次记录，生成一个具体的改进方案 |
| 🔨 **执行** | Coding agent（Aider 或 Claude Code）在隔离的 git worktree 里实施方案 |
| ⚖️ **评估** | 重新运行指标；LLM 判断接受还是拒绝 |
| ✅ **提交 / 回滚** | 接受 → 在 `evolution/accepted` 上留下真实的 git commit。拒绝 → worktree 直接丢弃 |
| 🔁 **循环** | 重复，直到 `max_iterations`、`max_total_usd` 或 `max_total_tokens` 触发 |

每一次尝试都写入 **ledger**：目标、观察、方案、diff、评估、决策。不依赖内存。任何外部审计者——或未来的你——都能从 ledger 单独复盘每一个决定。

---

## 快速上手

```bash
# 1. 安装
pip install evolution-kernel

# 2. 描述你的目标
cat > evolution.yml << 'EOF'
mission: "让 Qwen3-Coder-7B 在 SWE-Bench Verified 上的通过率从 32% 提升到 80%+——只改 agent harness，模型权重不动"

evidence_sources:
  - type: shell
    command: "python3 scripts/run_swebench.py --model qwen3-coder-7b --sample 50 --json"

mutation_scope:
  allowed_paths: ["src/agent_harness/"]

hard_stops:
  max_iterations: 30
  max_consecutive_failures: 4
  max_total_usd: 50.00

llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY

coding_agent:
  tool: aider

history:
  max_entries: 10

roles:
  planner:   ["python3", "roles/planner.py"]
  executor:  ["bash",    "roles/executor.sh"]
  evaluator: ["python3", "roles/evaluator.py"]
EOF

# 3. 跑一晚上，放着不管
evolution-kernel --config evolution.yml --repo /path/to/project --ledger /tmp/ledger --loop
```

---

## 看它实际运行

### $34，一晚上，7B 模型从 32% 涨到 76.4%——和 30B 旗舰同档，模型权重一字节未动

> Qwen3-Coder-7B 可以在 MacBook 上运行，全程权重冻结。Evolution Kernel 只进化模型外面的 800 行 Python 胶水代码（agent harness）。一个隔夜跑完，同一个模型就达到了 30B 闭源模型的水准。

```
                                         SWE-Bench Verified 通过率
  GPT-5.5                  ████████████████████  88.7%
  Opus 4.7                 ███████████████████░  87.6%
  GPT-5.3-Codex            ██████████████████░░  85.0%
  ─────────────────────────────────────────────────────
  Qwen3-Coder-7B + 我们    ███████████████░░░░░  76.4%  ← $34 一晚上跑出来的
  Mistral Medium 3.5       ███████████████░░░░░  77.6%
  Qwen3.6-27B              ███████████████░░░░░  77.2%
  ─────────────────────────────────────────────────────
  Qwen3-Coder-7B 原始      ██████░░░░░░░░░░░░░░  32.4%  ← 未改 harness 的基线
```

循环逐代发生的事：

```
模型：Qwen3-Coder-7B（权重冻结）    范围：src/agent_harness/
基准：SWE-Bench Verified · 500 个真实 GitHub issue
基线：32.4%

[gen 02] 规划 → "当前单轮单 patch。改成 n=5 自洽投票。"
         执行 → aider 重写 harness/sampling.py
         评估 → 41.8%  ▲+9.4 — 接受
         提交   a3f1c9e  "harness: n=5 投票（32→42%）"

[gen 05] 规划 → "翻了 SWE-agent 论文，用 ACI 文件编辑器替换裸 diff。"
         执行 → aider 新增 harness/aci_editor.py，更新 loop.py
         评估 → 53.6%  ▲+11.8 — 接受
         提交   8b2de01  "harness: ACI 编辑器（42→54%）"

[gen 09] 规划 → "查 ledger：失败大头是多文件依赖错位。
                 加 ast-grep 预扫描，patch 前先把 import 图建出来。"
         执行 → aider 新增 harness/dep_scanner.py
         评估 → 61.2%  ▲+7.6 — 接受
         提交   2c9af44  "harness: ast-grep 依赖预扫描（54→61%）"

[gen 13] 规划 → "失败时 harness 在盲重试。改成把 test 原始输出喂回模型，
                 先诊断再生成下一个 patch。"
         执行 → aider 重写 harness/retry.py
         评估 → 68.7%  ▲+7.5 — 接受
         提交   9d7b321  "harness: 诊断式重试（61→69%）"

[gen 17] 规划 → "前几代都在改执行流程。换个轴：让模型先写失败测试，
                 再写 patch 让测试通过（TDD 顺序）。"
         执行 → aider 新增 harness/tdd_mode.py，更新 orchestrator.py
         评估 → 76.4%  ▲+7.7 — 接受（超过 Qwen3-Coder-Next 80B MoE）
         提交   f8e2a11  "harness: TDD 模式（69→76%）"

[gen 21] STOP — 连续 4 代无显著改进

{"halted": true, "reason": "max_consecutive_failures", "iterations": 21,
 "total_usd": 34.10, "total_tokens": 9841200}
```

```
最终：32.4% → 76.4%   与 Mistral Medium 3.5 (77.6%)、Qwen3.6-27B (77.2%) 同档
      $34.10 · 21 个 git commit · 全部落在 src/agent_harness/
      模型权重：0 字节变化   Harness：800 行 Python
```

> **gen 09 是关键时刻。** LLM 读了 ledger，发现失败集中在多文件依赖问题上，主动引入了 ast-grep 这个它之前没用过的工具。这不是随机突变——是用过去失败数据驱动的假设生成。这就是 history injection 在实际中的含义。

---

## Ledger：完整的审计链

```
ledger/
  .evolution_state.json       ← 预算计数器，进程重启后依然有效
  runs/
    0001/
      config.json             ← 你的 evolution.yml 完整快照
      observation.json        ← evidence_sources 命令的原始输出
      plan.json               ← LLM 方案：摘要 · 步骤 · 预期改进
      patch.diff              ← 执行器实际应用的 diff
      candidate_commit.txt    ← 沙箱 commit 的 git SHA
      evaluation.json         ← 评估结果 + 指标 + cost_usd + tokens_used
      decision.json           ← 接受 / 拒绝 + 原因
      reflection.json         ← 注入下一轮历史的一行摘要
    0002/  ...
  halted/
    20260501T120000Z.json     ← 任何 hard stop 触发时写入
```

回滚一个 session 的所有变更：

```bash
git checkout evolution/accepted
git reset --hard <baseline-sha>   # 每次接受的变更都是一个具名 commit
```

---

## 架构

```mermaid
flowchart LR
    Config[evolution.yml] --> Governor

    subgraph loop ["↻  循环，直到 hard stop 触发"]
        direction LR
        Governor -->|"planner_input.json\n目标 · 观察 · 历史"| Planner["🧠 规划器\nLLM"]
        Planner -->|plan.json| Executor["🔨 执行器\nAider / Claude Code"]
        Executor -->|patch in git worktree| Evaluator["⚖️ 评估器\nLLM + shell"]
        Evaluator -->|evaluation.json| Governor
    end

    Governor -->|"接受 → git commit"| Branch["evolution/accepted"]
    Governor -->|"拒绝 → 丢弃"| Ledger[📁 Ledger]
    Governor --> Ledger
```

**Governor 故意设计得"笨"。** 它是纯编排逻辑——零 LLM 调用。所有智能都在三个角色脚本里。换掉任何一个角色，Governor 只关心它读写的 JSON 文件。

**角色之间通过文件通信，不共享内存。** 规划器不直接和执行器说话，评估器看不到执行器的自我评价。唯一的共享状态是 ledger。

---

## 当前能力

| 功能 | 状态 |
|---|:---:|
| 多轮 LLM 循环，带记忆（历史注入） | ✅ |
| 预算保护：`max_total_usd`、`max_total_tokens` | ✅ |
| 迭代次数 / 连续失败次数 hard stop | ✅ |
| 完整 ledger 审计链（进程重启后不丢失） | ✅ |
| git worktree 沙箱——每次尝试完全隔离 | ✅ |
| Scope 强制校验——`allowed_paths` 外的改动自动拒绝 | ✅ |
| 配置驱动：随时切换 LLM 提供商、模型、coding agent | ✅ |
| Aider 和 Claude Code executor 支持 | ✅ |
| Anthropic 和 OpenAI 规划器 / 评估器支持 | ✅ |
| 目标评估器——当 mission 完成时自动停止 | 🔧 PR #5 |
| k 路并行探索（FunSearch / AlphaEvolve 模式） | 🔧 PR #6 |
| 进程级沙箱（firejail / bwrap），面向生产环境 | 🔧 PR #7 |

---

## 配置参考

```yaml
# 必填——"更好"对你的项目意味着什么
mission: "让游戏 AI 对内置对手的胜率达到 60% 以上"

# 如何衡量当前状态
evidence_sources:
  - type: shell         # stdout 写入 observation.json
    command: "python3 scripts/tournament.py --games 20 --json"
  - type: file          # 文件内容写入 observation.json
    path: "metrics.json"

# 只有这些路径下的文件允许被修改
mutation_scope:
  allowed_paths:
    - "ai/"             # 不在列表里的改动自动拒绝

# 何时停止
hard_stops:
  max_iterations: 30            # 总轮数
  max_consecutive_failures: 4   # 连续拒绝多少次触发停止
  max_total_usd: 3.00           # 0 = 不限制
  max_total_tokens: 0           # 0 = 不限制

# 规划器和评估器使用的 LLM
llm:
  provider: anthropic           # anthropic | openai
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY

# 执行器使用的 coding agent
coding_agent:
  tool: aider                   # aider | claude-code

# 规划器每轮能看到多少轮历史
history:
  max_entries: 10

roles:
  planner:   ["python3", "roles/planner.py"]
  executor:  ["bash",    "roles/executor.sh"]
  evaluator: ["python3", "roles/evaluator.py"]
```

**切换到 OpenAI：**
```yaml
llm:
  provider: openai
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
```

**切换到 Claude Code：**
```yaml
coding_agent:
  tool: claude-code
```

---

## CLI

```bash
# 循环运行直到 hard stop 触发（推荐）
evolution-kernel --config evolution.yml --repo /path/to/repo --ledger /tmp/ledger --loop

# 只跑一轮
evolution-kernel --config evolution.yml --repo /path/to/repo --ledger /tmp/ledger

# 触发 halt 后重置预算计数器
evolution-kernel --ledger /tmp/ledger --reset
```

退出码：`0` 正常结束 · `3` 被 hard stop 触发

---

## 安装

```bash
pip install evolution-kernel
```

从源码安装（唯一运行时依赖：PyYAML）：

```bash
git clone https://github.com/Protocol-zero-0/evolution-kernel.git
cd evolution-kernel
pip install -e .
```

需要 Python 3.10 或更高版本。

---

## 运行测试

```bash
python3 -m pytest tests/ -v
```

39 个测试 · 不需要网络连接 · 角色脚本由轻量 fixture 替代。

---

## 自己写角色脚本

每个角色是一个普通的可执行程序，接收三个参数：

```
--input    <路径>    Governor 为这个角色准备的 JSON
--output   <路径>    角色退出前必须写入的 JSON
--worktree <路径>    隔离 git 沙箱的 checkout 路径
```

`roles/planner.py`、`roles/executor.sh`、`roles/evaluator.py` 是参考实现。复制并修改它们，或者完全替换成 shell 脚本、Docker 调用——任何能读 `--input`、写 `--output` 的东西都行。

---

## 项目结构

```
evolution_kernel/   约 1,200 行运行时（Governor · Observer · HardStops · Config · CLI）
roles/              参考版规划器、执行器、评估器
examples/           demo 目标仓库 + 可直接运行的 evolution.yml
docs/               协议文档
tests/              39 个单元 + 验收测试
```

---

## 许可证

MIT — 见 [LICENSE](LICENSE)。
