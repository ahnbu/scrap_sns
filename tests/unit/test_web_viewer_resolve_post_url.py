import json
import subprocess
import sys
import textwrap


def test_resolve_post_url_handles_threads_legacy_and_standard_shapes():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const start = src.indexOf('function resolvePostUrl(post) {');
        if (start === -1) {
          console.error('resolvePostUrl missing');
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
          console.error('resolvePostUrl parse failure');
          process.exit(1);
        }

        eval(src.slice(start, end));

        const result = {
          standard: resolvePostUrl({
            url: 'https://www.threads.net/@testuser/post/ABC123'
          }),
          legacyThreads: resolvePostUrl({
            sns_platform: 'threads',
            user: 'testuser',
            code: 'ABC123'
          }),
          legacyUrl: resolvePostUrl({
            post_url: 'https://example.com/legacy'
          })
        };

        console.log(JSON.stringify(result));
        """
    )

    completed = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=".",
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    assert payload["standard"] == "https://www.threads.net/@testuser/post/ABC123"
    assert payload["legacyThreads"] == "https://www.threads.net/@testuser/post/ABC123"
    assert payload["legacyUrl"] == "https://example.com/legacy"
