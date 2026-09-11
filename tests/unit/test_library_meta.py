"""자료 전용 필드가 목록 응답에서 떨어지지 않는다(META_FIELDS 함정).

`utils/post_meta.build_post_meta()` 는 META_FIELDS 밖 필드를 버린다. 이 레포가
세 번 겪은 조용한 실패라 필드마다 단언한다. 계획: _docs/20260911_01 (W2 T2-d)
"""
import os

from utils.library_index import build_library_posts
from utils.post_meta import META_FIELDS, build_post_meta

VAULT = os.path.join("tests", "fixtures", "golden", "library", "vault")
LIBRARY_FIELDS = [
    "library_title",
    "library_path",
    "library_topic",
    "library_tags",
    "library_source_type",
    "library_creator",
    "library_obsidian_url",
    "library_has_source_file",
    "library_source_file_url",
    "sort_seq",
    "library_notes",
]


def test_library_fields_are_whitelisted():
    missing = [field for field in LIBRARY_FIELDS if field not in META_FIELDS]
    assert not missing


def test_build_post_meta_keeps_library_values():
    post = next(p for p in build_library_posts(VAULT) if p["sns_platform"] == "file" and p["library_has_source_file"])
    post["sequence_id"] = 99
    post["sort_seq"] = 3.5
    meta = build_post_meta(post)

    assert meta["post_key"] == "file:20260102_파일자료_라마바"
    assert meta["library_title"] == "파일 자료 표본"
    assert meta["library_topic"] == "AI일반"
    assert meta["library_tags"] == ["노트북LM", "요약"]
    assert meta["library_has_source_file"] is True
    assert meta["library_obsidian_url"].startswith("obsidian://")
    assert meta["sort_seq"] == 3.5
    assert meta["is_saved"] is True
    assert meta["full_text_preview"].startswith("# 파일 자료 표본")


def test_library_preview_is_longer_than_sns_preview():
    """자료 카드는 기호를 걷고 6줄을 보이므로 600자, SNS 글은 200자 그대로(계획 20260911_02 W4 T4-c)."""
    body = "가" * 1000
    assert len(build_post_meta({"sns_platform": "file", "platform_id": "a", "full_text": body})["full_text_preview"]) == 600
    assert len(build_post_meta({"sns_platform": "web", "platform_id": "b", "full_text": body})["full_text_preview"]) == 600
    assert len(build_post_meta({"sns_platform": "threads", "platform_id": "c", "full_text": body})["full_text_preview"]) == 200


def test_sns_post_keeps_library_notes_link():
    meta = build_post_meta(
        {
            "sns_platform": "threads",
            "platform_id": "A1",
            "full_text": "x",
            "library_notes": [{"sequence_id": 5, "title": "요약", "path": "a/b.md"}],
        }
    )
    assert meta["library_notes"] == [{"sequence_id": 5, "title": "요약", "path": "a/b.md"}]
