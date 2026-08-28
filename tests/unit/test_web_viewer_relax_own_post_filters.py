"""MY 를 켤 때의 조건 단계 완화 절차(relaxOwnPostFilters) 검증.

계획: _docs/20260828_01_뷰어-MY필터-조건별-단계완화-계획.md (3.1, 4.2 N5)

이 절차의 핵심은 「플랫폼에도 태그에도 내 글이 있는데 둘을 겹치면 0건」인 교집합
함정을 넘기지 않는 것이다. 그런데 그 조합은 현재 수집 데이터에 0개다 - 내 글 68건 중
교차 게시가 23쌍이라 태그 16개가 전부 두 플랫폼에 걸쳐 있기 때문이다.

실데이터에 없는 조합이므로 E2E 로는 재현할 수 없다. 그래서 완화 절차를 DOM·전역에
의존하지 않는 순수 함수로 분리했고, 여기서 세는 함수를 직접 넣어 함정을 만든다.
"""

import json
import subprocess
import textwrap


def _run_relax(state, counts):
    """relaxOwnPostFilters 를 script.js 에서 추출해 실행한다.

    counts 는 {"platform|tag|author": 내_글_건수} 형태다. 키에 없으면 0으로 본다.
    """
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');

        function extractFunction(name) {
          const start = src.indexOf(`function ${name}(`);
          if (start === -1) {
            console.error(`${name} missing`);
            process.exit(1);
          }
          let depth = 0;
          let end = -1;
          for (let i = start; i < src.length; i += 1) {
            const ch = src[i];
            if (ch === '{') depth += 1;
            if (ch === '}') {
              depth -= 1;
              if (depth === 0) {
                end = i + 1;
                break;
              }
            }
          }
          if (end === -1) {
            console.error(`${name} parse failure`);
            process.exit(1);
          }
          return src.slice(start, end);
        }

        eval(extractFunction('relaxOwnPostFilters'));

        const state = %STATE%;
        const counts = %COUNTS%;
        const seen = [];
        const countOwnPosts = (s) => {
          const key = `${s.platform}|${s.tag ?? ''}|${s.author ?? ''}`;
          seen.push(key);
          return counts[key] ?? 0;
        };

        const result = relaxOwnPostFilters(state, countOwnPosts);
        console.log(JSON.stringify({ result, seen }));
        """
    )
    node_script = node_script.replace("%STATE%", json.dumps(state))
    node_script = node_script.replace("%COUNTS%", json.dumps(counts))

    completed = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=".",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_keeps_everything_when_own_posts_already_visible():
    """첫 조합부터 내 글이 있으면 아무것도 풀지 않는다."""
    out = _run_relax(
        {"platform": "linkedin", "tag": "코덱스", "author": None},
        {"linkedin|코덱스|": 6},
    )
    assert out["result"] == {"platform": "linkedin", "tag": "코덱스", "author": None}
    assert len(out["seen"]) == 1, "불필요하게 여러 번 셌습니다."


def test_releases_platform_when_it_has_no_own_posts():
    """YouTube 처럼 내 글이 0건인 플랫폼은 All 로 풀린다. 사용자 보고 건."""
    out = _run_relax(
        {"platform": "youtube", "tag": None, "author": None},
        {"all||": 68},
    )
    assert out["result"]["platform"] == "all"


def test_releases_tag_when_it_has_no_own_posts():
    """내 글이 0건인 태그는 풀리고, 플랫폼은 건드리지 않는다."""
    out = _run_relax(
        {"platform": "all", "tag": "하네스", "author": None},
        {"all||": 68},
    )
    assert out["result"] == {"platform": "all", "tag": None, "author": None}


def test_releases_author_first():
    """남의 작성자는 내 글과의 교집합이 구조적으로 항상 0이라 가장 먼저 풀린다."""
    out = _run_relax(
        {"platform": "linkedin", "tag": None, "author": "someone-else"},
        {"linkedin||": 36},
    )
    assert out["result"] == {"platform": "linkedin", "tag": None, "author": None}
    assert out["seen"][0] == "linkedin||someone-else"


def test_empty_intersection_releases_tag_but_keeps_platform():
    """교집합 함정 - 이 테스트가 이 파일의 존재 이유다.

    Threads 에 내 글 32건이 있고 태그 「신규주제」에도 내 글이 있지만,
    그 태그가 LinkedIn 글에만 붙어 있어 겹치면 0건인 상황.

    조건을 따로따로 검사하는 방식은 둘 다 통과시켜 빈 화면을 낸다.
    매 단계 실제로 세는 방식은 태그만 풀고 Threads 32건을 지켜낸다.
    """
    out = _run_relax(
        {"platform": "threads", "tag": "신규주제", "author": None},
        {
            # threads + 신규주제 = 0 (키 없음)
            "threads||": 32,
            "all||": 68,
        },
    )
    assert out["result"] == {"platform": "threads", "tag": None, "author": None}, (
        "태그만 풀고 플랫폼은 지켜야 합니다. 플랫폼까지 풀렸다면 지킬 수 있었던 조건을 버린 것입니다."
    )


def test_releases_everything_when_nothing_helps():
    """전부 풀어도 0건이면(남은 원인은 검색어뿐) 더 이상 손대지 않고 끝낸다."""
    out = _run_relax(
        {"platform": "linkedin", "tag": "하네스", "author": "someone-else"},
        {},
    )
    assert out["result"] == {"platform": "all", "tag": None, "author": None}


def test_does_not_mutate_input_state():
    """호출자의 상태를 직접 바꾸지 않는다. 화면 반영은 호출자가 결정한다."""
    node_script = textwrap.dedent(
        """
        const fs = require('fs');
        const src = fs.readFileSync('web_viewer/script.js', 'utf8');
        const start = src.indexOf('function relaxOwnPostFilters(');
        let depth = 0, end = -1;
        for (let i = start; i < src.length; i += 1) {
          if (src[i] === '{') depth += 1;
          if (src[i] === '}') { depth -= 1; if (depth === 0) { end = i + 1; break; } }
        }
        eval(src.slice(start, end));

        const original = { platform: 'youtube', tag: '하네스', author: 'x' };
        relaxOwnPostFilters(original, () => 0);
        console.log(JSON.stringify(original));
        """
    )
    completed = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=".",
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {
        "platform": "youtube",
        "tag": "하네스",
        "author": "x",
    }
