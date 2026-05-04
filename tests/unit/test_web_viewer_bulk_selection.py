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


def test_get_visible_selected_posts_preserves_current_screen_order():
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

        eval(extractFunction('resolvePostUrl'));
        eval(extractFunction('getVisibleSelectedPosts'));

        const posts = [
          {
            display_name: 'Alice',
            sns_platform: 'threads',
            url: 'https://www.threads.net/@alice/post/A'
          },
          {
            display_name: 'Bob',
            post_url: 'https://example.com/b'
          },
          {
            display_name: 'Carol',
            canonical_url: 'https://www.threads.com/@carol/post/C'
          }
        ];

        const selected = new Set([
          'https://example.com/b',
          'https://www.threads.com/@alice/post/A'
        ]);

        const result = getVisibleSelectedPosts(posts, selected)
          .map((post) => post.display_name);

        console.log(JSON.stringify({ result }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["result"] == ["Alice", "Bob"]


def test_build_bulk_copy_text_joins_existing_single_post_format():
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

        eval(extractFunction('resolvePostUrl'));
        eval(extractFunction('buildCopyText'));
        eval(extractFunction('buildBulkCopyText'));

        const result = buildBulkCopyText([
          {
            full_text: '첫 번째 본문',
            post_url: 'https://example.com/1',
            display_name: '첫작성자',
            created_at: '2026-05-04T10:00:00+09:00',
            sns_platform: 'linkedin'
          },
          {
            full_text: '두 번째 본문',
            post_url: 'https://example.com/2',
            username: 'second',
            created_at: '2026-05-04T11:00:00+09:00',
            sns_platform: 'threads'
          }
        ]);

        console.log(JSON.stringify({ result }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["result"] == (
        "첫 번째 본문\n\n"
        "*출처: https://example.com/1\n"
        "*첫작성자 / 2026-05-04 / linkedin\n\n"
        "---\n\n"
        "두 번째 본문\n\n"
        "*출처: https://example.com/2\n"
        "*second / 2026-05-04 / threads"
    )


def test_add_selected_urls_to_set_keeps_existing_values_and_ignores_empty_urls():
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

        eval(extractFunction('addSelectedUrlsToSet'));

        const target = new Set(['https://example.com/existing']);
        addSelectedUrlsToSet(target, new Set([
          'https://example.com/new',
          '',
          null,
          'https://example.com/existing'
        ]));

        console.log(JSON.stringify({ result: Array.from(target) }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["result"] == [
        "https://example.com/existing",
        "https://example.com/new",
    ]
