import json
import subprocess
import textwrap


def _run_node_json(node_script: str):
    completed = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=".",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_get_server_platform_filter_skips_local_only_filters():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const start = src.indexOf('function getServerPlatformFilter(filter) {');
        if (start === -1) {
          console.error('getServerPlatformFilter missing');
          process.exit(1);
        }

        let depth = 0;
        let end = -1;
        for (let i = start; i < src.length; i += 1) {
          const ch = src[i];
          if (ch === '{') depth += 1;
          if (ch === '}') {
            depth -= 1;
            if (depth === 0) {
              end = i + 1;
              break;
            }
          }
        }
        if (end === -1) {
          console.error('getServerPlatformFilter parse failure');
          process.exit(1);
        }

        eval(src.slice(start, end));

        console.log(JSON.stringify({
          favorites: getServerPlatformFilter('favorites'),
          todos: getServerPlatformFilter('todos'),
          threads: getServerPlatformFilter('threads'),
          x: getServerPlatformFilter('x')
        }));
        """
    )

    payload = _run_node_json(node_script)
    assert payload == {
        "favorites": "",
        "todos": "",
        "threads": "threads",
        "x": "twitter",
    }
