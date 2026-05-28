# Progress Tracker Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill that tracks multi-step AI task progress via nested checklists, stored as local JSON with optional GitHub Issue sync.

**Architecture:** Two Python scripts (`progress.py` for CRUD + display, `sync.py` for GitHub Issue sync) with a `SKILL.md` that instructs the model when to trigger the skill and how to invoke each script. Progress data lives in `progress.json` at the project root.

**Tech Stack:** Python 3.12 (stdlib only — json, os, sys, argparse, subprocess, datetime, re, pathlib), GitHub CLI (`gh`), Claude Code skill system.

---

## File Structure

```
progress-tracker/
├── SKILL.md                  # Skill trigger + workflow instructions
├── scripts/
│   ├── progress.py           # init, update, show, alert commands
│   └── sync.py               # push, pull to/from GitHub Issues
└── assets/
    └── progress.schema.json  # JSON Schema for progress.json validation
```

---

### Task 1: Create Directory Structure and Schema

**Files:**
- Create: `~/.claude/skills/progress-tracker/assets/progress.schema.json`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p ~/.claude/skills/progress-tracker/scripts ~/.claude/skills/progress-tracker/assets
```

- [ ] **Step 2: Write `assets/progress.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Progress Tracker",
  "type": "object",
  "required": ["version", "created", "updated", "tasks"],
  "properties": {
    "version": { "type": "integer", "const": 1 },
    "created": { "type": "string", "format": "date-time" },
    "updated": { "type": "string", "format": "date-time" },
    "github_issue": { "type": "integer" },
    "tasks": {
      "type": "array",
      "items": { "$ref": "#/$defs/task" }
    }
  },
  "$defs": {
    "task": {
      "type": "object",
      "required": ["id", "title", "status"],
      "properties": {
        "id": { "type": "string", "pattern": "^t\\d+(\\.\\d+)?$" },
        "title": { "type": "string" },
        "status": { "enum": ["pending", "in_progress", "done"] },
        "alert": { "type": "string" },
        "children": {
          "type": "array",
          "items": { "$ref": "#/$defs/subtask" }
        }
      }
    },
    "subtask": {
      "type": "object",
      "required": ["id", "title", "status"],
      "properties": {
        "id": { "type": "string", "pattern": "^t\\d+\\.\\d+$" },
        "title": { "type": "string" },
        "status": { "enum": ["pending", "in_progress", "done"] },
        "alert": { "type": "string" }
      }
    }
  }
}
```

---

### Task 2: Write `progress.py` Script

**Files:**
- Create: `~/.claude/skills/progress-tracker/scripts/progress.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Progress Tracker — manage multi-step AI task checklists.

Commands:
    init     Create a new progress.json with task tree
    update   Change a task's status (pending/in_progress/done)
    show     Display progress tree with completion bars
    alert    Flag a task with an alert message
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
PROGRESS_FILE = "progress.json"


def find_progress_file():
    """Walk up from CWD to find progress.json (max 3 levels up)."""
    path = os.getcwd()
    for _ in range(4):
        candidate = os.path.join(path, PROGRESS_FILE)
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def load_progress():
    """Find and load progress.json. Exits with message if not found."""
    path = find_progress_file()
    if not path:
        print(
            f"ERROR: No {PROGRESS_FILE} found in this project. Run 'init' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        return path, json.load(f)


def save_progress(path, data):
    """Write progress data to file, updating timestamp."""
    data['updated'] = datetime.now(CST).isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def find_task(tasks, task_id):
    """Find a task by ID. Returns (task, parent_list) or (None, None)."""
    for task in tasks:
        if task['id'] == task_id:
            return task, tasks
        if task.get('children'):
            for child in task['children']:
                if child['id'] == task_id:
                    return child, task['children']
    return None, None


def find_parent_task(tasks, task_id):
    """Find the parent task of a given subtask ID. Returns parent or None."""
    for task in tasks:
        if task.get('children'):
            for child in task['children']:
                if child['id'] == task_id:
                    return task
    return None


def compute_pct(task):
    """Compute completion percentage from children statuses."""
    if not task.get('children'):
        return 100 if task['status'] == 'done' else 0
    done = sum(1 for c in task['children'] if c['status'] == 'done')
    return int(done / len(task['children']) * 100) if task['children'] else 0


def update_parent_status(tasks, child_task_id):
    """After a child status changes, sync the parent's status."""
    parent = find_parent_task(tasks, child_task_id)
    if not parent or not parent.get('children'):
        return
    children = parent['children']
    if all(c['status'] == 'done' for c in children):
        parent['status'] = 'done'
    elif any(c['status'] == 'in_progress' for c in children):
        parent['status'] = 'in_progress'
    else:
        parent['status'] = 'pending'


def cmd_init(args):
    """Create a new progress.json in the current directory."""
    path = os.path.join(os.getcwd(), PROGRESS_FILE)
    if os.path.exists(path):
        print(
            f"ERROR: {PROGRESS_FILE} already exists. Use 'update' to modify.",
            file=sys.stderr,
        )
        sys.exit(1)

    subtitles = (
        [s.strip() for s in args.subtasks.split(',') if s.strip()]
        if args.subtasks
        else []
    )
    children = []
    for i, title in enumerate(subtitles, 1):
        children.append({"id": f"t1.{i}", "title": title, "status": "pending"})

    data = {
        "version": 1,
        "created": datetime.now(CST).isoformat(),
        "updated": datetime.now(CST).isoformat(),
        "tasks": [
            {
                "id": "t1",
                "title": args.title,
                "status": "pending",
                "children": children,
            }
        ],
    }

    save_progress(path, data)
    pct = compute_pct(data['tasks'][0])
    print(f"Created: {args.title} [{pct}%]")
    for c in children:
        print(f"  - [ ] {c['title']}")


def cmd_update(args):
    """Update a task's status and auto-sync parent."""
    path, data = load_progress()
    task, _ = find_task(data['tasks'], args.id)
    if not task:
        print(f"ERROR: Task '{args.id}' not found. Valid IDs:", file=sys.stderr)
        for t in data['tasks']:
            print(f"  {t['id']}: {t['title']}", file=sys.stderr)
            for c in t.get('children', []):
                print(f"    {c['id']}: {c['title']}", file=sys.stderr)
        sys.exit(1)

    old_status = task['status']
    task['status'] = args.status
    update_parent_status(data['tasks'], args.id)
    save_progress(path, data)
    print(f"Updated: {task['title']}  {old_status} -> {args.status}")


def cmd_show(args):
    """Display the progress tree with bars and percentages."""
    _, data = load_progress()
    print(f"Progress Tracker - {data['updated'][:16]}")
    print()

    tasks_to_show = data['tasks']
    if args.id:
        task, _ = find_task(data['tasks'], args.id)
        if not task:
            print(f"ERROR: Task '{args.id}' not found.", file=sys.stderr)
            sys.exit(1)
        tasks_to_show = [task]

    total_done = 0
    total_count = 0

    for task in tasks_to_show:
        pct = compute_pct(task)
        n = min(pct // 10, 10)
        bar = '=' * n + ' ' * (10 - n)

        extra_map = {
            'done': '',
            'in_progress': '  <- in progress',
            'pending': '',
        }

        print(f"+ {task['title']:40s} [{bar}] {pct}%")
        for child in task.get('children', []):
            marker = '[x]' if child['status'] == 'done' else '[ ]'
            extra = extra_map.get(child['status'], '')
            alert = f" !! {child['alert']}" if child.get('alert') else ''
            print(f"    {marker} {child['title']:34s}{extra}{alert}")
            if child['status'] == 'done':
                total_done += 1
            total_count += 1
        if not task.get('children'):
            print("    (no subtasks)")
        print()

    if total_count > 0:
        overall = int(total_done / total_count * 100)
        print(f"Total: {total_done}/{total_count} done ({overall}%)")


def cmd_alert(args):
    """Flag a task with an alert message."""
    path, data = load_progress()
    task, _ = find_task(data['tasks'], args.id)
    if not task:
        print(f"ERROR: Task '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)
    task['alert'] = args.msg
    save_progress(path, data)
    print(f"ALERT: {task['title']} - {args.msg}")


def main():
    parser = argparse.ArgumentParser(description='Progress tracker for AI projects')
    sub = parser.add_subparsers(dest='command')
    sub.required = True

    p_init = sub.add_parser('init', help='Create new progress.json')
    p_init.add_argument('--title', required=True, help='Top-level task title')
    p_init.add_argument(
        '--subtasks', default='', help='Comma-separated subtask titles'
    )

    p_update = sub.add_parser('update', help='Update a task status')
    p_update.add_argument('--id', required=True, help='Task ID (e.g. t1, t1.2)')
    p_update.add_argument(
        '--status',
        required=True,
        choices=['pending', 'in_progress', 'done'],
        help='New status',
    )

    p_show = sub.add_parser('show', help='Display progress')
    p_show.add_argument('--id', default=None, help='Optional: show only this task')

    p_alert = sub.add_parser('alert', help='Flag a task with an alert')
    p_alert.add_argument('--id', required=True, help='Task ID to flag')
    p_alert.add_argument('--msg', required=True, help='Alert message')

    args = parser.parse_args()

    commands = {
        'init': cmd_init,
        'update': cmd_update,
        'show': cmd_show,
        'alert': cmd_alert,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Test `init`**

```bash
cd /tmp && rm -f progress.json
python ~/.claude/skills/progress-tracker/scripts/progress.py init --title "Test Task" --subtasks "Step A,Step B,Step C"
# Expected: prints "Created: Test Task [0%]" with 3 subtasks

python ~/.claude/skills/progress-tracker/scripts/progress.py init --title "Dup" 2>&1
# Expected: ERROR: progress.json already exists
```

- [ ] **Step 3: Test `show`**

```bash
python ~/.claude/skills/progress-tracker/scripts/progress.py show
# Expected: tree with Test Task [          ] 0%, three [ ] subtasks
```

- [ ] **Step 4: Test `update` and auto parent sync**

```bash
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.1 --status done
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.2 --status in_progress
python ~/.claude/skills/progress-tracker/scripts/progress.py show
# Expected: t1.1 [x], t1.2 [ ]  <- in progress, parent bar shows 33%
```

- [ ] **Step 5: Test `alert`**

```bash
python ~/.claude/skills/progress-tracker/scripts/progress.py alert --id t1.3 --msg "CUDA OOM at step 1500"
python ~/.claude/skills/progress-tracker/scripts/progress.py show
# Expected: t1.3 shows "!! CUDA OOM at step 1500"
```

- [ ] **Step 6: Test error cases**

```bash
# Invalid task ID
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t99 --status done 2>&1
# Expected: ERROR with valid ID list, exit 1

# progress.json not found
cd /tmp && rm -f progress.json
python ~/.claude/skills/progress-tracker/scripts/progress.py show 2>&1
# Expected: ERROR: No progress.json found, exit 1
```

---

### Task 3: Write `sync.py` Script

**Files:**
- Create: `~/.claude/skills/progress-tracker/scripts/sync.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Sync progress.json with GitHub Issues.

Commands:
    push    Render progress as markdown, create or update a GitHub Issue
    pull    Fetch Issue body, extract JSON, overwrite local progress.json
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
PROGRESS_FILE = "progress.json"


def find_progress_file():
    """Walk up from CWD to find progress.json (max 3 levels up)."""
    path = os.getcwd()
    for _ in range(4):
        candidate = os.path.join(path, PROGRESS_FILE)
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def check_git():
    """Verify we're in a git repository."""
    try:
        subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "ERROR: Not a git repository. sync requires a GitHub remote.",
            file=sys.stderr,
        )
        sys.exit(1)


def check_gh_auth():
    """Verify gh CLI is authenticated."""
    try:
        subprocess.run(
            ['gh', 'auth', 'status'], capture_output=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "ERROR: gh CLI not authenticated. Run 'gh auth login' first.",
            file=sys.stderr,
        )
        sys.exit(1)


def format_issue_body(data):
    """Render progress data as a markdown Issue body with embedded JSON."""
    lines = ["# Progress Tracker\n"]
    for task in data['tasks']:
        children = task.get('children', [])
        done = sum(1 for c in children if c['status'] == 'done')
        total = max(len(children), 1)
        pct = int(done / total * 100) if children else (
            100 if task['status'] == 'done' else 0
        )
        lines.append(f"## {task['title']} ({pct}%)\n")
        for child in children:
            marker = 'x' if child['status'] == 'done' else ' '
            note = ' ← in progress' if child['status'] == 'in_progress' else ''
            alert = f" ⚠ {child['alert']}" if child.get('alert') else ''
            lines.append(f"- [{marker}] {child['title']}{note}{alert}")
        if not children:
            status_note = {
                'done': 'Completed',
                'in_progress': 'In progress',
                'pending': 'Not started',
            }.get(task['status'], '')
            lines.append(f"Status: {status_note}")
        lines.append('')

    lines.append('---')
    lines.append(f"Updated: {data['updated']}")
    lines.append('')
    lines.append(
        '```json\n' + json.dumps(data, indent=2, ensure_ascii=False) + '\n```'
    )
    return '\n'.join(lines)


def find_or_create_issue(title, body):
    """Find an existing open issue by title, or create a new one.
    Returns the issue number."""
    result = subprocess.run(
        [
            'gh', 'issue', 'list', '--search', f'"{title}"', '--state', 'open',
            '--json', 'number', '--limit', '1',
        ],
        capture_output=True, text=True,
    )
    try:
        issues = json.loads(result.stdout)
        if issues:
            number = issues[0]['number']
            subprocess.run(
                ['gh', 'issue', 'edit', str(number), '--body', body], check=True
            )
            return number
    except (json.JSONDecodeError, subprocess.CalledProcessError):
        pass

    # Create new issue
    result = subprocess.run(
        ['gh', 'issue', 'create', '--title', title, '--body', body],
        capture_output=True, text=True, check=True,
    )
    match = re.search(r'/issues/(\d+)', result.stdout)
    if match:
        return int(match.group(1))
    print(f"Created issue but could not parse number from:\n{result.stdout}")
    sys.exit(1)


def cmd_push():
    """Push local progress.json to a GitHub Issue."""
    progress_path = find_progress_file()
    if not progress_path:
        print(
            f"ERROR: No {PROGRESS_FILE} found in this project. Run 'init' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    check_git()
    check_gh_auth()

    with open(progress_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    project_name = os.path.basename(os.path.dirname(progress_path))
    title = f"Progress: {project_name}"
    body = format_issue_body(data)

    issue_number = find_or_create_issue(title, body)

    # Save issue number back to progress.json
    data['github_issue'] = issue_number
    data['updated'] = datetime.now(CST).isoformat()
    with open(progress_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f"Synced to Issue #{issue_number}: {title}")


def cmd_pull():
    """Pull progress from GitHub Issue and overwrite local progress.json."""
    check_git()
    check_gh_auth()

    progress_path = os.path.join(os.getcwd(), PROGRESS_FILE)
    if os.path.exists(progress_path):
        print("WARNING: This will overwrite local progress.json. Continue? (y/N)")
        response = input().strip().lower()
        if response != 'y':
            print("Aborted.")
            sys.exit(0)

    project_name = os.path.basename(os.getcwd())
    title = f"Progress: {project_name}"
    result = subprocess.run(
        [
            'gh', 'issue', 'list', '--search', f'"{title}"', '--state', 'open',
            '--json', 'number,body', '--limit', '1',
        ],
        capture_output=True, text=True,
    )

    try:
        issues = json.loads(result.stdout)
        if not issues:
            print(
                f"ERROR: No open issue found with title '{title}'.",
                file=sys.stderr,
            )
            sys.exit(1)

        body = issues[0]['body']
        match = re.search(r'```json\n(.*?)\n```', body, re.DOTALL)
        if not match:
            print(
                "ERROR: Could not find JSON block in Issue body.",
                file=sys.stderr,
            )
            sys.exit(1)

        data = json.loads(match.group(1))
        data['github_issue'] = issues[0]['number']
        data['updated'] = datetime.now(CST).isoformat()
        with open(progress_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n')

        print(f"Synced from Issue #{issues[0]['number']} to {PROGRESS_FILE}")
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in Issue body: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('push', 'pull'):
        print("Usage: python sync.py <push|pull>", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == 'push':
        cmd_push()
    else:
        cmd_pull()
```

- [ ] **Step 2: Test `push` without git**

```bash
cd /tmp && python ~/.claude/skills/progress-tracker/scripts/sync.py push 2>&1
# Expected: ERROR: Not a git repository
```

- [ ] **Step 3: Test `pull` overwrite warning (in a git repo)**

```bash
cd ~/my-git-project && python ~/.claude/skills/progress-tracker/scripts/sync.py pull
# Type "n" at prompt
# Expected: Aborted.
```

---

### Task 4: Write `SKILL.md`

**Files:**
- Create: `~/.claude/skills/progress-tracker/SKILL.md`

- [ ] **Step 1: Write the SKILL.md**

```markdown
---
name: progress-tracker
description: Track multi-step AI task progress with nested checklists, auto-generated from conversation context. Use when the user starts a long-running task (model fine-tuning, data processing, batch inference, Agent workflows, RAG pipelines), mentions multi-step plans, or asks about task status. Creates a local progress.json with completion percentages and optional GitHub Issue sync for real-time tracking.
---

# Progress Tracker

Track AI project progress with structured checklists. Tasks are auto-extracted from conversation context — use when the user describes multi-step or long-running work.

## Core Rules

1. **Detect, don't invent.** Only create tasks when the user actually describes multi-step work. Don't suggest tracking for single, trivial operations.
2. **Confirm before writing.** Print the proposed task tree and wait for user approval before running `init`.
3. **Scripts are authoritative.** All progress data mutations go through the scripts — never directly edit `progress.json` by hand.
4. **Update silently on success.** When a step completes, update its status automatically. The user shouldn't need to say "update the progress."
5. **Alert loudly on failure.** Non-zero exit codes, timeouts, or explicit errors → flag the task with `alert` and tell the user.

## When to Trigger

- User describes a workflow with 2+ distinct steps (e.g., "first do X, then Y, then Z")
- User asks about task/progress status ("how's the training going?", "what's left?")
- A long-running command (training, inference, data processing) has been started
- User explicitly asks for progress tracking ("track this", "make a checklist")

## Script Reference

Scripts live at `~/.claude/skills/progress-tracker/scripts/`. Use the full path. All scripts use Python 3 (stdlib only).

### progress.py — Local Progress Management

```bash
# Create a new progress tracker (ONE top-level task with subtasks)
python ~/.claude/skills/progress-tracker/scripts/progress.py init \
  --title "Fine-tune Qwen2.5" \
  --subtasks "Prepare data,Configure training,Start training,Evaluate model"

# Update a task status (auto-updates parent)
python ~/.claude/skills/progress-tracker/scripts/progress.py update \
  --id t1.2 --status done

# Show current progress
python ~/.claude/skills/progress-tracker/scripts/progress.py show

# Show only one task tree
python ~/.claude/skills/progress-tracker/scripts/progress.py show --id t1

# Flag an alert on a task
python ~/.claude/skills/progress-tracker/scripts/progress.py alert \
  --id t1.3 --msg "CUDA OOM at step 1500"
```

Status values: `pending`, `in_progress`, `done`. Task IDs use dotted notation (`t1`, `t1.1`, `t1.2`).

### sync.py — GitHub Issue Sync

```bash
# Push local progress to a GitHub Issue
python ~/.claude/skills/progress-tracker/scripts/sync.py push

# Pull progress from GitHub Issue (overwrites local)
python ~/.claude/skills/progress-tracker/scripts/sync.py pull
```

Requirements for sync: must be in a git repo with `gh` CLI authenticated.

## Workflows

### Workflow 1: Starting a New Task

1. User describes multi-step work
2. Propose a task tree: "I'll track this: [title] with N subtasks: [list]. Create?"
3. User confirms → run `progress.py init`
4. Show the created tree via `progress.py show`
5. Ask: "Want me to sync this to a GitHub Issue?"

### Workflow 2: Updating During Execution

1. A step completes → run `progress.py update --id <id> --status done` immediately
2. A new step starts → run `progress.py update --id <id> --status in_progress`
3. Don't announce every update — only show `progress.py show` when:
   - A parent task reaches 100% (milestone)
   - The user asks for status
   - Something fails

### Workflow 3: Handling Failures

1. Command exits non-zero or times out → run `progress.py alert --id <current_id> --msg "<error summary>"`
2. Tell the user clearly: "Task '<name>' hit an error: <msg>. Marked in progress tracker."
3. Show the current state: `progress.py show`

### Workflow 4: Syncing to GitHub

Suggest sync when:
- User explicitly asks ("sync progress", "push to GitHub")
- A major milestone is reached (parent task hits 100%)
- The session is ending with active tasks

```bash
python ~/.claude/skills/progress-tracker/scripts/sync.py push
```

## Display Format

When showing progress to the user, prefer running `progress.py show` over manually formatting — it produces consistent output:

```
Progress Tracker - 2026-05-29T12:30

+ Fine-tune Qwen2.5                       [====      ] 40%
    [x] Prepare training data
    [ ] Configure hyperparameters          <- in progress
    [ ] Start training
    [ ] Evaluate model

Total: 1/4 done (25%)
```

## Data Model

Progress is stored in `progress.json` at the project root. Schema at `~/.claude/skills/progress-tracker/assets/progress.schema.json`.

Key rules:
- Max 2 levels (parent → children; children cannot nest further)
- 3 states only: `pending`, `in_progress`, `done`
- IDs: `t1`, `t1.1`, `t1.2` (dotted hierarchy)
- Percentage is always computed from children, never stored
- `progress.json` is found by walking up from CWD (max 3 levels)
```

- [ ] **Step 2: Validate SKILL.md frontmatter**

```bash
python -c "
import yaml
with open('$HOME/.claude/skills/progress-tracker/SKILL.md') as f:
    content = f.read()
    # Extract YAML frontmatter
    _, fm, _ = content.split('---', 2)
    data = yaml.safe_load(fm)
    assert 'name' in data
    assert 'description' in data
    print('Frontmatter valid:', data['name'])
"
```

---

### Task 5: End-to-End Integration Test

- [ ] **Step 1: Full workflow test**

```bash
# Clean start
cd /tmp && rm -f progress.json

# Init
python ~/.claude/skills/progress-tracker/scripts/progress.py init \
  --title "Integration Test" \
  --subtasks "Step 1,Step 2,Step 3"

# Verify JSON structure
python -c "
import json
d = json.load(open('/tmp/progress.json'))
assert d['version'] == 1
assert len(d['tasks']) == 1
assert len(d['tasks'][0]['children']) == 3
print('JSON structure OK')
"

# Progress through all steps
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.1 --status done
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.2 --status in_progress
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.2 --status done
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.3 --status in_progress
python ~/.claude/skills/progress-tracker/scripts/progress.py alert --id t1.3 --msg "Test alert"

# Show final state
python ~/.claude/skills/progress-tracker/scripts/progress.py show

# Verify parent auto-sync: 2/3 done, parent should be in_progress
python -c "
import json
d = json.load(open('/tmp/progress.json'))
parent = d['tasks'][0]
assert parent['status'] == 'in_progress', f'Expected in_progress, got {parent[\"status\"]}'
assert d['tasks'][0]['children'][0]['status'] == 'done'
assert d['tasks'][0]['children'][1]['status'] == 'done'
assert d['tasks'][0]['children'][2]['alert'] == 'Test alert'
print('All assertions passed')
"

# Complete last step
python ~/.claude/skills/progress-tracker/scripts/progress.py update --id t1.3 --status done

# Verify parent auto-sync to done
python -c "
import json
d = json.load(open('/tmp/progress.json'))
assert d['tasks'][0]['status'] == 'done', f'Expected done, got {d[\"tasks\"][0][\"status\"]}'
print('Parent auto-sync to done OK')
"
```

- [ ] **Step 2: Clean up test artifacts**

```bash
rm -f /tmp/progress.json
```
