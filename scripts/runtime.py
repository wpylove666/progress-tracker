#!/usr/bin/env python3
"""Runtime Progress Reporter — decorator, tracker, and CLI for autonomous
progress reporting from Python training/inference/shell jobs.

Three interfaces, one file, zero external dependencies:
    1. @track(task_id)           — decorator for Python functions
    2. RuntimeTracker(task_id)   — manual tracker for loops / pipelines
    3. python runtime.py report  — CLI for shell scripts / non-Python jobs

Designed for: model fine-tuning, data processing, batch inference, RAG
pipelines, Agent workflows — any long-running, multi-phase AI task.
"""

import json
import os
import sys
import time
import argparse
import traceback
import functools
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
PROGRESS_FILE = "progress.json"
VALID_STATUSES = {"pending", "in_progress", "done"}


# ---------------------------------------------------------------------------
# Internal helpers — self-contained so runtime.py works standalone
# ---------------------------------------------------------------------------

def _find_progress_file():
    """Walk up from CWD to find progress.json (max 3 levels)."""
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


def _load_progress():
    """Find and load progress.json. Returns (path, data) or (None, None)."""
    path = _find_progress_file()
    if not path:
        return None, None
    with open(path, 'r', encoding='utf-8') as f:
        return path, json.load(f)


def _save_progress(path, data):
    """Write progress data, updating the timestamp."""
    data['updated'] = datetime.now(CST).isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')


def _find_task(tasks, task_id):
    """Find a task by ID. Returns (task, parent_list) or (None, None)."""
    for task in tasks:
        if task['id'] == task_id:
            return task, tasks
        if task.get('children'):
            for child in task['children']:
                if child['id'] == task_id:
                    return child, task['children']
    return None, None


def _find_parent_task(tasks, task_id):
    """Find the parent task of a subtask. Returns parent or None."""
    for task in tasks:
        if task.get('children'):
            for child in task['children']:
                if child['id'] == task_id:
                    return task
    return None


def _sync_parent(tasks, child_task_id):
    """Sync parent status after a child changes."""
    parent = _find_parent_task(tasks, child_task_id)
    if not parent or not parent.get('children'):
        return
    children = parent['children']
    if all(c['status'] == 'done' for c in children):
        parent['status'] = 'done'
    elif any(c['status'] == 'in_progress' for c in children):
        parent['status'] = 'in_progress'
    else:
        parent['status'] = 'pending'


def _safe(fn):
    """Decorator: catch all — progress failure must NOT crash the host task."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            pass
    return wrapper


# ---------------------------------------------------------------------------
# Core update logic
# ---------------------------------------------------------------------------

def _update_task(task_id, **fields):
    """Low-level: update task fields in progress.json. Never raises.

    Allowed fields: status, progress_pct, progress_msg, alert, clear_alert,
    started_at.
    """
    path, data = _load_progress()
    if not path or not data:
        return

    task, _ = _find_task(data['tasks'], task_id)
    if not task:
        return

    # Apply status
    if 'status' in fields and fields['status'] in VALID_STATUSES:
        old_status = task.get('status')
        task['status'] = fields['status']
        # Record when a task enters in_progress
        if fields['status'] == 'in_progress' and old_status != 'in_progress':
            if 'started_at' not in task:
                task['started_at'] = datetime.now(CST).isoformat()

    # Apply progress_pct
    if 'progress_pct' in fields and fields['progress_pct'] is not None:
        pct = int(fields['progress_pct'])
        task['progress_pct'] = max(0, min(100, pct))

    # Apply progress_msg
    if 'progress_msg' in fields and fields['progress_msg'] is not None:
        task['progress_msg'] = str(fields['progress_msg'])

    # Apply alert
    if 'alert' in fields and fields['alert'] is not None:
        task['alert'] = str(fields['alert'])

    # Clear alert
    if fields.get('clear_alert'):
        task.pop('alert', None)
        task.pop('progress_msg', None)

    # Sync parent
    _sync_parent(data['tasks'], task_id)

    _save_progress(path, data)


# ---------------------------------------------------------------------------
# Public API 1 — @track decorator
# ---------------------------------------------------------------------------

def track(task_id=None):
    """Decorator: auto-report a function's lifecycle to progress.json.

    Marks the task in_progress before the function runs, done after it
    returns, and sets an alert with the exception if it raises.

    Example:
        @track(task_id="t1.3")
        def train_model(epochs=10):
            for epoch in range(epochs):
                ...

    If task_id is omitted, the function's __name__ is used as the task ID.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            tid = task_id or fn.__name__
            _update_task(tid, status='in_progress',
                         progress_msg=f'Running {fn.__name__}...')
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                elapsed = time.time() - t0
                _update_task(tid, status='done', progress_pct=100,
                             progress_msg=f'Completed in {elapsed:.1f}s')
                return result
            except Exception:
                elapsed = time.time() - t0
                tb_lines = traceback.format_exc().strip().split('\n')
                short = tb_lines[-1] if tb_lines else str(sys.exc_info()[1])
                _update_task(tid, alert=f'[{elapsed:.0f}s] {short}')
                sys.stderr.write(f'[progress-tracker] {tid} FAILED: {short}\n')
                raise
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Public API 2 — RuntimeTracker class
# ---------------------------------------------------------------------------

class RuntimeTracker:
    """Manual progress tracker for loops and multi-phase operations.

    Example:
        tracker = RuntimeTracker(task_id="t1.3")
        tracker.start()
        for epoch in range(10):
            train_epoch()
            tracker.report(pct=(epoch+1)*10,
                          msg=f"Epoch {epoch+1}/10 complete")
        tracker.done()

    All methods are safe — failures are silently caught so training isn't
    interrupted.
    """

    def __init__(self, task_id):
        self.task_id = task_id
        self._start_time = None

    def start(self):
        """Mark the task as in_progress and record the start time."""
        self._start_time = time.time()
        _update_task(self.task_id, status='in_progress',
                     progress_pct=0, progress_msg='Starting...')

    def report(self, pct=None, msg=None):
        """Update the task's progress_pct and/or progress_msg.

        Call this at checkpoints: epoch boundaries, batch milestones, etc.
        pct: int 0–100
        msg: human-readable status string
        """
        _update_task(self.task_id, progress_pct=pct, progress_msg=msg)

    def done(self, msg=None):
        """Mark the task as done. Auto-computes elapsed time if no msg."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        final_msg = msg if msg else f'Completed in {elapsed:.1f}s'
        _update_task(self.task_id, status='done', progress_pct=100,
                     progress_msg=final_msg)

    def alert(self, msg):
        """Flag the task with an alert message (does NOT change status)."""
        _update_task(self.task_id, alert=str(msg))

    def fail(self, msg=None):
        """Mark the task with an alert AND reset to pending so it can retry."""
        error_msg = msg or 'Task failed'
        _update_task(self.task_id, alert=error_msg,
                     progress_msg=error_msg, clear_alert=False)

    def elapsed(self):
        """Return elapsed seconds since start() was called."""
        if self._start_time:
            return time.time() - self._start_time
        return 0


# ---------------------------------------------------------------------------
# Public API 3 — CLI
# ---------------------------------------------------------------------------

def _cmd_report(args):
    """Handle 'report' subcommand."""
    path, data = _load_progress()
    if not path or not data:
        print("ERROR: No progress.json found. Run 'init' first.",
              file=sys.stderr)
        sys.exit(1)

    task, _ = _find_task(data['tasks'], args.id)
    if not task:
        print(f"ERROR: Task '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)

    if args.status:
        if args.status not in VALID_STATUSES:
            print(f"ERROR: Invalid status '{args.status}'. "
                  f"Use: {', '.join(sorted(VALID_STATUSES))}",
                  file=sys.stderr)
            sys.exit(1)
        old = task.get('status')
        task['status'] = args.status
        if args.status == 'in_progress' and old != 'in_progress':
            task['started_at'] = datetime.now(CST).isoformat()

    if args.pct is not None:
        task['progress_pct'] = max(0, min(100, int(args.pct)))
    if args.msg:
        task['progress_msg'] = args.msg
    if args.alert:
        task['alert'] = args.alert
    if args.clear_alert:
        task.pop('alert', None)

    _sync_parent(data['tasks'], args.id)
    _save_progress(path, data)

    parts = [f"Reported: {task['title']}  status={task['status']}"]
    if 'progress_pct' in task:
        parts.append(f"pct={task['progress_pct']}%")
    print('  '.join(parts))


def _cmd_status(args):
    """Handle 'status' subcommand — quick status check."""
    _, data = _load_progress()
    if not data:
        print("ERROR: No progress.json found.", file=sys.stderr)
        sys.exit(1)

    task, _ = _find_task(data['tasks'], args.id)
    if not task:
        print(f"ERROR: Task '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)

    status = task['status']
    pct = task.get('progress_pct', '?')
    msg = task.get('progress_msg', '')
    alert = task.get('alert', '')

    print(f"{task['id']}: {task['title']}")
    print(f"  status={status}  pct={pct}%")
    if msg:
        print(f"  msg={msg}")
    if alert:
        print(f"  alert={alert}")


def _cmd_watch(args):
    """Handle 'watch' subcommand — block until a task is done or alert.

    Polls progress.json every N seconds. Useful in CI/CD pipelines.
    """
    interval = max(1, int(args.interval))
    timeout = int(args.timeout) if args.timeout else None
    t0 = time.time()

    while True:
        _, data = _load_progress()
        if not data:
            print("Waiting for progress.json...", flush=True)
            time.sleep(interval)
            continue

        task, _ = _find_task(data['tasks'], args.id)
        if not task:
            print(f"ERROR: Task '{args.id}' not found.", file=sys.stderr)
            sys.exit(1)

        status = task['status']
        pct = task.get('progress_pct', '?')
        msg = task.get('progress_msg', '')
        alert = task.get('alert', '')

        # Print status line
        now = datetime.now(CST).strftime('%H:%M:%S')
        print(f"[{now}] {task['title']}  {status}  {pct}%  {msg}",
              flush=True)

        if alert:
            print(f"  !! ALERT: {alert}")
            sys.exit(2)  # non-zero for CI to detect

        if status == 'done':
            print(f"  Done. ({task.get('progress_msg', '')})")
            sys.exit(0)

        if timeout and (time.time() - t0) > timeout:
            print(f"  Timeout after {timeout}s.", file=sys.stderr)
            sys.exit(3)

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description='Runtime progress reporter for AI tasks'
    )
    sub = parser.add_subparsers(dest='command')
    sub.required = True

    # report
    p_report = sub.add_parser('report', help='Report progress for a task')
    p_report.add_argument('--id', required=True, help='Task ID (e.g. t1.3)')
    p_report.add_argument('--status', choices=sorted(VALID_STATUSES),
                          help='Set task status')
    p_report.add_argument('--pct', type=int, metavar='0-100',
                          help='Progress percentage')
    p_report.add_argument('--msg', help='Progress message')
    p_report.add_argument('--alert', help='Alert message')
    p_report.add_argument('--clear-alert', action='store_true',
                          help='Remove existing alert')

    # status
    p_status = sub.add_parser('status', help='Quick status check')
    p_status.add_argument('--id', required=True, help='Task ID (e.g. t1.3)')

    # watch
    p_watch = sub.add_parser('watch', help='Block until task is done/alert')
    p_watch.add_argument('--id', required=True, help='Task ID to watch')
    p_watch.add_argument('--interval', default=5,
                         help='Poll interval in seconds (default: 5)')
    p_watch.add_argument('--timeout', default=None, type=int,
                         help='Max wait time in seconds')

    args = parser.parse_args()

    if args.command == 'report':
        _cmd_report(args)
    elif args.command == 'status':
        _cmd_status(args)
    elif args.command == 'watch':
        _cmd_watch(args)


if __name__ == '__main__':
    main()
