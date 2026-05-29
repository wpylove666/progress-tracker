#!/usr/bin/env python3
"""Progress Tracker — sync progress.json with GitHub Issues.

Commands:
    push     Push local progress.json to a GitHub Issue
    pull     Pull progress from a GitHub Issue to local progress.json
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
PROGRESS_FILE = "progress.json"


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


def check_git():
    """Verify we are in a git repo. Prints error to stderr and exits on failure."""
    try:
        subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            check=True,
            encoding='utf-8', errors='replace',
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "ERROR: Not a git repository. sync requires a GitHub remote.",
            file=sys.stderr,
        )
        sys.exit(1)


def check_gh_auth():
    """Verify gh CLI is authenticated. Prints error to stderr and exits on failure."""
    try:
        subprocess.run(
            ['gh', 'auth', 'status'],
            capture_output=True,
            check=True,
            encoding='utf-8', errors='replace',
        )
    except FileNotFoundError:
        print(
            "ERROR: gh CLI not authenticated. Run 'gh auth login' first.",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.CalledProcessError:
        print(
            "ERROR: gh CLI not authenticated. Run 'gh auth login' first.",
            file=sys.stderr,
        )
        sys.exit(1)


def compute_pct(task):
    """Calculate completion percentage for a task.

    Tasks without children: 100% if done, 0% otherwise.
    Tasks with children: done_count / total_children * 100.
    """
    if not task.get('children'):
        return 100 if task['status'] == 'done' else 0
    children = task['children']
    if not children:
        return 100 if task['status'] == 'done' else 0
    done = sum(1 for c in children if c['status'] == 'done')
    return int(done / len(children) * 100)


def format_issue_body(data):
    """Render progress data as a markdown Issue body."""
    lines = ['# Progress Tracker', '']

    for task in data.get('tasks', []):
        pct = compute_pct(task)
        lines.append(f'## {task["title"]} ({pct}%)')
        lines.append('')
        for child in task.get('children', []):
            marker = '[x]' if child['status'] == 'done' else '[ ]'
            if child['status'] == 'in_progress':
                pct = child.get('progress_pct')
                if pct is not None:
                    extra = f' ← {pct}%'
                else:
                    extra = ' ← in progress'
            elif child.get('progress_msg'):
                extra = f' — {child["progress_msg"]}'
            else:
                extra = ''
            alert = f' ⚠ {child["alert"]}' if child.get('alert') else ''
            lines.append(f'- {marker} {child["title"]}{extra}{alert}')
        if not task.get('children'):
            status_label = {
                'done': 'Done',
                'in_progress': 'In progress',
                'pending': 'Pending',
            }.get(task['status'], task['status'])
            lines.append(f'Status: {status_label}')
        lines.append('')

    lines.append('---')
    lines.append(f'Updated: {data.get("updated", datetime.now(CST).isoformat())}')
    lines.append('')
    lines.append('```json')
    lines.append(json.dumps(data, indent=2, ensure_ascii=False))
    lines.append('```')

    return '\n'.join(lines)


def find_or_create_issue(title, body):
    """Search for an existing open issue with the given title.

    If found, update its body. Otherwise, create a new issue.
    Returns the issue number (int).
    """
    # Search for existing open issue with this exact title
    result = subprocess.run(
        ['gh', 'issue', 'list', '--state', 'open',
         '--search', f'{title} in:title',
         '--limit', '1',
         '--json', 'number',
         '--jq', '.[0].number'],
        capture_output=True,
        encoding='utf-8', errors='replace',
    )

    issue_number_str = result.stdout.strip() if result.returncode == 0 else ''

    if issue_number_str:
        # Issue already exists — update its body
        number = int(issue_number_str)
        subprocess.run(
            ['gh', 'issue', 'edit', str(number), '--body', body],
            capture_output=True,
            check=True,
            encoding='utf-8', errors='replace',
        )
        return number
    else:
        # No existing issue — create a new one
        result = subprocess.run(
            ['gh', 'issue', 'create', '--title', title, '--body', body],
            capture_output=True,
            check=True,
            encoding='utf-8', errors='replace',
        )
        output = result.stdout.strip()
        # Parse issue number from URL in output, e.g.
        # https://github.com/owner/repo/issues/42
        match = re.search(r'/issues/(\d+)', output)
        if match:
            return int(match.group(1))
        # Fallback: try to parse the output directly as a number
        try:
            return int(output)
        except ValueError:
            # Last resort: search for the issue we just created
            result = subprocess.run(
                ['gh', 'issue', 'list', '--state', 'open',
                 '--search', f'{title} in:title',
                 '--limit', '1',
                 '--json', 'number',
                 '--jq', '.[0].number'],
                capture_output=True,
                check=True,
                encoding='utf-8', errors='replace',
            )
            return int(result.stdout.strip())


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_push():
    """Push local progress.json to a GitHub Issue."""
    # Find progress file
    filepath = find_progress_file()
    if not filepath:
        print(
            "ERROR: No progress.json found in this project.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Verify prerequisites
    check_git()
    check_gh_auth()

    # Load data
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Update timestamp before serializing into the issue body
    data['updated'] = datetime.now(CST).isoformat()

    # Project name = basename of the directory containing progress.json
    project_dir = os.path.abspath(os.path.dirname(filepath))
    project_name = os.path.basename(project_dir)
    title = f'Progress: {project_name}'

    # Render body and sync
    body = format_issue_body(data)
    issue_number = find_or_create_issue(title, body)

    # Store the issue number back into progress.json
    data['github_issue'] = issue_number
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f'Pushed progress to GitHub Issue #{issue_number}: {title}')


def cmd_pull():
    """Pull progress from a GitHub Issue to local progress.json."""
    # Check for existing progress file
    existing_path = find_progress_file()

    # Verify prerequisites
    check_git()
    check_gh_auth()

    # Determine project name
    if existing_path:
        project_dir = os.path.abspath(os.path.dirname(existing_path))
        project_name = os.path.basename(project_dir)
    else:
        project_name = os.path.basename(os.getcwd())

    title = f'Progress: {project_name}'

    # Warn before overwriting local file
    if existing_path:
        response = input(
            'This will overwrite local progress.json. Continue? (y/N) '
        ).strip().lower()
        if response != 'y':
            print('Aborted.')
            return

    # Search for open issue
    result = subprocess.run(
        ['gh', 'issue', 'list', '--state', 'open',
         '--search', f'{title} in:title',
         '--limit', '1',
         '--json', 'number',
         '--jq', '.[0].number'],
        capture_output=True,
        encoding='utf-8', errors='replace',
    )

    issue_number_str = result.stdout.strip() if result.returncode == 0 else ''

    if not issue_number_str:
        print(
            f"ERROR: No open issue found with title 'Progress: {project_name}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    issue_number = int(issue_number_str)

    # Fetch the issue body
    result = subprocess.run(
        ['gh', 'issue', 'view', str(issue_number), '--json', 'body',
         '--jq', '.body'],
        capture_output=True,
        check=True,
        encoding='utf-8', errors='replace',
    )
    body = result.stdout

    # Extract JSON block from the markdown body
    match = re.search(r'```json\n(.*?)\n```', body, re.DOTALL)
    if not match:
        print(
            "ERROR: Could not find JSON block in Issue body.",
            file=sys.stderr,
        )
        sys.exit(1)

    json_str = match.group(1)

    # Parse JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(
            f'ERROR: Invalid JSON in Issue body: {e}',
            file=sys.stderr,
        )
        sys.exit(1)

    # Update metadata
    data['github_issue'] = issue_number
    data['updated'] = datetime.now(CST).isoformat()

    # Determine output path
    output_path = existing_path if existing_path else os.path.join(
        os.getcwd(), PROGRESS_FILE
    )

    # Write back
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f'Pulled progress from GitHub Issue #{issue_number}: {title}')
    print(f'Written to: {output_path}')


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('push', 'pull'):
        print(
            f'Usage: python {os.path.basename(__file__)} <push|pull>',
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]
    if command == 'push':
        cmd_push()
    elif command == 'pull':
        cmd_pull()


if __name__ == '__main__':
    main()
