"""API surface가 문서와 일치하는지 검증한다.

라우트를 추가·삭제하면 _docs/architecture.md도 함께 고쳐야 한다.
이 테스트가 실패하면 코드가 아니라 문서를 먼저 확인할 것.
"""
import os
import re

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC_PATH = os.path.join(_REPO_ROOT, "_docs", "architecture.md")
EXPECTED_ROUTE_COUNT = 18


def _code_routes(app):
    return {
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/")
    }


def _doc_routes():
    """백틱으로 감싼 코드 표기만 라우트로 인정한다.

    산문 중 와일드카드 형태의 /api/ 언급을 오탐하지 않기 위함이다.
    """
    with open(DOC_PATH, encoding="utf-8") as f:
        text = f.read()
    found = re.findall(
        r"`(?:GET|POST|PUT|DELETE)?\s*(/api/[A-Za-z0-9/<>:_-]+)`", text
    )
    return {m for m in found if not m.endswith("/")}


def _normalize(route):
    """/api/post/<int:sequence_id> → /api/post/"""
    return route.split("<")[0]


def test_all_code_routes_documented(app):
    code = {_normalize(r) for r in _code_routes(app)}
    doc = {_normalize(r) for r in _doc_routes()}
    missing = sorted(code - doc)
    assert not missing, (
        f"코드에 있으나 {DOC_PATH}에 없는 라우트: {missing}"
    )


def test_no_phantom_routes_in_doc(app):
    code = {_normalize(r) for r in _code_routes(app)}
    doc = {_normalize(r) for r in _doc_routes()}
    phantom = sorted(doc - code)
    assert not phantom, (
        f"{DOC_PATH}에 있으나 코드에 없는 라우트: {phantom}"
    )


def test_route_count_is_pinned(app):
    actual = len(_code_routes(app))
    assert actual == EXPECTED_ROUTE_COUNT, (
        f"API 라우트 수가 {EXPECTED_ROUTE_COUNT} → {actual}로 변경됐습니다. "
        f"{DOC_PATH}를 갱신하고 EXPECTED_ROUTE_COUNT도 함께 고치세요."
    )
