# Repository Guidelines

## Project Structure & Module Organization
- Core crawlers are at repo root: `thread_scrap.py`, `twitter_scrap.py`, `linkedin_scrap.py`, `substack_scrap_by_user.py`, `total_scrap.py`.
- Viewer/backend code: `server.py`, `index.html`, `web_viewer/`.
- Output artifacts: `output_threads/`, `output_twitter/`, `output_linkedin/`, `output_total/`.
- Agent system lives under `.agent/`:
  - `skills/` domain skills and subagents
  - `workflows/` execution flows (`plan`, `coordinate`, `orchestrate`, `debug`, `review`, `tools`, `setup`)
  - `rules/` always-on constraints
  - `mcp.json` MCP tool and memory mapping

## Build, Test, and Development Commands
- Install runtime: `pip install playwright python-dotenv` and `playwright install chromium`.
- Local run:
  - `npm run start` -> `python server.py`
  - `npm run view` -> `run_viewer.bat`
  - `npm run stop` -> `stop_viewer.bat`
- Crawling:
  - `npm run scrap:threads`
  - `npm run scrap:linkedin`
  - `npm run scrap:all`
  - Example: `python total_scrap.py --mode update`
- Agent config health check: `python .agent/scripts/validate_agent_config.py`.

## Agent Routing & Precedence
- Apply this precedence strictly: `rules` > `workflows` > `skills`.
- `rules/*.md` are global constraints (coding style, data schema, encoding safety, testing, security, mermaid).
- `workflows/*.md` are process contracts; use them for multi-step operations and MCP-driven tasks.
- `skills/*/SKILL.md` are capability packs for focused execution.
- Some Codex clients reject unknown slash commands before model routing. In that case, use text triggers instead of slash commands.
- Preferred text triggers:
  - `omg-plan: <request>`
  - `omg-review: <scope>`
  - `omg-coordinate: <request>`
  - `omg-orchestrate: <request>`
  - `omg-debug: <error/context>`
- If slash commands are supported in another client build, `/omg-*` and `/prompts:*` may still be used as optional aliases.
- Slash commands may not exist in every client. If `/commit` is unsupported, use natural language: `commit changes using the commit skill workflow`.
- Detailed operating guide: `.agent/README.md`.

## `omg` / `oh-my-ag` Trigger Rule
- Treat `omg` as an alias of `oh-my-ag` in chat requests.
- Treat `omg-*:` text triggers as explicit `oh-my-ag` workflow invocations.
- When a user mentions `omg` or `oh-my-ag`, interpret the request as agent-orchestrated work and activate relevant `.agent` assets:
  - Select matching `skills` under `.agent/skills/`.
  - Use `workflows` under `.agent/workflows/` for multi-step, planning, review, debug, or orchestration tasks.
  - Enforce `rules` under `.agent/rules/` as always-on constraints.
- If a client slash command is unavailable, execute the same intent via natural-language workflow invocation.
- For every `omg`/`oh-my-ag` request, explicitly report to the user before execution:
  - Which `skill(s)` were selected (or `none`)
  - Which `workflow` was selected (or `none`)
  - Which key `rule` sets were enforced
- After execution, explicitly confirm whether the selected workflow/skills were actually applied, and if not, explain why.

## Coding, Testing, and PR Expectations
- Python: 4-space indentation, `snake_case`; JS: `camelCase`.
- Follow data ordering/typing in `.agent/rules/data-schema.md`.
- For JSON edits, follow `.agent/rules/encoding-safety.md` (UTF-8 safe workflow only).
- Validate with targeted tests (for example `python test_logic_refinement.py`, `python test_linkedin_image.py`) and a scraper smoke run.
- Use Conventional Commits (`feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `ui`), include validation steps in PR description, and attach evidence for UI/data changes.
- Commit message language policy:
  - Write commit subject/body in Korean by default.
  - Keep Conventional Commit type/scope tokens in English (for example `fix`, `chore`, `feat`).
  - Technical terms, product names, library names, and code identifiers may remain in English.
