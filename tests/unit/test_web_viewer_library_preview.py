"""자료 카드 미리보기 — 줄바꿈을 살리고 마크다운 기호를 걷는다.

종전에는 공백·줄바꿈을 모두 공백 하나로 합쳐 본문이 한 덩어리가 되고 `---` 가 글자로
보였다. 계획: _docs/20260911_02 (W4 T4-a·T4-d)
"""
import json
import subprocess
import textwrap

SAMPLE = "\n".join([
    "# 제미나이 책 제공 실무 프롬프트 및 자료 모음",
    "",
    "> 공냥이 저자의 **Google Gemini** 도서 특별 부록.",
    "",
    "---",
    "",
    "## 포함 자료 목록",
    "",
    "1. **`바로바로_프롬프트.xlsx`**: 업무 즉시 사용",
    "- [[노트북LM|노트북]] 템플릿 [링크](https://x.com/a)",
    "* [[폴더/대상노트]] 참고",
    "![이미지](https://img.example/a.png)",
    "",
    "",
    "| 열1 | 열2 |",
    "|---|:---:|",
    "| a | b |",
    "***",
])

EXPECTED = "\n".join([
    "공냥이 저자의 Google Gemini 도서 특별 부록.",
    "",
    "포함 자료 목록",
    "",
    "1. 바로바로_프롬프트.xlsx: 업무 즉시 사용",
    "· 노트북 템플릿 링크",
    "· 대상노트 참고",
    "",
    "열1 · 열2",
    "a · b",
])


def _run(markdown):
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const start = src.indexOf('function buildLibraryPreviewText(');
        if (start === -1) { console.error('missing'); process.exit(1); }
        let depth = 0; let end = -1;
        for (let i = start; i < src.length; i += 1) {
          if (src[i] === '{') depth += 1;
          if (src[i] === '}') { depth -= 1; if (depth === 0) { end = i + 1; break; } }
        }
        eval(src.slice(start, end));
        const input = JSON.parse(process.argv[1]);
        console.log(JSON.stringify(buildLibraryPreviewText(input)));
        """
    )
    completed = subprocess.run(
        ["node", "-e", node_script, json.dumps(markdown, ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_preview_keeps_lines_and_strips_markdown():
    assert _run(SAMPLE) == EXPECTED


def test_preview_drops_rules_inside_quotes():
    """인용 안의 가로선(`> ---`)도 버린다 - 실데이터 1건에서 남았다."""
    assert _run("> 앞\n>\n> ---\n> 뒤") == "앞\n뒤"


def test_preview_drops_only_leading_heading():
    assert _run("본문 먼저\n## 소제목\n내용") == "본문 먼저\n소제목\n내용"


def test_preview_empty():
    assert _run("") == ""
    assert _run("# 제목만") == ""
