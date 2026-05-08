from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _render_tag_management_block():
    script = (PROJECT_ROOT / "web_viewer" / "script.js").read_text(encoding="utf-8")
    start = script.index("function renderTagManagementList()")
    end = script.index("function renderInvisibleList()")
    return script[start:end]


def _tag_management_crud_block():
    script = (PROJECT_ROOT / "web_viewer" / "script.js").read_text(encoding="utf-8")
    start = script.index("function renderTagManagementList()")
    end = script.index("const runBatchAutoTagBtn")
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
    assert 'id="tabTags"\n          class="tab-pane flex-1 flex flex-col overflow-hidden"' in html
    assert 'id="tabHidden"\n          class="tab-pane hidden flex-1 overflow-y-auto no-scrollbar"' in html
    assert "switchTab('tabTags')" in script
