#!/usr/bin/env python3
"""
Install Claude Code skills and agents from a GitHub repository branch.

Usage:
    python install_claude.py <github-url> [options]

Examples:
    python install_claude.py https://github.com/user/repo
    python install_claude.py https://github.com/user/repo/tree/main
    python install_claude.py https://github.com/user/repo/tree/dev/skills --skills-only
    python install_claude.py https://github.com/user/repo --token ghp_xxx
    GITHUB_TOKEN=ghp_xxx python install_claude.py https://github.com/user/private-repo

Expected repo structure (auto-detected):
    <root>/
    ├── skills/
    │   └── <skill-name>/
    │       └── SKILL.md        ← any dir containing SKILL.md is treated as a skill
    └── agents/
        └── <agent-name>.md     ← .md files directly under agents/ are treated as agents

Installs to:
    Skills  → ~/.claude/skills/<skill-name>/
    Agents  → ~/.claude/agents/<agent-name>.md
"""

# ---------------------------------------------------------------------------
# Allowlists — only these skills/agents will be installed; all others are skipped.
# Add or remove names here to control what gets installed.
# ---------------------------------------------------------------------------

skill_list: list[str] = [
    # "graphify",
    # "code-review",
]

agent_list: list[str] = [
    # "my-agent",
]

# ---------------------------------------------------------------------------

import sys
import os
import re
import json
import shutil
import argparse
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError


CLAUDE_DIR = Path.home() / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

def parse_github_url(url: str) -> tuple[str, str, str | None, str]:
    """
    Parse a GitHub URL into (owner, repo, branch, subpath).

    Supports:
        https://github.com/owner/repo
        https://github.com/owner/repo.git
        https://github.com/owner/repo/tree/branch
        https://github.com/owner/repo/tree/branch/sub/path
    """
    pattern = r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.*))?)?/?$"
    m = re.match(pattern, url)
    if not m:
        raise ValueError(
            f"Cannot parse GitHub URL: {url!r}\n"
            "Expected format: https://github.com/owner/repo[/tree/branch[/subpath]]"
        )
    owner, repo, branch, subpath = m.groups()
    return owner, repo, branch, (subpath or "").rstrip("/")


def get_default_branch(owner: str, repo: str, token: str | None) -> str:
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "install-claude"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        req = Request(api_url, headers=headers)
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["default_branch"]
    except HTTPError as e:
        if e.code == 404:
            raise SystemExit(f"Error: Repository {owner}/{repo} not found (or private — pass --token).")
        if e.code == 401:
            raise SystemExit("Error: GitHub authentication failed. Check your token.")
        raise SystemExit(f"Error fetching repo metadata: {e}")
    except URLError as e:
        raise SystemExit(f"Error: Network error — {e.reason}")


# ---------------------------------------------------------------------------
# Repository cloning
# ---------------------------------------------------------------------------

def clone_repo(owner: str, repo: str, branch: str, dest: Path, token: str | None) -> None:
    if token:
        clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    else:
        clone_url = f"https://github.com/{owner}/{repo}.git"

    cmd = ["git", "clone", "--depth", "1", "--branch", branch, clone_url, str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Scrub token from error output before printing
        err = result.stderr.replace(token, "***") if token else result.stderr
        raise SystemExit(f"git clone failed:\n{err.strip()}")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_skills(search_dir: Path) -> list[tuple[str, Path]]:
    """Return [(skill_name, skill_dir)] for skills present in skill_list."""
    found = []
    for skill_md in sorted(search_dir.rglob("SKILL.md")):
        skill_dir = skill_md.parent
        # Skip if this is nested inside another skill dir
        if any(p.name == "SKILL.md" for p in skill_dir.parents if p != search_dir):
            continue
        name = skill_dir.name
        if name not in skill_list:
            print(f"  SKIP  skill '{name}' not in skill_list")
            continue
        found.append((name, skill_dir))
    return found


def find_agents(search_dir: Path) -> list[tuple[str, Path]]:
    """Return [(agent_name, agent_file)] for agents present in agent_list."""
    found = []
    agents_dir = search_dir / "agents"
    if agents_dir.is_dir():
        for md in sorted(agents_dir.glob("*.md")):
            name = md.stem
            if name not in agent_list:
                print(f"  SKIP  agent '{name}' not in agent_list")
                continue
            found.append((name, md))
    return found


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def install_skill(name: str, src: Path, force: bool, dry_run: bool) -> bool:
    dest = SKILLS_DIR / name
    label = f"skill '{name}'"

    if dest.exists() and not force:
        print(f"  SKIP  {label} already exists (use --force to overwrite)")
        return False

    if dry_run:
        action = "overwrite" if dest.exists() else "install"
        print(f"  DRY   would {action} {label} → {dest}")
        return True

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    print(f"  OK    {label} → {dest}")
    return True


def install_agent(name: str, src: Path, force: bool, dry_run: bool) -> bool:
    dest = AGENTS_DIR / f"{name}.md"
    label = f"agent '{name}'"

    if dest.exists() and not force:
        print(f"  SKIP  {label} already exists (use --force to overwrite)")
        return False

    if dry_run:
        action = "overwrite" if dest.exists() else "install"
        print(f"  DRY   would {action} {label} → {dest}")
        return True

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(f"  OK    {label} → {dest}")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install Claude Code skills and agents from a GitHub repo branch.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url", help="GitHub URL (optionally ending with /tree/<branch>[/subpath])")
    parser.add_argument(
        "--token", "-t",
        default=os.environ.get("GITHUB_TOKEN"),
        metavar="TOKEN",
        help="GitHub personal access token for private repos (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite already-installed skills/agents",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be installed without making any changes",
    )
    parser.add_argument("--skills-only", action="store_true", help="Install skills only")
    parser.add_argument("--agents-only", action="store_true", help="Install agents only")

    args = parser.parse_args()

    # Parse URL
    try:
        owner, repo, branch, subpath = parse_github_url(args.url)
    except ValueError as e:
        raise SystemExit(f"Error: {e}")

    # Resolve default branch if the URL did not specify one
    if not branch:
        print(f"Fetching default branch for {owner}/{repo}...")
        branch = get_default_branch(owner, repo, args.token)

    print(f"Source : github.com/{owner}/{repo}  branch={branch}" + (f"  subpath={subpath}" if subpath else ""))
    print(f"Target : {CLAUDE_DIR}")
    if args.dry_run:
        print("Mode   : DRY RUN (no files will be written)\n")

    with tempfile.TemporaryDirectory(prefix="install_claude_") as tmpdir:
        repo_dir = Path(tmpdir) / "repo"

        print("Cloning repository (shallow)...")
        clone_repo(owner, repo, branch, repo_dir, args.token)

        search_dir = repo_dir / subpath if subpath else repo_dir

        if not search_dir.exists():
            raise SystemExit(f"Error: subpath '{subpath}' not found in the repository.")

        skills = find_skills(search_dir) if not args.agents_only else []
        agents = find_agents(search_dir) if not args.skills_only else []

        if not skills and not agents:
            print(
                "\nNothing to install — no skills or agents detected.\n"
                "Skills:  any directory containing a SKILL.md file\n"
                "Agents:  .md files directly inside an agents/ directory"
            )
            return

        print(f"\nDetected {len(skills)} skill(s), {len(agents)} agent(s)\n")

        if not args.dry_run:
            SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        installed_skills = sum(install_skill(n, d, args.force, args.dry_run) for n, d in skills)
        installed_agents = sum(install_agent(n, f, args.force, args.dry_run) for n, f in agents)

    verb = "Would install" if args.dry_run else "Installed"
    print(f"\n{verb}: {installed_skills} skill(s), {installed_agents} agent(s).")


if __name__ == "__main__":
    main()
