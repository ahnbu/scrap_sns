import json
import os
import subprocess
from pathlib import Path


def _write_fake_opencli(tmp_path: Path) -> Path:
    appdata = tmp_path / "appdata"
    opencli_main = appdata / "npm" / "node_modules" / "@jackwener" / "opencli" / "dist" / "src" / "main.js"
    opencli_main.parent.mkdir(parents=True)
    log_path = tmp_path / "opencli-commands.jsonl"
    opencli_main.write_text(
        f"""
import {{ appendFileSync }} from "node:fs";

const logPath = {str(log_path).replace(chr(92), "/")!r};
const args = process.argv.slice(2);
appendFileSync(logPath, JSON.stringify(args) + "\\n", "utf8");

const command = args.slice(2);
if (command[0] === "open") {{
  console.log(JSON.stringify({{ opened: true }}));
}} else if (command[0] === "state") {{
  console.log("Saved");
}} else {{
  console.log("");
}}
""",
        encoding="utf-8",
    )
    return appdata


def _run_collector(tmp_path: Path, *args: str) -> list[list[str]]:
    appdata = _write_fake_opencli(tmp_path)
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "linkedin_opencli_shadow_collect.mjs"
    result = subprocess.run(
        [
            "node",
            str(script_path),
            "--session",
            "externally_bound",
            "--max-pages",
            "0",
            *args,
        ],
        cwd=script_path.parents[1],
        env=os.environ | {"APPDATA": str(appdata)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    log_path = tmp_path / "opencli-commands.jsonl"
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]


def test_linkedin_opencli_collector_declares_browser_close_cleanup():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "linkedin_opencli_shadow_collect.mjs"
    source = script_path.read_text(encoding="utf-8")

    assert 'browser(session, ["open", url, "--window", "background"]' in source
    assert 'browser(session, ["unbind"]' in source
    assert 'browser(session, ["close"]' in source
    assert '["tab", "new"' not in source
    assert '["tab", "close"' not in source


def test_linkedin_opencli_collector_closes_internally_opened_session(tmp_path):
    commands = _run_collector(tmp_path)

    assert ["browser", "externally_bound", "open", "https://www.linkedin.com/my-items/saved-posts/", "--window", "background"] in commands
    assert ["browser", "externally_bound", "unbind"] in commands
    assert ["browser", "externally_bound", "close"] in commands


def test_linkedin_opencli_collector_keeps_externally_bound_session_open(tmp_path):
    commands = _run_collector(tmp_path, "--use-bound-session")

    assert ["browser", "externally_bound", "open", "https://www.linkedin.com/my-items/saved-posts/", "--window", "background"] not in commands
    assert ["browser", "externally_bound", "unbind"] not in commands
    assert ["browser", "externally_bound", "close"] not in commands
