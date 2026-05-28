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
│   ├── progress.py           # init / update / show / alert
│   └── sync.py               # push / pull (GitHub Issues)
└── assets/
    └── progress.schema.json  # JSON Schema for progress.json
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

## Related

Part of a two-layer system:
- **Skill layer** (this repo) — conversation-driven task management
- **Runtime layer** (coming soon) — Python decorator/CLI for autonomous progress reporting from training/inference jobs
