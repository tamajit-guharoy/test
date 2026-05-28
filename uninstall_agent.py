#!/usr/bin/env python3
"""
Uninstall Claude Code skills and agents from the user home directory.

Usage:
    python uninstall_agent.py [options]

Removes only the skills/agents listed in skill_list and agent_list below.

Uninstalls from:
    Skills  → ~/.claude/skills/<skill-name>/
    Agents  → ~/.claude/agents/<agent-name>.md
"""

# ---------------------------------------------------------------------------
# Allowlists — only these skills/agents will be uninstalled.
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
import shutil
import argparse
from pathlib import Path


CLAUDE_DIR = Path.home() / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"


def uninstall_skill(name: str, dry_run: bool) -> bool:
    dest = SKILLS_DIR / name
    if not dest.exists():
        print(f"  SKIP  skill '{name}' not found at {dest}")
        return False
    if dry_run:
        print(f"  DRY   would remove skill '{name}' ({dest})")
        return True
    shutil.rmtree(dest)
    print(f"  OK    removed skill '{name}' ({dest})")
    return True


def uninstall_agent(name: str, dry_run: bool) -> bool:
    dest = AGENTS_DIR / f"{name}.md"
    if not dest.exists():
        print(f"  SKIP  agent '{name}' not found at {dest}")
        return False
    if dry_run:
        print(f"  DRY   would remove agent '{name}' ({dest})")
        return True
    dest.unlink()
    print(f"  OK    removed agent '{name}' ({dest})")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Uninstall Claude Code skills and agents from ~/.claude/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be removed without making any changes",
    )
    parser.add_argument("--skills-only", action="store_true", help="Uninstall skills only")
    parser.add_argument("--agents-only", action="store_true", help="Uninstall agents only")

    args = parser.parse_args()

    if not skill_list and not agent_list:
        raise SystemExit("Nothing to uninstall — both skill_list and agent_list are empty.")

    if args.dry_run:
        print("Mode: DRY RUN (no files will be removed)\n")

    skills = skill_list if not args.agents_only else []
    agents = agent_list if not args.skills_only else []

    removed_skills = sum(uninstall_skill(name, args.dry_run) for name in skills)
    removed_agents = sum(uninstall_agent(name, args.dry_run) for name in agents)

    verb = "Would remove" if args.dry_run else "Removed"
    print(f"\n{verb}: {removed_skills} skill(s), {removed_agents} agent(s).")


if __name__ == "__main__":
    main()
