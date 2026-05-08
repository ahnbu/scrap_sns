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
          sns_tag_catalog: JSON.stringify({
            AI: { primary: false, aliases: ['artificial intelligence'] }
          })
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
            const requestPayload = JSON.parse(options.body || '{}');
            const expectedRules = [
              { keyword: 'AI', tag: 'AI', match_field: 'all' },
              { keyword: 'artificial intelligence', tag: 'AI', match_field: 'all' }
            ];
            if (JSON.stringify(requestPayload.rules) !== JSON.stringify(expectedRules)) {
              throw new Error(`Unexpected rules: ${JSON.stringify(requestPayload.rules)}`);
            }
            return {
              ok: true,
              json: async () => ({
                url_to_auto_tags: {
                  'https://www.threads.com/@alice/post/ABC123': ['AI']
                },
                matched_post_count: 1,
                rule_count: 2
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

        eval(extractFunction('normalizeTagCatalog'));
        eval(extractFunction('buildAutoTagRulesFromCatalog'));
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
        "result": {"matchedPostCount": 1, "ruleCount": 2},
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


def test_build_tag_catalog_from_existing_state_migrates_alias_rules_and_primary():
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

          return src.slice(start, end);
        }

        eval(extractFunction('normalizeTagCatalog'));
        eval(extractFunction('mergeLegacyAutoTagRulesIntoCatalog'));
        eval(extractFunction('buildTagCatalogFromExistingState'));

        const postTags = {
          'https://example.com/1': ['리서치', '클로드'],
          'https://example.com/2': ['리서치']
        };
        const tagTypes = { '클로드': 'primary' };
        const legacyRules = [
          { keyword: '심층리서치', tag: '리서치' },
          { keyword: 'research', tag: '리서치' },
          { keyword: '리서치', tag: '리서치' },
          { keyword: 'Claude Code', tag: '클로드' }
        ];

        const catalog = buildTagCatalogFromExistingState(postTags, tagTypes, legacyRules);
        console.log(JSON.stringify(catalog));
        """
    )

    payload = run_node_json(node_script)
    assert payload == {
        "리서치": {"primary": False, "aliases": ["심층리서치", "research"]},
        "클로드": {"primary": True, "aliases": ["Claude Code"]},
    }


def test_merge_legacy_auto_tag_rules_into_existing_catalog():
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

          return src.slice(start, end);
        }

        eval(extractFunction('mergeLegacyAutoTagRulesIntoCatalog'));

        const catalog = {
          '리서치': { primary: false, aliases: ['research'] }
        };
        const changed = mergeLegacyAutoTagRulesIntoCatalog(catalog, [
          { keyword: '심층리서치', tag: '리서치' },
          { keyword: 'research', tag: '리서치' },
          { keyword: 'Claude Code', tag: '클로드' }
        ]);

        console.log(JSON.stringify({ changed, catalog }));
        """
    )

    payload = run_node_json(node_script)
    assert payload == {
        "changed": True,
        "catalog": {
            "리서치": {"primary": False, "aliases": ["research", "심층리서치"]},
            "클로드": {"primary": False, "aliases": ["Claude Code"]},
        },
    }


def test_build_auto_tag_rules_from_catalog_includes_tag_name_and_aliases():
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

          return src.slice(start, end);
        }

        eval(extractFunction('normalizeTagCatalog'));
        eval(extractFunction('buildAutoTagRulesFromCatalog'));

        const rules = buildAutoTagRulesFromCatalog({
          '리서치': { primary: false, aliases: ['심층리서치', 'research', '리서치'] },
          '클로드': { primary: true, aliases: ['Claude Code'] }
        });
        console.log(JSON.stringify(rules));
        """
    )

    payload = run_node_json(node_script)
    assert payload == [
        {"keyword": "리서치", "tag": "리서치", "match_field": "all"},
        {"keyword": "심층리서치", "tag": "리서치", "match_field": "all"},
        {"keyword": "research", "tag": "리서치", "match_field": "all"},
        {"keyword": "클로드", "tag": "클로드", "match_field": "all"},
        {"keyword": "Claude Code", "tag": "클로드", "match_field": "all"},
    ]


def test_rename_and_delete_tag_update_catalog_and_post_tags():
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

          return src.slice(start, end);
        }

        eval(extractFunction('normalizeTagCatalog'));
        eval(extractFunction('renameTagInState'));
        eval(extractFunction('deleteTagFromState'));

        const postTags = {
          'https://example.com/1': ['리서치', '클로드'],
          'https://example.com/2': ['리서치'],
          'https://example.com/3': ['디자인']
        };
        const catalog = {
          '리서치': { primary: false, aliases: ['research'] },
          '클로드': { primary: true, aliases: [] },
          '디자인': { primary: false, aliases: ['design'] }
        };

        renameTagInState(postTags, catalog, '리서치', '연구');
        deleteTagFromState(postTags, catalog, '클로드');

        console.log(JSON.stringify({ postTags, catalog }));
        """
    )

    payload = run_node_json(node_script)
    assert payload == {
        "postTags": {
            "https://example.com/1": ["연구"],
            "https://example.com/2": ["연구"],
            "https://example.com/3": ["디자인"],
        },
        "catalog": {
            "연구": {"primary": False, "aliases": ["research"]},
            "디자인": {"primary": False, "aliases": ["design"]},
        },
    }
