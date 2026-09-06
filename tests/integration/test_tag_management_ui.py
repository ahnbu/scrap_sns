import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _element_class_tokens(html: str, element_id: str) -> set[str]:
    """`id="<element_id>"` 를 가진 요소의 class 토큰 집합을 돌려준다.

    여는 태그 안에서 id 와 class 의 순서·줄바꿈·들여쓰기에 의존하지 않는다.
    """
    start = html.index(f'id="{element_id}"')
    open_tag_start = html.rindex("<", 0, start)
    open_tag_end = html.index(">", start)
    open_tag = html[open_tag_start : open_tag_end + 1]

    match = re.search(r'class="([^"]*)"', open_tag)
    assert match, f'{element_id} 요소에 class 속성이 없다: {open_tag!r}'
    return set(match.group(1).split())


def _render_tag_management_block():
    script = (PROJECT_ROOT / "web_viewer" / "script.js").read_text(encoding="utf-8")
    start = script.index("function renderTagManagementList()")
    end = script.index("function renderInvisibleList()")
    return script[start:end]


def _tag_management_crud_block():
    """태그 관리 CRUD 구간만 자른다.

    끝을 `renderInvisibleList()` 로 잡는다. 종전에는 `const runBatchAutoTagBtn`
    까지 늘려 잡아 **숨김 목록 기능(renderInvisibleList) 전체가 범위에 딸려
    들어왔고**, 거기 있는 `alert('숨김 복구 저장에 실패했습니다.')` 때문에
    태그 관리와 무관한 이유로 test_tag_management_crud_does_not_use_browser_prompts
    가 실패했다. 위 `_render_tag_management_block()` 은 처음부터 이 경계를 쓴다.
    """
    script = (PROJECT_ROOT / "web_viewer" / "script.js").read_text(encoding="utf-8")
    start = script.index("function renderTagManagementList()")
    end = script.index("function renderInvisibleList()")
    return script[start:end]


def test_tag_management_hides_primary_controls():
    block = _render_tag_management_block()

    assert "tag-primary-toggle" not in block
    assert ">Primary<" not in block
    assert "Primary 설정" not in block


def test_tag_management_uses_keyword_row_and_icon_add_button():
    block = _render_tag_management_block()
    style = (PROJECT_ROOT / "web_viewer" / "style.css").read_text(encoding="utf-8")

    assert "tag-alias-label" not in block
    assert "키워드" not in block
    assert "add_circle" in block
    assert "edit</span>" in block
    assert "delete</span>" in block
    assert 'text-[11px]">close</span>' in block
    assert 'text-[13px]">close</span>' not in block
    assert "tag-icon-action" in block
    assert "tag-alias-list" in block
    assert ".tag-alias-list" in style
    assert "overflow-x: auto" in style


def test_tag_management_crud_does_not_use_browser_prompts():
    block = _tag_management_crud_block()

    assert "prompt(" not in block
    assert "confirm(" not in block
    assert "alert(" not in block


def test_tag_management_uses_visible_crud_actions():
    block = _tag_management_crud_block()

    assert 'aria-label="이름 변경"' in block
    assert 'aria-label="삭제"' in block
    assert "저장" in block
    assert "취소" in block
    assert "tag-row-action" not in block
    assert "tag-menu-btn" not in block


def test_management_modal_opens_tag_tab_first():
    html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "web_viewer" / "script.js").read_text(encoding="utf-8")

    assert html.index('data-target="tabTags"') < html.index('data-target="tabHidden"')

    # 클래스 문자열을 줄바꿈·들여쓰기까지 통째로 대조하지 않는다. 종전 방식은
    # 마크업을 한 단 감싸기만 해도 깨졌고, 실제로 설정 모달을 세로 레일로 바꿀 때
    # 깨졌다. 확인하려는 것은 "탭 패널이 어떤 상태로 열리는가"이므로 클래스 토큰
    # 포함 여부만 본다. 계획: _docs/20260906_02 (T4)
    tab_tags_classes = _element_class_tokens(html, "tabTags")
    assert "tab-pane" in tab_tags_classes
    assert "hidden" not in tab_tags_classes, "태그 관리 탭이 기본으로 열려 있어야 한다"

    tab_hidden_classes = _element_class_tokens(html, "tabHidden")
    assert "tab-pane" in tab_hidden_classes
    assert "hidden" in tab_hidden_classes, "숨김 관리 탭은 기본으로 닫혀 있어야 한다"

    assert "switchTab('tabTags')" in script
