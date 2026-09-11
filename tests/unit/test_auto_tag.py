"""자동 태그 규칙 — 자료 카드 훑는 범위·볼트 분류 합류·기존 태그 정리.

계획: _docs/20260911_02 (W3 T3-a·T3-f)
"""
import json
import subprocess
import textwrap

from utils.auto_tag import (
    JUNK_KEY_MARKER,
    LIBRARY_SCAN_CHARS,
    build_rules,
    match_post,
    migrate_library_tags,
    vault_tags,
)

CATALOG = {
    "gemini": {"aliases": ["제미나이", "agy"], "primary": False},
    "chatgpt": {"aliases": ["gpt", "챗GPT", "codex", "코덱스"], "primary": False},
    "코덱스": {"aliases": ["codex"], "primary": False},
    "이미지": {"aliases": [], "primary": False},
    "프롬프트": {"aliases": ["prompt"], "primary": False},
    "클로드": {"aliases": ["claude"], "primary": False},
    "리서치": {"aliases": ["research"], "primary": False},
}
RULES = build_rules(CATALOG)
FILLER = "가" * (LIBRARY_SCAN_CHARS + 50)


def _library(**overrides):
    post = {
        "sns_platform": "file",
        "library_title": "",
        "full_text": "",
        "display_name": "홍길동",
        "username": "홍길동",
        "library_topic": "AI일반",
        "library_tags": [],
    }
    post.update(overrides)
    return post


def test_rules_match_viewer_builder():
    """서버 규칙이 뷰어 buildAutoTagRulesFromCatalog() 와 같아야 정리 결과가 뷰어 적용과 맞는다."""
    with open("web_viewer/sns_tag_catalog.json", encoding="utf-8") as handle:
        catalog = json.load(handle)
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        function extractFunction(name) {
          const start = src.indexOf(`function ${name}(`);
          let depth = 0;
          for (let i = start; i < src.length; i += 1) {
            if (src[i] === '{') depth += 1;
            if (src[i] === '}') { depth -= 1; if (depth === 0) return src.slice(start, i + 1); }
          }
          throw new Error(name);
        }
        eval(extractFunction('normalizeTagCatalog'));
        eval(extractFunction('buildAutoTagRulesFromCatalog'));
        const catalog = JSON.parse(fs.readFileSync('web_viewer/sns_tag_catalog.json', 'utf8'));
        console.log(JSON.stringify(buildAutoTagRulesFromCatalog(catalog)));
        """
    )
    completed = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == build_rules(catalog)


def test_sns_post_still_scans_whole_text():
    post = {"sns_platform": "threads", "full_text": FILLER + " claude"}
    assert match_post(post, RULES) == ["클로드"]


def test_library_post_ignores_keywords_after_scan_window():
    post = _library(full_text=FILLER + " claude research")
    assert match_post(post, RULES) == []
    # 변경 전 범위(정리 스크립트 전용)는 본문 전체를 본다.
    assert match_post(post, RULES, legacy=True) == ["클로드", "리서치"]


def test_library_title_is_scanned():
    post = _library(library_title="Claude 프롬프트 모음", full_text=FILLER)
    assert match_post(post, RULES) == ["프롬프트", "클로드"]


def test_vault_terms_map_to_catalog_tags():
    post = _library(library_topic="챗GPT코덱스", library_tags=["제미나이", "AI일반", "템플릿"])
    assert vault_tags(post, RULES) == ["chatgpt", "코덱스", "gemini"]


def test_vault_compound_topic_uses_map():
    assert vault_tags(_library(library_topic="영상이미지"), RULES) == ["이미지"]


def test_vault_tags_skip_tags_missing_from_catalog():
    rules = build_rules({"클로드": {"aliases": ["claude"]}})
    assert vault_tags(_library(library_topic="영상이미지", library_tags=["클로드"]), rules) == ["클로드"]


def test_vault_tags_join_match_result():
    post = _library(library_title="claude", library_topic="제미나이")
    assert match_post(post, RULES) == ["클로드", "gemini"]


def test_sns_post_gets_no_vault_tags():
    post = {"sns_platform": "threads", "full_text": "", "library_topic": "제미나이"}
    assert match_post(post, RULES) == []


def test_server_apply_uses_library_scope(client, monkeypatch):
    import scrap_sns_server as server

    posts = [
        {"canonical_url": "https://a", **_library(full_text=FILLER + " claude", library_topic="제미나이")},
        {"canonical_url": "https://b", "sns_platform": "threads", "full_text": FILLER + " claude"},
    ]
    monkeypatch.setattr(server, "_load_latest_posts", lambda: {"posts_full": posts})
    response = client.post("/api/auto-tag/apply", json={"rules": RULES})
    assert response.status_code == 200
    assert response.get_json()["url_to_auto_tags"] == {"https://a": ["gemini"], "https://b": ["클로드"]}


def test_migrate_removes_only_legacy_scope_tags():
    url = "obsidian://open?path=x"
    post = _library(library_title="claude", full_text=FILLER + " research", library_topic="제미나이")
    tags = {url: ["리서치", "클로드", "수동"], "https://sns": ["리서치"]}
    result, summary = migrate_library_tags(tags, {url: post}, RULES)
    assert result[url] == ["클로드", "수동", "gemini"]
    assert result["https://sns"] == ["리서치"]
    assert summary["removed_tags"] == 1 and summary["added_tags"] == 1 and summary["changed_keys"] == 1
    assert tags[url] == ["리서치", "클로드", "수동"]  # 입력을 바꾸지 않는다


def test_migrate_is_idempotent():
    url = "https://lib"
    post = _library(sns_platform="web", full_text=FILLER + " research")
    once, _ = migrate_library_tags({url: ["리서치"]}, {url: post}, RULES)
    twice, summary = migrate_library_tags(once, {url: post}, RULES)
    assert once == twice == {url: []}
    assert summary["changed_keys"] == 0


def test_migrate_blanks_junk_keys_instead_of_deleting():
    junk = f"obsidian://open?path=C%3A%2FTemp%2F{JUNK_KEY_MARKER}abc%2Fnote.md"
    result, summary = migrate_library_tags({junk: ["이미지"]}, {}, RULES)
    assert result == {junk: []}
    assert summary["junk_keys"] == 1


def test_migrate_blanks_given_fixture_keys_only():
    fixture = "https://www.threads.com/@hong/post/DAbc123XYZ?xmt=AQF0tracking"
    tags = {fixture: ["SNS노하우"], "https://real": ["클로드"]}
    result, summary = migrate_library_tags(tags, {}, RULES, junk_keys={fixture})
    assert result == {fixture: [], "https://real": ["클로드"]}
    assert summary["junk_keys"] == 1
