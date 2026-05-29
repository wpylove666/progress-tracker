# Progress Tracker — Claude Code Skill

AI task progress tracking with nested checklists, auto-detected from conversation context.

## What It Does

Tracks multi-step AI workflows (fine-tuning, data processing, batch inference, Agent pipelines) with real-time progress feedback:

- **Auto-detects** tasks from conversation — no manual input needed
- **Nested checklists** (2-level) with auto-computed percentages
- **Silent updates** during execution, **alerts on failure**
- **GitHub Issue sync** — push progress to a live Issue for team visibility
- **100% Python stdlib** — no external dependencies

## Install

```bash
# Clone into skills directory
git clone https://github.com/wpylove666/progress-tracker.git ~/.claude/skills/progress-tracker
```

Claude Code auto-discovers skills in `~/.claude/skills/`. Restart Claude Code or start a new conversation.

## Quick Start

Start a multi-step task naturally in conversation:

```
> I need to fine-tune Qwen2.5: prepare data, config LoRA, train, evaluate, export
```

Claude will detect the workflow and propose a task tree. Confirm, and the tracker is live.

## Commands

### progress.py — Local Progress

```bash
python progress.py init --title "Task" --subtasks "A,B,C"
python progress.py update --id t1.2 --status done
python progress.py show
python progress.py alert --id t1.3 --msg "CUDA OOM at step 1500"
```

### sync.py — GitHub Issue Sync

```bash
python sync.py push    # Local → GitHub Issue
python sync.py pull    # GitHub Issue → Local
```

Requires: git repo + `gh auth login`.

## Requirements

- Python 3.10+
- `gh` CLI (for sync only, optional)

## File Structure

```
progress-tracker/
├── SKILL.md                  # Skill definition + workflow instructions
├── scripts/
│   ├── progress.py           # init / update / show / alert (Skill layer)
│   ├── sync.py               # push / pull (GitHub Issues)
│   └── runtime.py            # @track / RuntimeTracker / CLI (Runtime layer)
└── assets/
    └── progress.schema.json  # JSON Schema for progress.json (v2)
```

## How It Works

1. You describe multi-step work → Claude detects it
2. Claude proposes a task tree → you confirm
3. `progress.json` is written to your project root
4. As steps complete, statuses update silently
5. Failures trigger alerts with context
6. Optional: sync to GitHub Issue for team visibility

## Example

```
Progress Tracker - 2026-05-29T14:30

+ Fine-tune Qwen2.5                       [====      ] 40%
    [x] Prepare training data
    [x] Configure hyperparameters
    [ ] Start training                     ← in progress
    [ ] Evaluate model

Total: 2/4 done (50%)
```

## Runtime Layer

The **Runtime layer** (`scripts/runtime.py`) lets your Python training/inference code report progress autonomously — no AI conversation needed. Three interfaces:

### 1. `@track` Decorator

```python
from runtime import track

@track(task_id="t1.3")
def train_model(epochs=10):
    for epoch in range(epochs):
        ...

# Before: marks t1.3 as in_progress
# After (success): marks t1.3 as done
# After (exception): sets alert on t1.3, re-raises
```

### 2. `RuntimeTracker` Class

```python
from runtime import RuntimeTracker

tracker = RuntimeTracker(task_id="t1.3")
tracker.start()                         # in_progress, 0%

for epoch in range(10):
    train_epoch()
    tracker.report(pct=(epoch+1)*10,    # 10%, 20%, ...
                   msg=f"Epoch {epoch+1}/10")

tracker.done()                          # done, 100%
```

### 3. CLI (Shell / Non-Python)

```bash
python runtime.py report --id t1.3 --status in_progress --pct 60 --msg "Batch 600/1000"
python runtime.py status  --id t1.3
python runtime.py watch   --id t1.3 --interval 5 --timeout 3600
```

`watch` blocks until the task is `done` or gets an `alert` — useful in CI/CD.

**Design:** 100% stdlib; all update methods catch exceptions silently so progress reporting never crashes your training job.

## Changelog

### v0.2.0 — Runtime Layer (2026-05-30)

**新增：`scripts/runtime.py`** — 让训练/推理任务自主上报进度，无需 AI 对话介入。

| 接口 | 说明 | 作用 |
|---|---|---|
| `@track(task_id)` 装饰器 | import 后装饰函数 | 函数执行前自动标记 `in_progress`，成功返回标记 `done`，抛异常自动写入 `alert` |
| `RuntimeTracker` 类 | `start()` → `report()` → `done()` | 训练循环内手动上报百分比和状态消息，静默失败不影响主任务 |
| CLI `report/status/watch` | `python runtime.py report --id t1.3 --pct 60` | Shell 脚本和非 Python 任务直接调用，`watch` 子命令阻塞等待任务完成（CI/CD 用） |

**底层改动：**
- `progress.py show` — 展示 Runtime 上报的 `progress_pct` 和 `progress_msg`
- `sync.py` — GitHub Issue body 渲染 Runtime 进度信息
- JSON Schema → v2：新增 `started_at`、`progress_pct`、`progress_msg` 可选字段
- `README.md` / `SKILL.md` — 补充 Runtime 层文档

**设计原则：** 100% stdlib 零依赖，所有更新方法静默捕获异常——进度上报失败绝不崩溃训练作业。

---

### v0.1.0 — Skill Layer (2026-05-29)

首次发布。对话驱动的进度管理：
- `progress.py` — `init` / `update` / `show` / `alert` 本地任务树
- `sync.py` — `push` / `pull` 与 GitHub Issue 双向同步
- `SKILL.md` — Claude Code skill 触发规则与工作流
- 两层嵌套任务树，自动计算百分比，失败告警

---

## Related

Part of a two-layer system:
- **Skill layer** — `progress.py` + `sync.py` + `SKILL.md` — conversation-driven task management
- **Runtime layer** — `runtime.py` — autonomous progress reporting from Python/Shell jobs
