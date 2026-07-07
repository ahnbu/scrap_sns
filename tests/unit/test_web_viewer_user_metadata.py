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
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _extract_helper_script():
    return """
    const fs = require('fs');
    const src = fs.readFileSync('web_viewer/script.js', 'utf8');
    function extractFunction(name) {
      const patterns = [`function ${name}(`, `async function ${name}(`];
      let start = -1;
      for (const pattern of patterns) {
        start = src.indexOf(pattern);
        if (start !== -1) break;
      }
      if (start === -1) throw new Error(`${name} missing`);
      let depth = 0;
      for (let i = start; i < src.length; i += 1) {
        if (src[i] === '{') depth += 1;
        if (src[i] === '}') {
          depth -= 1;
          if (depth === 0) return src.slice(start, i + 1);
        }
      }
      throw new Error(`${name} parse failure`);
    }
    function resolvePostKey(post) {
      return post.post_key;
    }
    function resolvePostUrl(post) {
      return post.canonical_url;
    }
    function getKstIsoString() {
      return '2026-07-07T11:06:00+09:00';
    }
    """


def test_merge_legacy_state_into_user_metadata():
    node_script = textwrap.dedent(
        _extract_helper_script()
        + """
        eval(extractFunction('mergeLegacyStateIntoUserMetadata'));
        const posts = [
          {
            post_key: 'threads:ABC123',
            canonical_url: 'https://www.threads.com/@alice/post/ABC123'
          }
        ];
        const metadata = {};
        mergeLegacyStateIntoUserMetadata(
          metadata,
          posts,
          ['https://www.threads.com/@alice/post/ABC123'],
          ['https://www.threads.com/@alice/post/ABC123']
        );
        console.log(JSON.stringify(metadata));
        """
    )

    assert run_node_json(node_script) == {
        "threads:ABC123": {
            "canonical_url": "https://www.threads.com/@alice/post/ABC123",
            "favorite": True,
            "hidden": True,
            "updated_at": "2026-07-07T11:06:00+09:00",
        }
    }


def test_legacy_favorites_are_not_reapplied_after_migration_flag():
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        function extractFunction(name) {
          const start = src.indexOf(`function ${name}(`);
          if (start === -1) throw new Error(`${name} missing`);
          let depth = 0;
          for (let i = start; i < src.length; i += 1) {
            if (src[i] === '{') depth += 1;
            if (src[i] === '}') {
              depth -= 1;
              if (depth === 0) return src.slice(start, i + 1);
            }
          }
          throw new Error(`${name} parse failure`);
        }
        const storage = { sns_user_metadata_legacy_migrated: 'true' };
        global.localStorage = {
          getItem(key) {
            return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null;
          }
        };
        eval(extractFunction('shouldMergeLegacyUserMetadata'));
        console.log(JSON.stringify({ shouldMergeLegacy: shouldMergeLegacyUserMetadata() }));
        """
    )

    assert run_node_json(node_script) == {
        "shouldMergeLegacy": False,
    }


def test_set_user_metadata_entry_updates_and_prunes_state():
    node_script = textwrap.dedent(
        _extract_helper_script()
        + """
        eval(extractFunction('pruneUserMetadataEntry'));
        eval(extractFunction('setUserMetadataEntry'));
        const metadata = {};
        const post = {
          post_key: 'threads:ABC123',
          canonical_url: 'https://www.threads.com/@alice/post/ABC123'
        };
        setUserMetadataEntry(metadata, post, { favorite: true });
        setUserMetadataEntry(metadata, post, { favorite: false });
        console.log(JSON.stringify(metadata));
        """
    )

    assert run_node_json(node_script) == {}


def test_set_note_prunes_empty_note():
    node_script = textwrap.dedent(
        _extract_helper_script()
        + """
        eval(extractFunction('pruneUserMetadataEntry'));
        const favoriteOnly = pruneUserMetadataEntry({ favorite: true, note: '   ' });
        const empty = pruneUserMetadataEntry({ note: '   ' });
        console.log(JSON.stringify({ favoriteOnly, empty }));
        """
    )

    assert run_node_json(node_script) == {
        "favoriteOnly": {"favorite": True},
        "empty": None,
    }


def test_build_user_note_signature_uses_only_non_empty_notes():
    node_script = textwrap.dedent(
        _extract_helper_script()
        + """
        eval(extractFunction('buildUserNoteSignature'));
        const signature = buildUserNoteSignature({
          'threads:B': { note: '  second  ', favorite: true },
          'threads:A': { note: 'first' },
          'threads:C': { favorite: true },
          'threads:D': { note: '   ' }
        });
        console.log(JSON.stringify({ signature }));
        """
    )

    assert run_node_json(node_script) == {
        "signature": '[[\"threads:A\",\"first\"],[\"threads:B\",\"second\"]]',
    }


def test_render_note_section_displays_existing_note():
    node_script = textwrap.dedent(
        _extract_helper_script()
        + """
        const userMetadata = {
          'threads:ABC123': {
            canonical_url: 'https://www.threads.com/@alice/post/ABC123',
            note: '확인할 인사이트'
          }
        };
        function escapeHtml(value) {
          return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        }
        eval(extractFunction('renderNoteSection'));
        const container = { innerHTML: '' };
        renderNoteSection(container, {
          post_key: 'threads:ABC123',
          canonical_url: 'https://www.threads.com/@alice/post/ABC123'
        });
        console.log(JSON.stringify({
          hasTitle: container.innerHTML.includes('메모'),
          hasNote: container.innerHTML.includes('확인할 인사이트')
        }));
        """
    )

    assert run_node_json(node_script) == {
        "hasTitle": True,
        "hasNote": True,
    }
