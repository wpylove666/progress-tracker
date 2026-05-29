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
VALID_STATUSES = {"pending", "in_progress", "done"}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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
    """Find and load progress.json. Exits with message if not found.

    Returns (path, data) tuple.
    """
    path = find_progress_file()
    if not path:
        print(
            f"ERROR: No {PROGRESS_FILE} found in this project. "
            "Run 'init' first.",
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
    """Find a task by ID. Returns (task, parent_list) or (None, None).

    Searches both top-level tasks and children.
    """
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
    """Calculate completion percentage from children's statuses.

    Tasks without children: 100% if done, 0% otherwise.
    Tasks with children: done_count / total_children * 100.
    """
    if not task.get('children'):
        return 100 if task['status'] == 'done' else 0
    children = task['children']
    done = sum(1 for c in children if c['status'] == 'done')
    return int(done / len(children) * 100) if children else 0


def update_parent_status(tasks, child_task_id):
    """After a child status changes, sync the parent's status.

    Rules:
        All children done  → parent = done
        Any in_progress    → parent = in_progress
        Otherwise          → parent = pending
    """
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


def _collect_valid_ids(tasks):
    """Collect all task IDs (top-level + children) for error messages."""
    ids = []
    for t in tasks:
        ids.append((t['id'], t['title']))
        for c in t.get('children', []):
            ids.append((c['id'], c['title']))
    return ids


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_init(args):
    """Create a new progress.json in the current directory."""
    path = os.path.join(os.getcwd(), PROGRESS_FILE)
    if os.path.exists(path):
        print(
            f"ERROR: {PROGRESS_FILE} already exists. "
            "Use 'update' to modify.",
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

    now = datetime.now(CST).isoformat()
    data = {
        "version": 2,
        "created": now,
        "updated": now,
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
    task, _parent_list = find_task(data['tasks'], args.id)

    if not task:
        print(
            f"ERROR: Task '{args.id}' not found. Valid IDs:",
            file=sys.stderr,
        )
        for tid, ttitle in _collect_valid_ids(data['tasks']):
            depth = "    " if '.' in tid else "  "
            print(f"  {depth}{tid}: {ttitle}", file=sys.stderr)
        sys.exit(1)

    old_status = task['status']
    task['status'] = args.status
    update_parent_status(data['tasks'], args.id)
    save_progress(path, data)
    print(f"Updated: {task['title']}  {old_status} -> {args.status}")


def cmd_show(args):
    """Display the progress tree with bars, percentages, and runtime info."""
    _path, data = load_progress()
    print(f"Progress Tracker - {data['updated'][:16]}")
    print()

    tasks_to_show = data['tasks']
    if args.id:
        task, _ = find_task(data['tasks'], args.id)
        if not task:
            print(
                f"ERROR: Task '{args.id}' not found.",
                file=sys.stderr,
            )
            sys.exit(1)
        tasks_to_show = [task]

    total_done = 0
    total_count = 0

    for task in tasks_to_show:
        # Use runtime progress_pct if available, otherwise compute from children
        runtime_pct = task.get('progress_pct')
        pct = runtime_pct if runtime_pct is not None else compute_pct(task)
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

            # Runtime progress info
            c_pct = child.get('progress_pct')
            c_msg = child.get('progress_msg')
            runtime = ''
            if c_pct is not None and child['status'] == 'in_progress':
                runtime = f'  ({c_pct}%'
                if c_msg:
                    runtime += f' — {c_msg}'
                runtime += ')'

            print(f"    {marker} {child['title']:34s}{extra}{alert}{runtime}")
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
    task, _parent_list = find_task(data['tasks'], args.id)

    if not task:
        print(
            f"ERROR: Task '{args.id}' not found. Valid IDs:",
            file=sys.stderr,
        )
        for tid, ttitle in _collect_valid_ids(data['tasks']):
            depth = "    " if '.' in tid else "  "
            print(f"  {depth}{tid}: {ttitle}", file=sys.stderr)
        sys.exit(1)

    task['alert'] = args.msg
    save_progress(path, data)
    print(f"ALERT: {task['title']} - {args.msg}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Progress tracker for AI projects'
    )
    sub = parser.add_subparsers(dest='command')
    sub.required = True

    # init
    p_init = sub.add_parser('init', help='Create new progress.json')
    p_init.add_argument('--title', required=True, help='Top-level task title')
    p_init.add_argument(
        '--subtasks',
        default='',
        help='Comma-separated subtask titles',
    )

    # update
    p_update = sub.add_parser('update', help='Update a task status')
    p_update.add_argument('--id', required=True, help='Task ID (e.g. t1, t1.2)')
    p_update.add_argument(
        '--status',
        required=True,
        choices=sorted(VALID_STATUSES),
        help='New status',
    )

    # show
    p_show = sub.add_parser('show', help='Display progress')
    p_show.add_argument(
        '--id', default=None, help='Optional: show only this task'
    )

    # alert
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
