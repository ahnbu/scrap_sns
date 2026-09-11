"""볼트 자료 인덱스 변환 규칙. 계획: _docs/20260911_01 (W2 T2-a·T2-b)."""
import hashlib
import json
import os

import pytest

from utils.library_index import (
    build_library_posts,
    link_library_posts,
    orphan_metadata_keys,
    parse_wikilink,
    split_frontmatter,
    url_key,
    vault_state,
)

GOLDEN = os.path.join("tests", "fixtures", "golden", "library")
VAULT = os.path.join(GOLDEN, "vault")


def _by_path(posts):
    return {post["library_path"]: post for post in posts}


def test_frontmatter_survives_dashes_inside_values():
    """`text.split("---")` 는 경로 속 `-----` 에서 잘린다 - 19건이 조용히 빠졌던 결함."""
    text = open(os.path.join(VAULT, "AI일반", "20260101_웹자료_가나다.md"), encoding="utf-8").read()
    front, body = split_frontmatter(text)
    assert front["topic"] == "AI일반"
    assert front["creator"] == "[[가나다|가나다 표시]]"
    assert front["tags"] == ["프롬프트", "에이전트"]
    assert body.startswith("# 웹 자료 표본")
    assert "구분선 아래에도 --- 가 있다" in body


def test_inline_list_and_missing_frontmatter():
    front, _ = split_frontmatter("---\ntags: [a, \"b\"]\ntitle: 'x'\n---\n본문")
    assert front == {"tags": ["a", "b"], "title": "x"}
    assert split_frontmatter("# 제목만")[0] == {}


@pytest.mark.parametrize("url,expected", json.load(open(os.path.join(GOLDEN, "url_keys.json"), encoding="utf-8")))
def test_url_key_golden(url, expected):
    assert url_key(url) == expected


def test_parse_wikilink():
    assert parse_wikilink('"[[가나다|가나다 표시]]"'.strip('"')) == ("가나다", "가나다 표시")
    assert parse_wikilink("[[_제작자별_상세/라마바.md]]") == ("라마바", "라마바")
    assert parse_wikilink("평문") == ("평문", "평문")


def test_selection_rule_uses_frontmatter_not_folders():
    paths = set(_by_path(build_library_posts(VAULT)))
    assert paths == {
        "AI일반/20260101_웹자료_가나다.md",
        "AI일반/20260102_파일자료_라마바.md",
        "클로드/20260105_스레드겹침_홍길동.md",
        "보안표본/20260106_악성표본_테스트.md",
    }


def test_field_conversion_web_and_file():
    posts = _by_path(build_library_posts(VAULT))
    web = posts["AI일반/20260101_웹자료_가나다.md"]
    assert web["sns_platform"] == "web"
    assert web["platform_id"] == hashlib.sha1(b"youtube:ABCDEFGHIJK").hexdigest()[:16]
    assert web["username"] == "가나다"
    assert web["display_name"] == "가나다 표시"
    assert web["url"] == "https://www.youtube.com/watch?v=ABCDEFGHIJK&t=30s"
    assert web["created_at"] == "2026-01-01 00:00:00"
    assert web["date"] == "2026-01-01"
    assert web["is_saved"] is True and web["is_own_post"] is False
    assert web["library_topic"] == "AI일반"
    assert web["library_tags"] == ["프롬프트", "에이전트"]
    assert web["library_obsidian_url"].startswith("obsidian://open?path=")
    assert web["library_has_source_file"] is False
    assert "---" not in web["full_text"].splitlines()[0]

    file_post = posts["AI일반/20260102_파일자료_라마바.md"]
    assert file_post["sns_platform"] == "file"
    assert file_post["platform_id"] == "20260102_파일자료_라마바"
    assert file_post["url"] == file_post["library_obsidian_url"]
    assert file_post["created_at"] == "2026-01-02 14:05:00"
    assert file_post["library_tags"] == ["노트북LM", "요약"]
    assert file_post["library_has_source_file"] is True
    assert file_post["library_source_file_url"].endswith("sample.csv")


def test_overlap_notes_link_to_sns_post_and_get_sequence():
    library = build_library_posts(VAULT)
    sns = [
        {
            "sequence_id": 10,
            "sns_platform": "threads",
            "platform_id": "DAbc123XYZ",
            "username": "hong",
            "url": "https://www.threads.net/@hong/post/DAbc123XYZ",
            "crawled_at": "2026-01-04T10:00:00",
        },
        {"sequence_id": 11, "sns_platform": "linkedin", "platform_id": "1", "crawled_at": "2026-01-10T10:00:00"},
    ]
    visible, overlaps = link_library_posts(library, sns, start_seq=12)

    assert [note["library_path"] for note in overlaps] == ["클로드/20260105_스레드겹침_홍길동.md"]
    assert overlaps[0]["library_overlap_of"] == "threads:DAbc123XYZ"
    assert sns[0]["library_notes"] == [
        {"sequence_id": overlaps[0]["sequence_id"], "title": "스레드 겹침 표본", "path": "클로드/20260105_스레드겹침_홍길동.md"}
    ]
    seqs = sorted(note["sequence_id"] for note in visible + overlaps)
    assert seqs == [12, 13, 14, 15]
    # 로컬수집순: 2026-01-01·02 자료는 2026-01-04 수집분(10) 앞, 01-06 자료는 그 뒤.
    by_path = _by_path(visible)
    assert by_path["AI일반/20260101_웹자료_가나다.md"]["sort_seq"] == 0.5
    assert by_path["보안표본/20260106_악성표본_테스트.md"]["sort_seq"] == 10.5


def test_vault_state_changes_when_note_touched(tmp_path):
    folder = tmp_path / "AI일반"
    folder.mkdir()
    note = folder / "a.md"
    note.write_text("---\ntopic: AI일반\ncreator: \"[[x]]\"\n---\n본문", encoding="utf-8")
    before = vault_state(str(tmp_path))
    os.utime(note, ns=(before[1] + 10**9, before[1] + 10**9))
    after = vault_state(str(tmp_path))
    assert before[0] == after[0] == 1
    assert after[1] > before[1]


def test_orphan_metadata_keys_reports_renamed_file_notes():
    library = build_library_posts(VAULT)
    live_key = f"file:{'20260102_파일자료_라마바'}"
    metadata = {live_key: {"favorite": True}, "file:옛이름": {"note": "x"}, "threads:1": {}}
    assert orphan_metadata_keys(metadata, library) == ["file:옛이름"]
