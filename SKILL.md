---
name: progress-tracker
description: Track multi-step AI task progress with a local checklist and optional GitHub Issue sync. Use this whenever the user describes a workflow with 2+ steps, starts a long-running command (training, inference, batch processing, data processing), asks about task status or progress, or mentions checklists, subtasks, or tracking progress — even if they don't explicitly ask for a progress tracker.
---

# Progress Tracker

Track multi-step AI tasks with a local `progress.json` file, automatic status updates, and optional GitHub Issue sync.

## Core Rules

1. **Detect, don't invent.** Only create tasks when the user has actual multi-step work — not for single commands or trivial one-liners. If there is only one step, there is nothing to track.

2. **Confirm before writing.** When you detect a multi-step workflow, print the proposed task tree and ask the user to confirm before running `init`. This avoids creating trackers the user did not want.

3. **Scripts are authoritative.** Always use the bundled scripts to read and write progress state. Never edit `progress.json` by hand — the scripts handle status transitions and parent-child consistency automatically.

4. **Update silently.** When a step completes during normal execution, update its status without announcing it to the user. Show progress only at milestones (a parent task reaches 100%), when the user explicitly asks, or on failure.

5. **Alert loudly on failure.** When a command exits non-zero, times out, or hits a known error, flag the task with an alert and tell the user immediately. Alerts persist in the tracker until the task is resolved.

## When to Trigger

Use this skill when any of these patterns appear:

- The user describes a workflow with 2 or more distinct steps
- The user starts a long-running command (model training, inference, data processing, batch job)
- The user asks "how is X going?", "what's the status?", or "where are we?"
- The user explicitly asks to track progress, create a checklist, or manage subtasks
- A task naturally decomposes into sequential phases that each need confirmation

## Script Reference

Scripts live in `scripts/` next to this SKILL.md. All commands operate on `progress.json` in the current project root. 

`<SKILL_DIR>` is the directory containing this SKILL.md — resolve it from the skill's install path (typically `~/.claude/skills/progress-tracker/` for manual installs).

### progress.py

```bash
# init - Create a new progress tracker with a top-level task and subtasks
python <SKILL_DIR>/scripts/progress.py init \
  --title "Fine-tune Qwen2.5" \
  --subtasks "Prepare data,Configure training,Start training,Evaluate model"

# update - Change a task status (auto-syncs parent)
python <SKILL_DIR>/scripts/progress.py update --id t1.2 --status done

# show - Display the full progress tree
python <SKILL_DIR>/scripts/progress.py show

# show - Display only one task and its children
python <SKILL_DIR>/scripts/progress.py show --id t1

# alert - Flag a task with an error or warning message
python <SKILL_DIR>/scripts/progress.py alert --id t1.3 --msg "CUDA OOM at step 1500, try reducing batch size"
```

Status values are `pending`, `in_progress`, and `done`. Task IDs use dotted hierarchy: `t1` (parent), `t1.1`, `t1.2` (children). Maximum depth is 2 levels.

### sync.py

```bash
# push - Sync local progress.json to a GitHub Issue (auto-detects or creates)
python <SKILL_DIR>/scripts/sync.py push

# pull - Download progress from a GitHub Issue and overwrite local file (confirms first)
python <SKILL_DIR>/scripts/sync.py pull
```

Sync requires the `gh` CLI to be authenticated and the project to have a GitHub remote. The Issue title is `Progress: <project-name>`.

## Workflows

### Starting a New Task

1. Detect that the user's request has 2+ distinct steps.
2. Propose a task tree in conversation: "I will track this: **Fine-tune Qwen2.5** with 4 subtasks: Prepare data, Configure training, Start training, Evaluate model. Create the tracker?"
3. On confirmation, run `progress.py init` with the title and comma-separated subtasks.
4. Show the result with `progress.py show` so the user sees the checklist.
5. Ask: "Want me to sync this to a GitHub Issue?" — do not push without asking.

### Updating During Execution

1. When a step completes, update its status to `done` immediately. Do not announce.
2. Mark the next step `in_progress` before starting it.
3. Only display the full tracker when:
   - A parent task reaches 100% (all children done) — milestone achieved
   - The user asks "how's it going?" or "show progress"
   - A failure occurs (see below)

### Handling Failures

1. When a command exits non-zero, times out, or produces a recognizable error, run `progress.py alert` with a short, actionable message.
2. Tell the user: "Task **<name>** hit an error: <message>. Marked in the progress tracker."
3. Run `progress.py show` so the user sees the full state including the alert.
4. Do not advance to the next step until the user confirms the issue is resolved.

### Syncing to GitHub

Suggest syncing when:
- The user explicitly asks to sync or push
- A major milestone is reached (parent task hits 100%)
- The session is ending and there are active (non-done) tasks

Always ask before pushing. Pulling overwrites the local file, so it always prompts for confirmation.

## Display Format

The `show` command renders a tree with progress bars and status markers:

```
Progress Tracker - 2026-05-29T14:30:00

+ Fine-tune Qwen2.5                       [====      ] 40%
    [x] Prepare data
    [x] Configure training
    [ ] Start training                     <- in progress
    [ ] Evaluate model

Total: 2/4 done (50%)
```

Markers: `[x]` done, `[ ]` pending, `<- in progress` for the active step. Alerted tasks show `!! <message>` appended. The bar is a 10-char visual scaled to the percentage.

## Data Model

The tracker writes a `progress.json` file at the project root. The full JSON Schema is at `<SKILL_DIR>/assets/progress.schema.json`.

Key constraints:
- Task tree is maximum 2 levels deep (parent tasks with children, no grandchildren)
- Each task has exactly one of three statuses: `pending`, `in_progress`, `done`
- Task IDs are auto-generated: `t1` for the first parent, `t1.1`, `t1.2` etc. for children
- Parent status is auto-computed from children: all done -> done, any in_progress -> in_progress, otherwise pending
- Percentages are computed from child statuses, never stored — no stale numbers
- Alerts are optional string fields that persist until the task is updated
