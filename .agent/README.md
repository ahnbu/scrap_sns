# Agent Operating Guide

## Purpose
This file defines how to operate `.agent` assets consistently across Codex/CLI environments.

## Source of Truth
- Skills: `.agent/skills/*/SKILL.md`
- Workflows: `.agent/workflows/*.md`
- Rules: `.agent/rules/*.md`
- MCP + memory mapping: `.agent/mcp.json`
- User language/agent CLI mapping: `.agent/config/user-preferences.yaml`

## Execution Priority
1. `rules` (always-on constraints)
2. `workflows` (process contract)
3. `skills` (task capability)

If two instructions conflict, follow the highest-priority layer.

## Available Skills (Current)
- `backend-agent`, `frontend-agent`, `mobile-agent`
- `qa-agent`, `debug-agent`, `pm-agent`
- `commit`, `workflow-guide`, `orchestrator`

## Workflow Selection
- Use `plan` for requirement decomposition and API/task planning.
- Use `coordinate` for multi-domain execution with PM + QA loop.
- Use `orchestrate` for plan-driven parallel agent spawning.
- Use `debug` for reproduce-root-cause-fix-regression flow.
- Use `review` for QA/security/performance/a11y review.
- Use `tools` to inspect/limit MCP tool access.
- Use `setup` for CLI/MCP initialization checks.

## Operational Notes
- Some clients do not support slash commands. If `/commit` is unavailable, use natural language:
  - `Commit current changes using commit skill rules`
  - `Show commit message preview, wait for confirmation, then commit`
- `orchestrate` expects `.agent/plan.json`. Create it via `plan` first.
- Most workflows require MCP tool usage and memory writes to `.serena/memories`.

## Guardrails
- Follow `.agent/rules/encoding-safety.md` for JSON edits.
- Follow `.agent/rules/data-schema.md` for output field order/type.
- Follow `.agent/rules/security-check.md` before commit/release.

## Validation
Run:

```bash
python .agent/scripts/validate_agent_config.py
```

This verifies required directories/files and cross-references in workflow docs.
