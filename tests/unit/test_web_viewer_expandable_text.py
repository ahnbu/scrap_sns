import json
import subprocess
import textwrap
from pathlib import Path


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


def test_get_read_more_indicator_html_switches_between_states():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const start = src.indexOf('function getReadMoreIndicatorHtml(isExpanded) {');
        if (start === -1) {
          console.error('getReadMoreIndicatorHtml missing');
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
          console.error('getReadMoreIndicatorHtml parse failure');
          process.exit(1);
        }

        eval(src.slice(start, end));

        const result = {
          collapsed: getReadMoreIndicatorHtml(false),
          expanded: getReadMoreIndicatorHtml(true)
        };

        console.log(JSON.stringify({ result }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["result"]["collapsed"] == '<span>Read more</span><span class="material-symbols-outlined text-[14px]">expand_more</span>'
    assert payload["result"]["expanded"] == '<span>Show less</span><span class="material-symbols-outlined text-[14px]">expand_less</span>'


def test_toggle_expandable_text_flips_clamp_and_indicator_html():
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

        eval(extractFunction('getReadMoreIndicatorHtml'));
        eval(extractFunction('toggleExpandableText'));

        function createParagraph(initiallyCollapsed) {
          const classes = new Set(initiallyCollapsed ? ['line-clamp-4'] : []);
          return {
            classList: {
              contains(name) {
                return classes.has(name);
              },
              add(name) {
                classes.add(name);
              },
              remove(name) {
                classes.delete(name);
              }
            },
            snapshot() {
              return Array.from(classes).sort();
            }
          };
        }

        const collapsedParagraph = createParagraph(true);
        const collapsedIndicator = { innerHTML: '' };
        toggleExpandableText(collapsedParagraph, collapsedIndicator);

        const expandedParagraph = createParagraph(false);
        const expandedIndicator = { innerHTML: '' };
        toggleExpandableText(expandedParagraph, expandedIndicator);

        console.log(JSON.stringify({
          collapsed: {
            classes: collapsedParagraph.snapshot(),
            indicator: collapsedIndicator.innerHTML
          },
          expanded: {
            classes: expandedParagraph.snapshot(),
            indicator: expandedIndicator.innerHTML
          }
        }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["collapsed"] == {
        "classes": [],
        "indicator": '<span>Show less</span><span class="material-symbols-outlined text-[14px]">expand_less</span>',
    }
    assert payload["expanded"] == {
        "classes": ["line-clamp-4"],
        "indicator": '<span>Read more</span><span class="material-symbols-outlined text-[14px]">expand_more</span>',
    }


def test_web_viewer_long_text_click_binding_targets_indicator_only():
    src = Path("web_viewer/script.js").read_text(encoding="utf-8")
    assert "content.addEventListener('click'" not in src
    assert "indicator.addEventListener('click'" in src
    assert "group/text" not in src
    assert "select-none" not in src
