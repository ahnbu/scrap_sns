"""뷰어가 쓰는 Tailwind 유틸리티 클래스가 CSS 에 정의돼 있는가.

`web_viewer/tailwind-built.css` 는 미리 빌드된 파일이고 재빌드 명령이 없다. 거기 없는
클래스는 조용히 무시된다 — 모달 폭(`max-w-3xl`)·본문 여백(`py-5`)·칩 간격(`gap-1.5`)이
그렇게 사라졌고, 모달은 화면 폭 − 32px 로 퍼졌다(2026-09-11 실측 1888px).
새 유틸리티를 쓰면 `style.css` 에 정의를 두거나 의미 클래스로 바꾼다.

템플릿 치환(`${…}`)이 든 토큰은 보지 않는다 — 실행 전에는 값을 모른다.
계획: _docs/20260911_02 (W1 T1-c)
"""
import re

SOURCES = ["index.html", "web_viewer/script.js"]
CSS_FILES = ["web_viewer/tailwind-built.css", "web_viewer/style.css"]

# 알고 두는 예외. 사유 없이 늘리지 않는다.
# (계획 단계에서 `2xl:flex` 를 누락으로 봤으나 빌드 CSS 에 `.\32 xl\:flex` 로 있다 —
#  숫자로 시작하는 클래스는 16진 escape 된다. 그래서 비어 있다.)
KNOWN_UNDEFINED: set[str] = set()

UTILITY = re.compile(
    r"^(?:[a-z0-9]+:)*-?(?:"
    r"bg|text|border|p[xytrbl]?|m[xytrbl]?|gap|space-[xy]|size|w|h|min-w|min-h|max-w|max-h|"
    r"inset|top|right|bottom|left|z|opacity|rounded|shadow|leading|tracking|font|flex|grid|"
    r"items|justify|self|place|overflow|whitespace|line-clamp|accent|ring|cursor|transition|"
    r"duration|ease|delay|scale|translate|rotate|order|basis|grow|shrink|underline|truncate|"
    r"hidden|block|inline|fixed|absolute|relative|sticky|pointer-events|object|aspect|"
    r"backdrop|blur|divide|outline|resize|uppercase|lowercase|italic|antialiased"
    r")(?:-|$)"
)
CLASS_PATTERNS = [
    re.compile(r'class="([^"]*)"'),
    re.compile(r"class='([^']*)'"),
    re.compile(r"className\s*=\s*[`'\"]([^`'\"]*)[`'\"]"),
]
CLASSLIST = re.compile(r"classList\.(?:add|remove|toggle)\(([^)]*)\)")


def _unescape(selector):
    # Tailwind 는 쉼표를 16진 escape(`\2c `)로 쓴다 - 한 글자 escape 보다 먼저 푼다.
    value = re.sub(r"\\([0-9a-fA-F]{1,6}) ?", lambda m: chr(int(m.group(1), 16)), selector)
    return re.sub(r"\\(.)", r"\1", value)


def _defined_classes():
    defined = set()
    for path in CSS_FILES:
        with open(path, encoding="utf-8") as handle:
            css = handle.read()
        for match in re.finditer(r"\.((?:\\[0-9a-fA-F]{1,6} ?|\\.|[A-Za-z0-9_-])+)", css):
            defined.add(_unescape(match.group(1)))
    return defined


def _used_tokens():
    for path in SOURCES:
        with open(path, encoding="utf-8") as handle:
            src = handle.read()
        for pattern in CLASS_PATTERNS:
            for match in pattern.finditer(src):
                value = re.sub(r"\$\{[^}]*\}", " ", match.group(1))
                line = src.count("\n", 0, match.start()) + 1
                for token in value.split():
                    yield token, f"{path}:{line}"
        for match in CLASSLIST.finditer(src):
            line = src.count("\n", 0, match.start()) + 1
            for token in re.findall(r"['\"]([^'\"$]+)['\"]", match.group(1)):
                yield token, f"{path}:{line}"


def test_used_utility_classes_are_defined():
    defined = _defined_classes()
    missing = {}
    for token, where in _used_tokens():
        if "$" in token or not UTILITY.match(token):
            continue
        if token in defined or token in KNOWN_UNDEFINED:
            continue
        missing.setdefault(token, []).append(where)
    assert not missing, "CSS 에 정의가 없는 유틸리티: " + "; ".join(
        f"{token} ({', '.join(places[:3])})" for token, places in sorted(missing.items())
    )


def test_known_undefined_are_still_undefined():
    """예외가 정의되면 목록에서 뺀다 — 예외 목록이 낡은 채 남지 않게."""
    defined = _defined_classes()
    assert not (KNOWN_UNDEFINED & defined)
