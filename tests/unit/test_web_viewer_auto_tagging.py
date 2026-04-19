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


def test_apply_auto_tags_function_is_removed_after_server_delegation():
    with open("web_viewer/script.js", "r", encoding="utf-8") as handle:
        src = handle.read()

    assert "async function applyAutoTags(" not in src
    assert "async function applyAutoTagRules(" in src


def test_apply_auto_tag_rules_merges_server_tags_additively():
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

        const storage = {
          sns_auto_tag_rules: JSON.stringify([{ keyword: 'ai', tag: 'AI' }])
        };
        let savedPayload = null;
        let renderCalls = 0;
        global.postTags = {
          'https://www.threads.com/@alice/post/ABC123': ['Manual']
        };
        global.localStorage = {
          getItem(key) {
            return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null;
          },
          setItem(key, value) {
            storage[key] = String(value);
          }
        };
        global.updateGlobalTags = () => {};
        global.renderPosts = () => {
          renderCalls += 1;
        };
        global.fetch = async (url, options = {}) => {
          if (url === '/api/auto-tag/apply') {
            return {
              ok: true,
              json: async () => ({
                url_to_auto_tags: {
                  'https://www.threads.com/@alice/post/ABC123': ['AI']
                },
                matched_post_count: 1,
                rule_count: 1
              })
            };
          }
          if (url === '/api/save-tags') {
            savedPayload = JSON.parse(options.body || '{}');
            return {
              ok: true,
              json: async () => ({ status: 'success' })
            };
          }
          throw new Error(`Unexpected fetch: ${url}`);
        };

        eval(extractFunction('mergeAutoTags'));
        eval(extractFunction('applyAutoTagRules'));

        (async () => {
          const result = await applyAutoTagRules();
          console.log(JSON.stringify({ result, postTags, savedPayload, renderCalls }));
        })().catch((error) => {
          console.error(error);
          process.exit(1);
        });
        """
    )

    payload = run_node_json(node_script)
    assert payload == {
        "result": {"matchedPostCount": 1, "ruleCount": 1},
        "postTags": {
            "https://www.threads.com/@alice/post/ABC123": ["Manual", "AI"],
        },
        "savedPayload": {
            "https://www.threads.com/@alice/post/ABC123": ["Manual", "AI"],
        },
        "renderCalls": 1,
    }


def test_migrate_legacy_tag_keys_repairs_threads_legacy_namespaces_and_states():
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

        const storage = {};
        global.__syncCalls = 0;
        global.postTags = {
          'undefined': [''],
          'ABC123': ['legacy-code'],
          'https://www.threads.net/t/ABC123': ['legacy-t'],
          'https://www.threads.net/@alice/post/ABC123': ['legacy-alice'],
          'https://www.threads.com/@ally/post/ABC123': ['keep'],
          'https://example.com/unmatched': ['other']
        };
        storage.sns_favorites = JSON.stringify([
          'https://www.threads.net/@alice/post/ABC123',
          'https://www.threads.net/t/ABC123'
        ]);
        storage.sns_invisible_posts = JSON.stringify([
          'https://www.threads.net/@alice/post/ABC123'
        ]);
        storage.sns_folded_posts = JSON.stringify([
          'https://www.threads.net/t/ABC123'
        ]);
        storage.sns_todos = JSON.stringify({
          'https://www.threads.net/@alice/post/ABC123': 'pending',
          'https://www.threads.net/t/ABC123': 'completed'
        });
        global.localStorage = {
          getItem(key) {
            return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null;
          },
          setItem(key, value) {
            storage[key] = String(value);
          }
        };
        global.syncTagsToServer = () => {
          global.__syncCalls += 1;
        };

        eval(extractFunction('resolvePostUrl'));
        eval(extractFunction('migrateLegacyTagKeys'));

        const migrated = migrateLegacyTagKeys([
          {
            sns_platform: 'threads',
            user: 'ally',
            platform_id: 'ABC123',
            url: 'https://www.threads.com/@ally/post/ABC123'
          }
        ]);

        console.log(JSON.stringify({
          migrated,
          postTags,
          syncCalls: global.__syncCalls,
          stored: JSON.parse(storage.sns_tags),
          favorites: JSON.parse(storage.sns_favorites),
          invisiblePosts: JSON.parse(storage.sns_invisible_posts),
          foldedPosts: JSON.parse(storage.sns_folded_posts),
          todos: JSON.parse(storage.sns_todos)
        }));
        """
    )

    payload = run_node_json(node_script)
    assert payload["migrated"] == 4
    assert payload["syncCalls"] == 1
    assert payload["postTags"] == {
        "https://www.threads.com/@ally/post/ABC123": [
            "keep",
            "legacy-code",
            "legacy-t",
            "legacy-alice",
        ],
        "https://example.com/unmatched": ["other"],
    }
    assert payload["stored"] == payload["postTags"]
    assert payload["favorites"] == ["https://www.threads.com/@ally/post/ABC123"]
    assert payload["invisiblePosts"] == ["https://www.threads.com/@ally/post/ABC123"]
    assert payload["foldedPosts"] == ["https://www.threads.com/@ally/post/ABC123"]
    assert payload["todos"] == {"https://www.threads.com/@ally/post/ABC123": "completed"}
