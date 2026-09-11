"""뷰어 자동 태그 규칙.

서버 `POST /api/auto-tag/apply` 와 `scripts/migrate_library_auto_tags.py` 가 함께 쓴다.
규칙 원천은 태그 카탈로그(`web_viewer/sns_tag_catalog.json`)다 — 태그 이름과 별칭이
키워드가 된다. 뷰어 `buildAutoTagRulesFromCatalog()`(`web_viewer/script.js`)와 같은 규칙을
만든다.

볼트 자료 카드(web·file)는 두 가지가 SNS 글과 다르다.

- **훑는 범위**: 제목 + 본문 앞 800자. 노트 본문 전체(최대 69만 자)를 훑으면 거의 모든
  키워드가 걸려 자료 카드 평균 5.3개·최대 19개 태그가 붙었다(2026-09-11 실측).
- **볼트 분류 합류**: 노트의 주제(`library_topic`)와 태그(`library_tags`)를 카탈로그 태그
  이름으로 바꿔 더한다. 볼트 어휘(제미나이·영상이미지)와 뷰어 어휘(gemini·이미지)가 달라
  대응이 필요하다. 카탈로그 태그 이름·별칭과 똑같으면 그대로 잇고, 복합 주제만 아래
  대응표가 잇는다. 카탈로그에 없는 태그는 내보내지 않는다 — 카탈로그가 정본이다.

계획: _docs/20260911_02 (W3)
"""
from __future__ import annotations

LIBRARY_PLATFORMS = ("web", "file")
LIBRARY_SCAN_CHARS = 800
# 검증 전용 서버가 운영 태그 파일에 남긴 임시 볼트 경로 키의 표식(계획 F11).
JUNK_KEY_MARKER = "sns-library-verify-"

# 볼트 복합 주제 → 카탈로그 태그. 키는 소문자로 비교한다.
VAULT_TERM_MAP = {
    "영상이미지": ["이미지"],
    "개발디자인": ["디자인"],
    "기획제안": ["기획"],
    "sns마케팅": ["마케팅"],
    "챗gpt코덱스": ["chatgpt", "코덱스"],
    "노션옵시디언": ["노션", "옵시디언"],
    "오픈클로-헤르메스": ["오픈클로"],
}


def build_rules(catalog: dict) -> list[dict]:
    """카탈로그 → 규칙 목록. 뷰어 normalizeTagCatalog + buildAutoTagRulesFromCatalog 와 같다."""
    rules = []
    for raw_tag, meta in (catalog or {}).items():
        tag = str(raw_tag or "").strip()
        if not tag:
            continue
        aliases = []
        for alias in (meta or {}).get("aliases") or []:
            value = str(alias or "").strip()
            if value and value != tag and value not in aliases:
                aliases.append(value)
        seen = set()
        for keyword in [tag, *aliases]:
            if keyword in seen:
                continue
            seen.add(keyword)
            rules.append({"keyword": keyword, "tag": tag, "match_field": "all"})
    return rules


def is_library_post(post: dict) -> bool:
    return str(post.get("sns_platform") or "").lower() in LIBRARY_PLATFORMS


def haystack(post: dict, match_field: str = "all", *, legacy: bool = False) -> str:
    """키워드를 대 볼 글자. `legacy=True` 는 변경 전 범위(자료도 본문 전체)다 — 정리 스크립트 전용."""
    full_text = str(post.get("full_text") or "")
    if is_library_post(post) and not legacy:
        text = f"{post.get('library_title') or ''}\n{full_text[:LIBRARY_SCAN_CHARS]}"
    else:
        text = full_text
    parts = [text, str(post.get("_user_note") or "")]
    if match_field == "all":
        parts.extend([
            str(post.get("display_name") or ""),
            str(post.get("username") or post.get("user") or ""),
        ])
    return " ".join(part for part in parts if part).lower()


def _clean_rules(rules: list) -> list[tuple[str, str, str]]:
    cleaned = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        keyword = str(rule.get("keyword") or "").strip().lower()
        tag = str(rule.get("tag") or "").strip()
        match_field = str(rule.get("match_field") or "all").strip().lower()
        if keyword and tag:
            cleaned.append((keyword, tag, match_field))
    return cleaned


def vault_tags(post: dict, rules: list) -> list[str]:
    """노트 주제·태그 → 카탈로그 태그. 규칙에 있는 태그만 낸다."""
    cleaned = _clean_rules(rules)
    known = []
    by_keyword: dict[str, list[str]] = {}
    for keyword, tag, _ in cleaned:
        if tag not in known:
            known.append(tag)
        by_keyword.setdefault(keyword, [])
        if tag not in by_keyword[keyword]:
            by_keyword[keyword].append(tag)

    terms = [post.get("library_topic"), *(post.get("library_tags") or [])]
    result = []
    for term in terms:
        value = str(term or "").strip().lower()
        if not value:
            continue
        candidates = VAULT_TERM_MAP.get(value) or by_keyword.get(value) or []
        for tag in candidates:
            if tag in known and tag not in result:
                result.append(tag)
    return result


def match_post(post: dict, rules: list, *, legacy: bool = False) -> list[str]:
    """글 하나에 붙을 자동 태그. 규칙 순서대로, 중복 없이."""
    matched = []
    cache: dict[str, str] = {}
    for keyword, tag, match_field in _clean_rules(rules):
        if match_field not in cache:
            cache[match_field] = haystack(post, match_field, legacy=legacy)
        if keyword in cache[match_field] and tag not in matched:
            matched.append(tag)
    if is_library_post(post) and not legacy:
        for tag in vault_tags(post, rules):
            if tag not in matched:
                matched.append(tag)
    return matched


def migrate_library_tags(
    tags: dict, library_posts_by_url: dict, rules: list, junk_keys=()
) -> tuple[dict, dict]:
    """이미 붙은 자료 카드 자동 태그를 새 범위로 맞춘다. 입력을 바꾸지 않고 새 맵을 돌려준다.

        새 태그 = (저장된 태그 − (옛 범위 자동 − 새 범위 자동)) ∪ 새 범위 자동

    옛 규칙이 붙였고 새 규칙은 안 붙이는 태그만 뺀다. 규칙으로 설명 안 되는 태그(손으로
    붙인 것)는 남는다. `library_posts_by_url` 에는 SNS 글과 URL 이 겹치지 않는 자료만
    넣는다 — 겹침 노트는 원문 카드와 태그 키를 공유한다(계획 F10).

    지울 키는 삭제하지 않고 빈 배열로 둔다. 뷰어는 로드 때 서버 값으로 키를 덮어쓰고 빈
    배열을 지운 뒤 저장한다 — 서버에서 키를 없애면 브라우저 사본이 다음 저장에 되살린다(F12).
    """
    result = {key: list(value) if isinstance(value, list) else value for key, value in tags.items()}
    summary = {"library_keys": 0, "changed_keys": 0, "removed_tags": 0, "added_tags": 0, "junk_keys": 0}

    for url, post in library_posts_by_url.items():
        summary["library_keys"] += 1
        stored = [tag for tag in (result.get(url) or []) if isinstance(tag, str) and tag.strip()]
        new = match_post(post, rules)
        drop = set(match_post(post, rules, legacy=True)) - set(new)
        kept = [tag for tag in stored if tag not in drop]
        added = [tag for tag in new if tag not in kept]
        final = kept + added
        if final != stored:
            summary["changed_keys"] += 1
            summary["removed_tags"] += len(stored) - len(kept)
            summary["added_tags"] += len(added)
        if final or url in result:
            result[url] = final

    # 운영 데이터가 아닌 키 — 임시 볼트 경로(표식), 그리고 호출자가 넘기는 검증 표본 노트의
    # 원문 URL(검증 서버가 운영 태그에 남겼다). 삭제 대신 빈 배열로 둔다(위 F12).
    junk = set(junk_keys or ())
    for key in list(result):
        if (JUNK_KEY_MARKER in key or key in junk) and result[key]:
            result[key] = []
            summary["junk_keys"] += 1
    return result, summary
