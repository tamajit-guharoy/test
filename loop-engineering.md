# Loop Engineering: A Practical Guide

> "I don't prompt Claude anymore. I have loops running that prompt Claude and figuring out what to do. My job is to write loops."
> — Boris Cherny, Head of Claude Code, Anthropic

---

## Table of Contents

1. [From Prompts to Loops](#1-from-prompts-to-loops)
2. [Anatomy of a Loop](#2-anatomy-of-a-loop)
3. [Your First Loop](#3-your-first-loop)
4. [Harness Design](#4-harness-design)
5. [Loop Patterns](#5-loop-patterns)
6. [Real World: CI Auto-Fix Loop](#6-real-world-ci-auto-fix-loop)
7. [Real World: Living Documentation Loop](#7-real-world-living-documentation-loop)
8. [Real World: Data Pipeline Monitor](#8-real-world-data-pipeline-monitor)
9. [Real World: Multi-Agent Loops](#9-real-world-multi-agent-loops)
10. [Termination & Guard Rails](#10-termination--guard-rails)
11. [Observability](#11-observability)
12. [When NOT to Use a Loop](#12-when-not-to-use-a-loop)

---

## 1. From Prompts to Loops

### The Prompt Engineering Era

Most people start their AI journey like this:

```
You: "Review this Python function and suggest improvements."
Claude: "Here are five suggestions: ..."
You: (manually apply some, ignore others, move on)
```

This works — but it puts *you* in the loop. Every decision, every trigger, every follow-up requires your attention. You are the scheduler, the evaluator, and the executor.

### The Ceiling You Hit

One-shot prompting breaks down when:

- The task recurs (every PR, every deploy, every commit)
- The output of one step feeds the next
- Quality requires iteration, not a single pass
- You want work to happen while you sleep

### What Loop Engineering Solves

Loop engineering flips the model: instead of you driving the AI, you write a **harness** — a program that drives the AI on your behalf. The harness decides when to run, what to ask, how to evaluate the result, and whether to loop again.

```
Traditional:  You → Prompt → AI → Answer → You (manual action)

Loop:         Harness → Prompt → AI → Answer → Harness (auto action) → repeat
```

The result: you go from crafting one prompt at a time to designing systems that run autonomously.

---

## 2. Anatomy of a Loop

Every loop, no matter how simple or complex, has four parts:

```
┌─────────────┐
│   TRIGGER   │  What starts the loop? (time, event, file change, CI status)
└──────┬──────┘
       ↓
┌─────────────┐
│    TASK     │  What does the AI do? (review, fix, generate, summarize)
└──────┬──────┘
       ↓
┌─────────────┐
│  EVALUATE   │  Did it succeed? (tests pass, diff is non-empty, score > threshold)
└──────┬──────┘
       ↓
┌─────────────┐
│  FEEDBACK   │  What happens next? (commit, retry, alert, stop)
└─────────────┘
```

### Example: A Simple PR Review Loop

| Part     | Value                                              |
|----------|----------------------------------------------------|
| Trigger  | New pull request opened                            |
| Task     | Ask AI to review diff for bugs and style issues    |
| Evaluate | Did the review produce actionable comments?        |
| Feedback | Post comments on PR; if critical issues, block merge |

---

## 3. Your First Loop

Let's build a **file-watching code review loop** — the simplest useful loop you can write. Every time you save a Python file, it gets auto-reviewed.

### What It Does

- Watches a directory for `.py` file changes
- Sends the changed file to Claude for review
- Prints the review to your terminal
- Loops indefinitely until you stop it

### The Code

```python
# file_review_loop.py
import time
import subprocess
import os
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()
WATCH_DIR = "./src"
CHECK_INTERVAL = 3  # seconds

def get_file_mtimes(directory):
    mtimes = {}
    for path in Path(directory).rglob("*.py"):
        mtimes[str(path)] = path.stat().st_mtime
    return mtimes

def review_file(filepath):
    code = Path(filepath).read_text()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"Review this Python file for bugs, style issues, and improvements. Be concise.\n\n```python\n{code}\n```"
        }]
    )
    return response.content[0].text

def run_loop():
    print(f"Watching {WATCH_DIR} for changes...")
    previous_mtimes = get_file_mtimes(WATCH_DIR)

    while True:
        time.sleep(CHECK_INTERVAL)
        current_mtimes = get_file_mtimes(WATCH_DIR)

        for filepath, mtime in current_mtimes.items():
            if filepath not in previous_mtimes or previous_mtimes[filepath] != mtime:
                print(f"\n--- File changed: {filepath} ---")
                review = review_file(filepath)
                print(review)
                print("---")

        previous_mtimes = current_mtimes

if __name__ == "__main__":
    run_loop()
```

### Running It

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here
python file_review_loop.py
```

Now save any `.py` file in `./src` and watch the review appear automatically. You didn't prompt anything — the harness did.

---

## 4. Harness Design

The harness is the code that surrounds the AI call. Good harness design is what separates a toy loop from a production-grade one.

### Core Principles

**1. The harness owns the logic; the model owns the language.**

Don't ask the model "should I retry?" — that's a harness decision. Ask the model "fix this bug" and let the harness decide whether to run tests and retry.

**2. Make state explicit.**

Store what the loop has done so it can resume after a crash, avoid repeating work, and produce an audit trail.

**3. Design for failure from day one.**

The model will occasionally produce bad output. Your harness needs to detect it (evaluation step) and handle it gracefully (feedback step).

### Harness Template

```python
# harness_template.py
import json
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()
STATE_FILE = "loop_state.json"

def load_state():
    if Path(STATE_FILE).exists():
        return json.loads(Path(STATE_FILE).read_text())
    return {"processed": [], "iteration": 0}

def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))

def get_work_items():
    # Return list of things to process (files, PRs, rows, etc.)
    return []

def do_task(item, state):
    # Call the model with context from item + state
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": f"Process: {item}"}]
    )
    return response.content[0].text

def evaluate(result):
    # Return True if result is acceptable, False to retry
    return len(result.strip()) > 0

def apply_feedback(item, result, state):
    # Commit, post, write file, send alert, etc.
    state["processed"].append(item)
    state["iteration"] += 1
    save_state(state)

def run(max_iterations=100):
    state = load_state()
    items = get_work_items()

    for item in items:
        if item in state["processed"]:
            continue  # skip already-done work
        if state["iteration"] >= max_iterations:
            print("Max iterations reached. Stopping.")
            break

        result = do_task(item, state)

        if evaluate(result):
            apply_feedback(item, result, state)
        else:
            print(f"Evaluation failed for {item}. Skipping.")

if __name__ == "__main__":
    run()
```

---

## 5. Loop Patterns

### Pattern 1: Polling Loop

Check a resource on a schedule and act if something changed.

```
every 5 minutes:
    fetch latest CI status
    if failed: ask AI to diagnose and suggest fix
    if passed: do nothing
```

**Use when:** you don't have webhooks but need to react to external state.

### Pattern 2: Event-Driven Loop

React to events as they arrive (file save, webhook, queue message).

```
on file change:
    ask AI to review
    post review as comment
```

**Use when:** you have a reliable event source and want low latency.

### Pattern 3: Recursive Loop

The AI's output becomes the next input. Iterate until a condition is met.

```
iteration 1: AI writes first draft of function
iteration 2: AI reviews its own draft, identifies issues
iteration 3: AI rewrites based on its review
...until: tests pass or max iterations reached
```

**Use when:** quality improves with iteration (writing, code generation, refactoring).

### Pattern 4: Fan-Out Loop

Split one task into many parallel sub-loops.

```
for each file in repo:
    spawn worker loop → review file
collect all reviews → synthesize summary
```

**Use when:** work is parallelizable and you want speed.

---

## 6. Real World: CI Auto-Fix Loop

### The Problem

Your CI pipeline fails. You look at the logs, copy the error, paste it to Claude, apply the fix, push, wait for CI again. This takes 10–20 minutes per cycle and you might need 3–5 cycles.

### The Loop

A CI auto-fix loop watches your CI status, extracts the failure, asks Claude to fix it, commits the fix, and pushes — automatically.

```python
# ci_fix_loop.py
import subprocess
import time
from anthropic import Anthropic

client = Anthropic()
MAX_ATTEMPTS = 5

def get_ci_status():
    result = subprocess.run(
        ["gh", "run", "list", "--limit", "1", "--json", "status,conclusion,databaseId"],
        capture_output=True, text=True
    )
    import json
    runs = json.loads(result.stdout)
    return runs[0] if runs else None

def get_ci_logs(run_id):
    result = subprocess.run(
        ["gh", "run", "view", str(run_id), "--log-failed"],
        capture_output=True, text=True
    )
    return result.stdout[-4000:]  # last 4000 chars to stay within token limits

def get_failing_files():
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "--name-only"],
        capture_output=True, text=True
    )
    return result.stdout.strip().split("\n")

def ask_claude_to_fix(logs, files):
    file_contents = ""
    for f in files:
        try:
            content = open(f).read()
            file_contents += f"\n\n### {f}\n```\n{content}\n```"
        except Exception:
            pass

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""CI is failing. Here are the logs:

{logs}

Here are the relevant files:
{file_contents}

Identify the root cause and output ONLY the fixed file contents, one file at a time, in this format:

### path/to/file.py
```python
<full corrected file content>
```

Do not explain. Just output the fixed files."""
        }]
    )
    return response.content[0].text

def apply_fixes(claude_output):
    import re
    pattern = r'### (.+?)\n```(?:\w+)?\n(.*?)```'
    matches = re.findall(pattern, claude_output, re.DOTALL)
    for filepath, content in matches:
        filepath = filepath.strip()
        print(f"  Writing fix to {filepath}")
        with open(filepath, "w") as f:
            f.write(content.strip())
    return len(matches)

def commit_and_push(attempt):
    subprocess.run(["git", "add", "-A"])
    subprocess.run(["git", "commit", "-m", f"fix: CI auto-fix attempt {attempt}"])
    subprocess.run(["git", "push"])

def run_ci_fix_loop():
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n[Attempt {attempt}/{MAX_ATTEMPTS}] Checking CI status...")
        time.sleep(10)  # wait for CI to register latest push

        run = get_ci_status()
        if not run:
            print("No CI runs found.")
            break

        if run["conclusion"] == "success":
            print("CI is green! Loop complete.")
            break

        if run["status"] == "in_progress":
            print("CI still running, waiting 30s...")
            time.sleep(30)
            continue

        print(f"CI failed (run {run['databaseId']}). Fetching logs...")
        logs = get_ci_logs(run["databaseId"])
        files = get_failing_files()

        print("Asking Claude for a fix...")
        fix_output = ask_claude_to_fix(logs, files)

        num_fixes = apply_fixes(fix_output)
        if num_fixes == 0:
            print("Claude couldn't identify files to fix. Stopping.")
            break

        print(f"Applied {num_fixes} file fix(es). Committing and pushing...")
        commit_and_push(attempt)

    else:
        print("Max attempts reached without CI going green.")

if __name__ == "__main__":
    run_ci_fix_loop()
```

### What Just Happened

You ran one script and walked away. The loop handled the entire fix-push-verify cycle. This is the core value of loop engineering: **you design the workflow once, the loop executes it many times.**

---

## 7. Real World: Living Documentation Loop

### The Problem

Documentation goes stale. A function signature changes, a config key gets renamed, a new environment variable is added — and the README still shows the old version. Nobody has time to update docs after every commit.

### The Loop

A living docs loop watches for commits that touch source files and automatically updates corresponding documentation.

```python
# living_docs_loop.py
import subprocess
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()
DOCS_MAP = {
    "src/config.py": "docs/configuration.md",
    "src/api/routes.py": "docs/api-reference.md",
    "src/auth.py": "docs/authentication.md",
}

def get_changed_files_in_last_commit():
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "--name-only"],
        capture_output=True, text=True
    )
    return result.stdout.strip().split("\n")

def update_doc(source_file, doc_file):
    source_code = Path(source_file).read_text()
    existing_doc = Path(doc_file).read_text() if Path(doc_file).exists() else ""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Update the documentation to match the current source code.

SOURCE CODE ({source_file}):
```
{source_code}
```

CURRENT DOCUMENTATION ({doc_file}):
```
{existing_doc}
```

Rules:
- Keep the same structure and headings
- Update only what has changed (signatures, parameters, config keys, env vars)
- Do not remove sections unless the feature is completely gone
- Output the complete updated documentation file only, no explanation"""
        }]
    )
    return response.content[0].text

def run_docs_loop():
    changed = get_changed_files_in_last_commit()
    updated = []

    for source_file in changed:
        if source_file in DOCS_MAP:
            doc_file = DOCS_MAP[source_file]
            print(f"Updating {doc_file} from {source_file}...")
            new_doc = update_doc(source_file, doc_file)
            Path(doc_file).write_text(new_doc)
            updated.append(doc_file)

    if updated:
        subprocess.run(["git", "add"] + updated)
        subprocess.run(["git", "commit", "-m", "docs: auto-update from source changes [skip ci]"])
        subprocess.run(["git", "push"])
        print(f"Updated and committed: {updated}")
    else:
        print("No documentation updates needed.")

if __name__ == "__main__":
    run_docs_loop()
```

### Wiring It Into Git Hooks

Add this to `.git/hooks/post-commit` to trigger automatically on every commit:

```bash
#!/bin/bash
python living_docs_loop.py
```

```bash
chmod +x .git/hooks/post-commit
```

Now your docs stay fresh automatically, every commit, no human effort.

---

## 8. Real World: Data Pipeline Monitor

### The Problem

A data pipeline runs nightly. Sometimes it silently produces wrong output — wrong row counts, unexpected nulls, broken aggregations. You only find out when a stakeholder emails you.

### The Loop

A data monitor loop runs after each pipeline execution, checks key metrics, and asks Claude to diagnose anything anomalous.

```python
# pipeline_monitor_loop.py
import json
import sqlite3
import time
from datetime import datetime
from anthropic import Anthropic

client = Anthropic()
DB_PATH = "pipeline_output.db"
ALERT_LOG = "anomaly_report.md"

def get_pipeline_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    stats = {}

    # Row counts per table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[f"{table}_row_count"] = cursor.fetchone()[0]

        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE rowid IN (SELECT rowid FROM {table} LIMIT 1000)")
        # Check for nulls in first column
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if columns:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {columns[0]} IS NULL")
            stats[f"{table}_{columns[0]}_nulls"] = cursor.fetchone()[0]

    conn.close()
    return stats

def load_previous_stats():
    try:
        return json.loads(open("previous_stats.json").read())
    except FileNotFoundError:
        return {}

def save_stats(stats):
    with open("previous_stats.json", "w") as f:
        json.dump(stats, f)

def detect_anomalies(current, previous):
    anomalies = []
    for key, value in current.items():
        if key in previous:
            prev = previous[key]
            if prev > 0:
                change_pct = abs(value - prev) / prev * 100
                if change_pct > 20:  # flag >20% change
                    anomalies.append({
                        "metric": key,
                        "previous": prev,
                        "current": value,
                        "change_pct": round(change_pct, 1)
                    })
    return anomalies

def diagnose_anomalies(anomalies, current_stats):
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""A data pipeline produced anomalous metrics. Diagnose likely causes and suggest what to check.

ANOMALIES DETECTED:
{json.dumps(anomalies, indent=2)}

FULL CURRENT STATS:
{json.dumps(current_stats, indent=2)}

For each anomaly, explain:
1. Likely root cause
2. What to check first
3. Whether this looks like a data issue or a pipeline issue

Be concise and practical."""
        }]
    )
    return response.content[0].text

def write_alert_report(anomalies, diagnosis):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"""## Pipeline Anomaly Report — {timestamp}

### Anomalies
{json.dumps(anomalies, indent=2)}

### Diagnosis
{diagnosis}

---
"""
    with open(ALERT_LOG, "a") as f:
        f.write(report)
    print(f"Report written to {ALERT_LOG}")

def run_monitor_loop(interval_seconds=3600):
    print("Pipeline monitor started.")
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Running pipeline check...")

        current_stats = get_pipeline_stats()
        previous_stats = load_previous_stats()
        anomalies = detect_anomalies(current_stats, previous_stats)

        if anomalies:
            print(f"Found {len(anomalies)} anomaly(s). Asking Claude to diagnose...")
            diagnosis = diagnose_anomalies(anomalies, current_stats)
            write_alert_report(anomalies, diagnosis)
        else:
            print("All metrics look normal.")

        save_stats(current_stats)
        print(f"Sleeping {interval_seconds}s until next check...")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    run_monitor_loop()
```

### What This Gives You

- Automatic anomaly detection (no threshold tuning required — Claude understands context)
- Plain-English diagnosis you can forward to your team
- A running log you can diff over time

---

## 9. Real World: Multi-Agent Loops

### The Problem

A single AI pass has blind spots. The model that wrote the code has a hard time spotting its own bugs — the same assumptions that led to the bug lead to missing it in review.

### The Pattern: Writer + Critic

Use two agents in a loop: one writes, one reviews. The critic's feedback feeds back to the writer. Repeat until the critic approves.

```python
# writer_critic_loop.py
from anthropic import Anthropic

client = Anthropic()
MAX_ROUNDS = 4

def writer_agent(task, previous_code=None, feedback=None):
    messages = [{"role": "user", "content": task}]

    if previous_code and feedback:
        messages = [
            {"role": "user", "content": task},
            {"role": "assistant", "content": previous_code},
            {"role": "user", "content": f"A reviewer found these issues:\n\n{feedback}\n\nPlease fix them and return the complete updated code."}
        ]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=messages,
        system="You are a senior software engineer. Write clean, correct, production-ready code."
    )
    return response.content[0].text

def critic_agent(code, task):
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Review this code for the following task:

TASK: {task}

CODE:
{code}

Check for:
- Correctness (does it actually solve the task?)
- Edge cases (empty input, None, overflow, etc.)
- Security issues
- Performance problems

If the code is acceptable, respond with exactly: APPROVED
Otherwise, list specific issues to fix. Be concise."""
        }],
        system="You are a meticulous code reviewer. You do not approve code that has real issues."
    )
    return response.content[0].text

def run_writer_critic_loop(task):
    print(f"Task: {task}\n")
    code = None
    feedback = None

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"--- Round {round_num} ---")
        print("Writer generating code...")
        code = writer_agent(task, code, feedback)
        print(code)

        print("\nCritic reviewing...")
        feedback = critic_agent(code, task)
        print(f"Critic: {feedback}\n")

        if feedback.strip().startswith("APPROVED"):
            print(f"Code approved after {round_num} round(s).")
            return code

    print(f"Max rounds reached. Last code returned.")
    return code

if __name__ == "__main__":
    task = """
    Write a Python function `parse_csv_safe(filepath)` that:
    - Reads a CSV file
    - Returns a list of dicts (one per row)
    - Handles missing files gracefully
    - Handles empty files gracefully
    - Handles rows with missing columns gracefully
    """
    final_code = run_writer_critic_loop(task)
```

### Sample Output

```
--- Round 1 ---
Writer generating code...
[first draft — missing empty file handling]

Critic: The function raises StopIteration on empty CSV files. Add a check after
opening the file. Also: no handling when a row is shorter than the header.

--- Round 2 ---
Writer generating code...
[fixed draft]

Critic: APPROVED
Code approved after 2 round(s).
```

The loop converged in 2 rounds. No human reviewed anything.

---

## 10. Termination & Guard Rails

Loops that never stop are bugs. Production loops need explicit exit conditions and safety limits.

### The Three Termination Conditions

**1. Success condition** — the loop achieved its goal.
```python
if test_suite_passes():
    print("Done.")
    break
```

**2. Budget limit** — cap cost and API calls.
```python
MAX_TOKENS_TOTAL = 100_000
if total_tokens_used >= MAX_TOKENS_TOTAL:
    print("Token budget exhausted.")
    break
```

**3. Iteration limit** — prevent infinite loops.
```python
MAX_ITERATIONS = 10
if iteration >= MAX_ITERATIONS:
    print("Max iterations reached.")
    break
```

### Human Checkpoints

For high-stakes actions (pushing to main, sending emails, deleting data), add a human-in-the-loop confirmation step:

```python
def confirm(action_description):
    response = input(f"\nAbout to: {action_description}\nProceed? [y/N]: ")
    return response.strip().lower() == "y"

# In the loop:
if is_high_stakes_action(result):
    if not confirm(f"Push fix to main branch"):
        print("User declined. Stopping loop.")
        break
```

### Exponential Backoff on Failure

Don't hammer an API or service when it's failing. Back off gracefully:

```python
import time

def call_with_backoff(fn, max_retries=4):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s, 8s
            print(f"Attempt {attempt+1} failed: {e}. Retrying in {wait}s...")
            time.sleep(wait)
```

---

## 11. Observability

A loop that runs silently is a loop you can't debug. Instrument everything.

### Structured Logging

```python
import json
import logging
from datetime import datetime

logging.basicConfig(
    filename="loop.log",
    level=logging.INFO,
    format="%(message)s"
)

def log_event(event_type, data):
    logging.info(json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "event": event_type,
        **data
    }))

# Usage:
log_event("task_started", {"file": filepath, "iteration": 3})
log_event("task_completed", {"file": filepath, "tokens_used": 412, "duration_ms": 1840})
log_event("evaluation_failed", {"file": filepath, "reason": "empty output"})
```

### What to Always Log

| Event             | Fields to capture                              |
|-------------------|------------------------------------------------|
| Loop started      | timestamp, config, trigger source              |
| Task called       | item identifier, iteration number              |
| Model responded   | tokens used, latency, first 100 chars of output|
| Evaluation result | pass/fail, reason                              |
| Feedback applied  | action taken (commit hash, file path, etc.)    |
| Loop stopped      | reason (success / budget / iterations / error) |

### Alerting

For production loops, emit an alert if the loop stops unexpectedly:

```python
import smtplib
from email.message import EmailMessage

def send_alert(subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "loop-monitor@yourcompany.com"
    msg["To"] = "oncall@yourcompany.com"
    msg.set_content(body)
    # configure your SMTP server here
    with smtplib.SMTP("localhost") as s:
        s.send_message(msg)

# In your loop's exception handler:
except Exception as e:
    send_alert(
        subject=f"Loop crashed: {loop_name}",
        body=f"Error: {e}\nLast state: {json.dumps(state)}"
    )
    raise
```

---

## 12. When NOT to Use a Loop

Loop engineering is powerful, but it's not always the right tool.

### Use a Single Prompt When:

| Situation | Why a loop is overkill |
|-----------|------------------------|
| One-off question | Loops are for recurring tasks |
| Interactive exploration | You want to steer the conversation, not automate it |
| Trivial transformation | Wrapping a one-liner in a loop adds complexity with no benefit |
| Unclear success criteria | If you can't define "done", the evaluation step can't work |
| Result needs human judgment | Some decisions shouldn't be automated |

### Signs You're Over-Engineering a Loop

- Your evaluation step always returns "pass"
- You have retries but no actual failure cases
- The loop runs once and you're happy with the first result every time
- You're spending more time on the harness than the underlying task

### The Decision Rule

> If you'd copy-paste the same prompt more than 3 times, it's time for a loop.
> If you'd only run it once, stick with a prompt.

---

## Summary

| Chapter | Key Takeaway |
|---------|-------------|
| 1 | Loops replace you as the scheduler and evaluator |
| 2 | Every loop has: trigger, task, evaluate, feedback |
| 3 | Start simple: file watcher → AI review → print |
| 4 | The harness owns logic; the model owns language |
| 5 | Four patterns: polling, event-driven, recursive, fan-out |
| 6 | CI auto-fix loops eliminate the fix-push-wait cycle |
| 7 | Living docs loops keep documentation honest |
| 8 | Pipeline monitors catch silent data failures |
| 9 | Writer + critic loops produce higher quality output |
| 10 | Always have success, budget, and iteration limits |
| 11 | Log every event; alert on unexpected stops |
| 12 | One-off tasks don't need loops — keep it simple |

---

*The shift from prompt engineering to loop engineering is a shift from driving to navigating. You stop steering every turn and start designing the road.*
