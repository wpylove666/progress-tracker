# Progress Tracker Skill — Design Spec

**Date**: 2026-05-29
**Status**: approved
**Approach**: B (SKILL.md + helper scripts)

## Overview

A Claude Code skill that tracks project progress via a nested task checklist. Tasks are auto-extracted from conversation context. Progress is stored as local JSON with optional GitHub Issue sync.

## File Layout

```
progress-tracker/
├── SKILL.md                  # Trigger rules, workflow, script invocation
├── scripts/
│   ├── progress.py           # CRUD + percentage calculation
│   └── sync.py               # Local ↔ GitHub Issue sync
└── assets/
    └── progress.schema.json  # Schema reference for the model
```

`progress.json` is created by scripts in the user's project root on demand.

## Data Model

```json
{
  "version": 1,
  "created": "2026-05-29T10:00:00+08:00",
  "updated": "2026-05-29T12:30:00+08:00",
  "tasks": [
    {
      "id": "t1",
      "title": "Lora Fine-tune Qwen2.5",
      "status": "in_progress",
      "children": [
        { "id": "t1.1", "title": "Prepare training data", "status": "done" },
        { "id": "t1.2", "title": "Configure hyperparameters", "status": "in_progress" },
        { "id": "t1.3", "title": "Start training", "status": "pending" },
        { "id": "t1.4", "title": "Evaluate model", "status": "pending" }
      ]
    }
  ]
}
```

Rules:
- Status: `pending` | `in_progress` | `done` (three states only)
- Max 2 levels (parent with children; children cannot have children)
- IDs use dotted hierarchy: `t1`, `t1.1`, `t1.2`
- Percentage is computed, not stored (children done / children total)
- `updated` changes on any status mutation

## Core Workflow

### Division of Labor

**Model (SKILL.md instructions) — 3 responsibilities:**
1. **Task extraction** — detect multi-step intent in conversation, propose task tree, wait for user confirmation
2. **Status awareness** — after each step completes (script finishes, training starts), update status
3. **Anomaly detection** — non-zero exit codes, prolonged silence → flag task and alert user

**Scripts — 2 responsibilities:**
1. `progress.py` — `init`, `update`, `show`, `alert`
2. `sync.py` — `push`, `pull`

### Constraints
- Tasks are NOT auto-created — model proposes, user confirms, then writes
- Only long-running or multi-step tasks are tracked; sub-second operations are ignored
- `progress.json` is found by walking up from CWD (max 3 levels)

## Script Interfaces

### progress.py

```bash
python progress.py init --title "Lora fine-tune" --subtasks "Prepare data,Config,Training,Eval"
python progress.py update --id t1.2 --status done
python progress.py show                # all tasks
python progress.py show --id t1        # single task tree
python progress.py alert --id t1.3 --msg "CUDA OOM at step 1500"
```

Exit 0 = success, non-0 = failure with stderr message.

### sync.py

```bash
python sync.py push    # local → GitHub Issue (create on first push, update after)
python sync.py pull    # GitHub Issue → local (overwrites local progress.json)
```

- `push` without `gh` authentication → error + instructions
- `push` in non-git directory → error + explanation
- `pull` overwrites local; warns before executing

## GitHub Sync Flow

1. First `push`: create a GitHub Issue titled "Progress: <project-name>", body = markdown checklist rendered from `progress.json`
2. Subsequent `push`: update the same Issue body with current state
3. `pull`: fetch Issue body, extract JSON block, overwrite local `progress.json`
4. Issue number tracked in `progress.json` (added by `push` after creation)
5. Fallback: if not a git repo or no GitHub remote, scripts error gracefully with clear messages

## Display Format (terminal output of `progress.py show`)

```
Progress Tracker — 2026-05-29 12:30

├── Lora 微调 Qwen2.5                    [==========        ] 50%
│   ├── [x] 准备训练数据
│   ├── [  ] 配置训练参数                ← in_progress
│   ├── [  ] 启动训练
│   └── [  ] 评估模型
│
└── RAG 数据清洗                          [                  ] 0%
    └── (no subtasks)

Total: 1/5 done (20%)
```

## Error Handling

| Scenario | Behavior |
|---|---|
| `progress.json` not found | Scripts print "No progress file in this project. Run `init` first." |
| Invalid task ID | Scripts print valid IDs and exit 1 |
| `push` without git repo | Error: "Not a git repository. sync requires a GitHub remote." |
| `push` without `gh` auth | Error: "Run `gh auth login` first." |
| `pull` with local changes | Warn: "This will overwrite local progress. Continue? (y/N)" |
| Corrupt JSON | Backup to `progress.json.bak`, print error, exit 1 |

## SKILL.md Outline

1. **Trigger conditions** — multi-step tasks, long-running operations, user asks for status
2. **Task extraction rules** — what constitutes a trackable task, confirmation gate
3. **Script invocation** — when and how to call each script
4. **Display format** — how to present progress to user
5. **Sync flow** — when to suggest/execute GitHub sync
