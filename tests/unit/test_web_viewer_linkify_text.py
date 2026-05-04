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


def test_linkify_text_converts_http_urls_and_preserves_newlines():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const prefix = src.slice(0, src.indexOf("document.addEventListener('DOMContentLoaded'"));
        eval(prefix);

        if (typeof linkifyText !== 'function') {
          console.error('linkifyText missing');
          process.exit(1);
        }

        const html = linkifyText('참고 https://example.com/a?b=1&c=2\\n끝');
        console.log(JSON.stringify({ html }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["html"] == (
        '참고 <a href="https://example.com/a?b=1&amp;c=2" '
        'target="_blank" rel="noopener noreferrer" '
        'class="inline-post-link">'
        'https://example.com/a?b=1&amp;c=2</a><br>끝'
    )


def test_linkify_text_keeps_html_escaped_and_rejects_javascript_urls():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const prefix = src.slice(0, src.indexOf("document.addEventListener('DOMContentLoaded'"));
        eval(prefix);

        if (typeof linkifyText !== 'function') {
          console.error('linkifyText missing');
          process.exit(1);
        }

        const html = linkifyText('<script>alert(1)</script> javascript:alert(1) https://safe.example/path');
        console.log(JSON.stringify({ html }));
        """
    )

    payload = run_node_json(node_script)
    assert "<script>" not in payload["html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in payload["html"]
    assert 'href="javascript:alert(1)"' not in payload["html"]
    assert 'href="https://safe.example/path"' in payload["html"]


def test_linkify_text_does_not_link_truncated_preview_tail_url():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const prefix = src.slice(0, src.indexOf("document.addEventListener('DOMContentLoaded'"));
        eval(prefix);

        if (typeof linkifyText !== 'function') {
          console.error('linkifyText missing');
          process.exit(1);
        }

        const truncated = linkifyText('보기 https://example.com/partial', { isTruncated: true });
        const complete = linkifyText('보기 https://example.com/partial', { isTruncated: false });
        console.log(JSON.stringify({ truncated, complete }));
        """
    )

    payload = run_node_json(node_script)
    assert '<a href=' not in payload["truncated"]
    assert payload["truncated"] == "보기 https://example.com/partial"
    assert 'href="https://example.com/partial"' in payload["complete"]


def test_linkify_text_keeps_sentence_punctuation_outside_link():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const prefix = src.slice(0, src.indexOf("document.addEventListener('DOMContentLoaded'"));
        eval(prefix);

        if (typeof linkifyText !== 'function') {
          console.error('linkifyText missing');
          process.exit(1);
        }

        const html = linkifyText('원문(https://example.com/path).');
        console.log(JSON.stringify({ html }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["html"] == (
        '원문(<a href="https://example.com/path" target="_blank" '
        'rel="noopener noreferrer" class="inline-post-link">'
        'https://example.com/path</a>).'
    )
