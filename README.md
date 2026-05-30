<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/dependencies-0-green.svg" alt="Zero Dependencies">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/platform-Claude%20Code-purple.svg" alt="Claude Code">
</p>

# progress-tracker

**让 AI 执行的每一个任务，进度可见、状态可查、失败可追溯。**

A two-layer progress tracking system for Claude Code — Skill layer for conversation-driven task management, Runtime layer for autonomous reporting from training/inference jobs.

---

## 为什么需要它？ / The Problem

用 Claude Code 做复杂任务时：

- 😵 AI 执行到一半上下文被压缩，进度信息丢失
- 🤷 挂着的训练/推理任务，不知道跑到哪一步了
- 😤 任务失败了没有记录，排查全靠猜

`progress-tracker` 解决的就是这个问题：**让多步骤 AI 任务从"黑盒"变成"仪表盘"**。

---

## 两层架构 / Two Layers

```
┌─────────────────────────────────────────────────────┐
│  Skill Layer (对话驱动)                               │
│  AI 自动识别多步骤任务 → 创建清单 → 自动更新状态        │
│  progress.py + sync.py + SKILL.md                     │
├─────────────────────────────────────────────────────┤
│  Runtime Layer (代码自主上报)                          │
│  @track 装饰器 / RuntimeTracker / CLI                  │
│  训练脚本无需 AI 介入，自主报告进度                     │
│  runtime.py                                           │
└─────────────────────────────────────────────────────┘
```

### Skill Layer — AI 对话驱动

你只需要正常描述任务，AI 自动检测并创建进度跟踪：

```
👤 我要微调 Qwen2.5：准备数据 → 配置 LoRA → 训练 → 评估 → 导出

🤖 检测到 5 步工作流，建议创建进度跟踪：

   + 微调 Qwen2.5
       [ ] 准备训练数据
       [ ] 配置 LoRA 参数
       [ ] 启动训练
       [ ] 评估模型
       [ ] 导出模型

   创建？[Y/n]
```

执行过程中：
- ✅ 步骤完成 → 静默更新，不打扰你
- ❌ 步骤失败 → 立即告警，附加上下文
- 📊 随时问"进度如何"→ 显示完整进度树

### Runtime Layer — 代码自主上报

训练/推理脚本无需 AI 对话介入，自主报告进度：

```python
# 方式 1: 装饰器，一行搞定
from runtime import track

@track(task_id="t1.3")
def train_model(epochs=10):
    for epoch in range(epochs):
        ...

# 方式 2: 手动控制，训练循环内上报
from runtime import RuntimeTracker

tracker = RuntimeTracker(task_id="t1.3")
tracker.start()
for epoch in range(10):
    train_epoch()
    tracker.report(pct=(epoch+1)*10, msg=f"Epoch {epoch+1}/10")
tracker.done()
```

```bash
# 方式 3: CLI，Shell 脚本也能用
python runtime.py report --id t1.3 --pct 60 --msg "Batch 600/1000"
python runtime.py watch  --id t1.3 --interval 5 --timeout 3600
```

---

## 快速开始 / Quick Start

```bash
# 1. 安装（克隆到 skills 目录）
git clone https://github.com/wpylove666/progress-tracker.git ~/.claude/skills/progress-tracker

# 2. 重启 Claude Code，然后在对话中描述一个多步骤任务
#    例如："帮我做三件事：整理数据、训练模型、生成报告"

# 3. AI 自动检测并提议创建进度跟踪，你确认即可
```

**就这么简单。** 不需要配置，不需要 API Key，不需要数据库。

---

## 命令速查 / Commands

### `progress.py` — 本地进度管理

```bash
python progress.py init   --title "任务名" --subtasks "A,B,C"   # 创建
python progress.py update --id t1.2 --status done               # 更新状态
python progress.py show                                         # 查看全部
python progress.py show   --id t1                               # 查看某个
python progress.py alert  --id t1.3 --msg "CUDA OOM at step 1500"  # 标记告警
```

### `sync.py` — GitHub Issue 同步

```bash
python sync.py push   # 本地 → GitHub Issue（团队可见）
python sync.py pull   # GitHub Issue → 本地
```

需要：git 仓库 + `gh auth login`

---

## 终端效果 / Demo

```
Progress Tracker - 2026-05-30T14:30:00

+ 微调 Qwen2.5                              [====      ] 40%
    [x] 准备训练数据
    [x] 配置 LoRA 参数
    [ ] 启动训练                              ← in progress
    [ ] 评估模型

Total: 2/4 done (50%)
```

---

## 设计原则 / Design

| 原则 | 说明 |
|------|------|
| **零依赖** | 100% Python 标准库，`pip install` 都不需要 |
| **静默失败** | 进度上报失败绝不崩溃你的训练任务 |
| **本地优先** | 数据存本地 `progress.json`，GitHub Sync 可选 |
| **两层解耦** | Skill 层和 Runtime 层独立运作，互不依赖 |

---

## 文件结构 / Structure

```
progress-tracker/
├── SKILL.md                   # Skill 定义 + AI 触发规则
├── README.md                  # 你正在看
├── LICENSE                    # MIT
├── scripts/
│   ├── progress.py            # init / update / show / alert
│   ├── sync.py                # push / pull (GitHub Issues)
│   └── runtime.py             # @track / RuntimeTracker / CLI
└── assets/
    └── progress.schema.json   # JSON Schema v2
```

---

## 版本历史 / Changelog

### v0.2.0 — Runtime Layer (2026-05-30)

新增 `runtime.py`，训练/推理脚本可自主上报进度，无需 AI 介入：

- `@track(task_id)` 装饰器 — 自动标记函数生命周期
- `RuntimeTracker` 类 — 训练循环内手动上报
- CLI `report/status/watch` — Shell 和非 Python 任务也能用
- `progress_pct` / `progress_msg` / `started_at` 字段支持

### v0.1.0 — Skill Layer (2026-05-29)

首次发布：对话驱动的进度管理 + GitHub Issue 同步。

---

## 适用场景 / Use Cases

- 🏋️ 模型微调/训练（多 epoch，需要跟踪进度）
- 📊 批量数据处理（多阶段 pipeline）
- 🤖 Claude Code Agent 工作流（多步骤自动化）
- 🔧 任何需要"知道跑到哪了"的长时间 AI 任务

---

## 贡献 / Contributing

项目刚起步，欢迎 Issue、PR、Star ⭐

如果你觉得有用，也欢迎分享给其他 Claude Code 用户。

---

<p align="center">
  <b>Built with ❤️ for the Claude Code community</b><br>
  <sub>0 dependency · 100% stdlib · MIT licensed</sub>
</p>
