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


def test_resolve_post_key_prefers_post_key_then_platform_identifier():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const start = src.indexOf(`function ${name}(`);
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

        eval(extractFunction('resolvePostUrl'));
        eval(extractFunction('normalizePostKeyPlatform'));
        eval(extractFunction('resolvePostKey'));

        console.log(JSON.stringify({
          explicit: resolvePostKey({ post_key: 'threads:EXISTING', sns_platform: 'threads', platform_id: 'ABC123' }),
          twitter: resolvePostKey({ sns_platform: 'twitter', platform_id: '12345', url: 'https://x.com/u/status/12345' }),
          threadsCode: resolvePostKey({ sns_platform: 'threads', code: 'ABC123', username: 'alice' }),
          fallbackUrl: resolvePostKey({ sns_platform: 'linkedin', url: 'https://www.linkedin.com/feed/update/urn:li:activity:1/' })
        }));
        """
    )

    payload = _run_node_json(node_script)
    assert payload == {
        "explicit": "threads:EXISTING",
        "twitter": "x:12345",
        "threadsCode": "threads:ABC123",
        "fallbackUrl": "linkedin:url:https://www.linkedin.com/feed/update/urn:li:activity:1/",
    }


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
