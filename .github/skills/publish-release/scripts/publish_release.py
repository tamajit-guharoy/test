"""
Clones a GitHub repo, copies a file into it, commits, and pushes.

Usage:
    python push-file-to-repo.py <repo-url> <branch> <input-file> <target-dir>

Example:
    python push-file-to-repo.py https://github.com/owner/repo.git feature/x ./file.txt data/uploaded
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _run(cmd: list[str], cwd: str | None = None, check: bool = False) -> subprocess.CompletedProcess:
    """Run a git command and return the result. Raises on failure if check=True."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{stderr}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Push a file to a GitHub repo branch")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument("branch", help="Target branch name")
    parser.add_argument("input_file", help="Local file to copy into the repo")
    parser.add_argument("target_dir", help="Destination directory relative to repo root")
    args = parser.parse_args()

    # --- Validation ---
    errors: list[str] = []

    if not Path(args.input_file).is_file():
        errors.append(f"Input file not found: '{args.input_file}'")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        errors.append("GITHUB_TOKEN environment variable is not set")

    if errors:
        print(f"{RED}ERROR: The following details are missing or invalid:{RESET}")
        for e in errors:
            print(f"  {RED}- {e}{RESET}")
        sys.exit(1)

    file_name = Path(args.input_file).name

    # --- Build authenticated clone URL ---
    try:
        parsed = urlparse(args.repo_url)
        clone_url = urlunparse(parsed._replace(netloc=f"oauth2:{token}@{parsed.hostname}"))
    except Exception as e:
        print(f"{RED}ERROR: Invalid RepoUrl '{args.repo_url}' — {e}{RESET}")
        sys.exit(1)

    temp_dir = tempfile.mkdtemp(prefix="repo_")
    print(f"Temp directory: {temp_dir}")

    push_succeeded = False
    original_cwd = os.getcwd()

    try:
        # --- Clone ---
        print(f"Cloning {args.repo_url} ...")
        _run(["git", "clone", "--quiet", clone_url, temp_dir], check=True)

        os.chdir(temp_dir)

        # --- Checkout / create branch ---
        print(f"Setting up branch '{args.branch}' ...")
        r = _run(["git", "ls-remote", "--heads", "origin", args.branch])

        if r.stdout.strip():
            _run(["git", "checkout", args.branch], check=True)
        else:
            _run(["git", "checkout", "--orphan", args.branch], check=True)
            _run(["git", "rm", "-r", "--quiet", "--cached", "."], check=True)
            _run(["git", "commit", "--allow-empty", "-m", f"Initial empty commit for {args.branch}"], check=True)

        # --- Build target paths ---
        target_dir_abs = Path(temp_dir) / args.target_dir
        target_file_abs = target_dir_abs / file_name
        relative_path = (Path(args.target_dir) / file_name).as_posix()

        if not target_dir_abs.exists():
            target_dir_abs.mkdir(parents=True)
            print(f"Created directory: {target_dir_abs}")

        # --- Copy file ---
        print(f"Copying '{args.input_file}' -> '{relative_path}' ...")
        shutil.copy2(args.input_file, target_file_abs)

        # --- Add, commit, push ---
        print("Committing and pushing ...")
        _run(["git", "add", relative_path], check=True)

        commit_msg = f"{file_name} added"
        r = _run(["git", "commit", "-m", commit_msg])
        if r.returncode != 0 and "nothing to commit" in (r.stderr + r.stdout):
            print("No changes to commit (file already matches).")
        elif r.returncode != 0:
            raise RuntimeError(f"git commit failed: {r.stderr.strip()}")

        _run(["git", "push", "-u", "origin", args.branch], check=True)

        push_succeeded = True
        print(f"{GREEN}SUCCESS: '{file_name}' pushed to '{args.repo_url}' on branch '{args.branch}'.{RESET}")

    except Exception as e:
        print(f"{RED}ERROR: {e}{RESET}")
        sys.exit(1)
    finally:
        try:
            os.chdir(original_cwd)
        except OSError:
            pass

        if push_succeeded:
            print("Cleaning up temp directory...")
            shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            print(f"{YELLOW}Push did not succeed — temp directory kept for inspection: {temp_dir}{RESET}")


if __name__ == "__main__":
    main()
