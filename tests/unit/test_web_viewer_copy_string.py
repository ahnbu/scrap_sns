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


def test_build_copy_text_uses_author_fallback_and_resolved_post_url():
    cases = [
        (
            "display_name",
            {
                "full_text": "본문",
                "post_url": "https://example.com/post",
                "display_name": "표시명",
                "username": "user-name",
                "user": "user-id",
                "created_at": "2025-04-17T09:00:00Z",
                "sns_platform": "threads",
            },
            "본문\n\n*출처: https://example.com/post\n*표시명 / 2025-04-17 / threads",
        ),
        (
            "username",
            {
                "full_text": "본문",
                "post_url": "https://example.com/post",
                "username": "user-name",
                "user": "user-id",
                "created_at": "2025-04-17T09:00:00Z",
                "sns_platform": "threads",
            },
            "본문\n\n*출처: https://example.com/post\n*user-name / 2025-04-17 / threads",
        ),
        (
            "user",
            {
                "full_text": "본문",
                "post_url": "https://example.com/post",
                "user": "user-id",
                "created_at": "2025-04-17T09:00:00Z",
                "sns_platform": "threads",
            },
            "본문\n\n*출처: https://example.com/post\n*user-id / 2025-04-17 / threads",
        ),
    ]

    for case_name, post, expected in cases:
        node_script = textwrap.dedent(
            f"""
            const fs = require('fs');
            const src = fs.readFileSync('web_viewer/script.js', 'utf8');

            function extractFunction(name) {{
              const patterns = [`async function ${{name}}(`, `function ${{name}}(`];
              let start = -1;
              for (const pattern of patterns) {{
                start = src.indexOf(pattern);
                if (start !== -1) break;
              }}
              if (start === -1) {{
                console.error(`${{name}} missing`);
                process.exit(1);
              }}

              let depth = 0;
              let end = -1;
              for (let i = start; i < src.length; i += 1) {{
                const ch = src[i];
                if (ch === '{{') depth += 1;
                if (ch === '}}') {{
                  depth -= 1;
                  if (depth === 0) {{
                    end = i + 1;
                    break;
                  }}
                }}
              }}

              if (end === -1) {{
                console.error(`${{name}} parse failure`);
                process.exit(1);
              }}

              return src.slice(start, end);
            }}

            eval(extractFunction('resolvePostUrl'));
            eval(extractFunction('buildCopyText'));

            const result = buildCopyText({json.dumps(post)});

            console.log(JSON.stringify({{ caseName: {json.dumps(case_name)}, result }}));
            """
        )

        payload = run_node_json(node_script)
        assert payload["caseName"] == case_name
        assert payload["result"] == expected
