#!/usr/bin/env python3
"""
Validate .agent structure and key cross references.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = ROOT / ".agent"


REQUIRED_DIRS = [
    AGENT_DIR / "skills",
    AGENT_DIR / "workflows",
    AGENT_DIR / "rules",
    AGENT_DIR / "config",
]

REQUIRED_FILES = [
    AGENT_DIR / "mcp.json",
    AGENT_DIR / "config" / "user-preferences.yaml",
]

REQUIRED_WORKFLOWS = [
    "setup.md",
    "plan.md",
    "coordinate.md",
    "orchestrate.md",
    "debug.md",
    "review.md",
    "tools.md",
]

REQUIRED_RULES = [
    "coding-style.md",
    "data-schema.md",
    "encoding-safety.md",
    "mermaid.md",
    "security-check.md",
    "testing.md",
]

OPTIONAL_REFERENCES = {
    ".agent/plan.json",
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}")


def ok(message: str) -> None:
    print(f"[OK]   {message}")


def check_paths() -> int:
    errors = 0
    for d in REQUIRED_DIRS:
        if d.is_dir():
            ok(f"Directory exists: {d.relative_to(ROOT)}")
        else:
            fail(f"Missing directory: {d.relative_to(ROOT)}")
            errors += 1

    for f in REQUIRED_FILES:
        if f.is_file():
            ok(f"File exists: {f.relative_to(ROOT)}")
        else:
            fail(f"Missing file: {f.relative_to(ROOT)}")
            errors += 1

    for name in REQUIRED_WORKFLOWS:
        p = AGENT_DIR / "workflows" / name
        if p.is_file():
            ok(f"Workflow present: .agent/workflows/{name}")
        else:
            fail(f"Missing workflow: .agent/workflows/{name}")
            errors += 1

    for name in REQUIRED_RULES:
        p = AGENT_DIR / "rules" / name
        if p.is_file():
            ok(f"Rule present: .agent/rules/{name}")
        else:
            fail(f"Missing rule: .agent/rules/{name}")
            errors += 1

    skill_files = list((AGENT_DIR / "skills").glob("*/SKILL.md"))
    if skill_files:
        ok(f"Detected skills: {len(skill_files)}")
    else:
        fail("No skill definitions found at .agent/skills/*/SKILL.md")
        errors += 1

    return errors


def check_references() -> int:
    errors = 0
    workflow_files = sorted((AGENT_DIR / "workflows").glob("*.md"))
    rel_path_pattern = re.compile(r"`(\.agent/[^`]+)`")

    for wf in workflow_files:
        text = wf.read_text(encoding="utf-8")
        refs = rel_path_pattern.findall(text)
        for rel in refs:
            target = ROOT / rel
            if target.exists():
                ok(f"Reference ok: {wf.relative_to(ROOT)} -> {rel}")
            elif rel in OPTIONAL_REFERENCES:
                ok(f"Optional reference skipped: {wf.relative_to(ROOT)} -> {rel}")
            else:
                fail(f"Broken reference: {wf.relative_to(ROOT)} -> {rel}")
                errors += 1

    return errors


def main() -> int:
    print("Validating .agent configuration...")
    total_errors = 0
    total_errors += check_paths()
    total_errors += check_references()

    if total_errors:
        print(f"\nValidation completed with {total_errors} error(s).")
        return 1

    print("\nValidation passed with no errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
