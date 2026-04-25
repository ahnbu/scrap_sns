import json
import subprocess
import textwrap


def run_node_json(node_script: str):
    completed = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=".",
    )

    assert completed.returncode == 0, completed.stderr
    stdout = completed.stdout.strip()
    return json.loads(stdout.splitlines()[-1])


def test_get_failed_platforms_returns_only_known_failed_platforms():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const patterns = [`async function ${name}(`, `function ${name}(`];
          let start = -1;
          for (const pattern of patterns) {
            start = src.indexOf(pattern);
            if (start !== -1) break;
          }
          if (start === -1) {
            console.error(`${name} missing`);
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
            console.error(`${name} parse failure`);
            process.exit(1);
          }

          return src.slice(start, end);
        }

        global.authPlatformLabels = {
          linkedin: 'LinkedIn',
          threads: 'Threads',
          x: 'X'
        };

        eval(extractFunction('normalizeAuthPlatform'));
        eval(extractFunction('getFailedPlatforms'));

        const result = getFailedPlatforms({
          platform_results: {
            x: { status: 'failed' },
            linkedin: { status: 'ok' },
            threads: { status: 'failed' },
            unknown: { status: 'failed' }
          }
        });

        console.log(JSON.stringify(result));
        """
    )

    assert run_node_json(node_script) == ["x", "threads"]
