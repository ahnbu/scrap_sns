# declarative-waddling-flask 계획 검수보고서

- 검수 대상: `C:\Users\ahnbu\.claude\plans\declarative-waddling-flask.md`
- 검수 일시: `2026-04-18` KST
- 결론: 승인 보류

## 요약

이 계획은 `twitter_scrap_single.py`를 `twitter-cli` 기반으로 전환하려는 방향 자체는 타당하다. 다만 현재 문서는 코드 교체만 다루고 있고, 실제 저장 데이터 정합성 복구, 테스트/문서 영향, 인증 운영 경로, CLI 응답 해석 규칙이 결정 완료 상태가 아니다.

특히 이 저장소는 X 상세 수집 결과가 `output_twitter/python/twitter_py_full_YYYYMMDD.json`, `scrap_failures_twitter.json`, `output_total/total_full_YYYYMMDD.json`, `web_viewer/data.js`로 이어지므로, 파싱/정규화 로직 변경 계획이라면 마이그레이션과 재검증 절차가 반드시 들어가야 한다.

## 주요 결함

### 1. 데이터 마이그레이션과 정합성 복구 계획이 누락됨

계획은 변경 범위를 사실상 `twitter_scrap_single.py` 1개와 선택적 `utils/twitter_parser.py` 삭제로 한정한다 ([plan:14-25](C:/Users/ahnbu/.claude/plans/declarative-waddling-flask.md:14)). 하지만 프로젝트 문서는 X 관련 영구화 surface를 `twitter_py_simple_*`, `twitter_py_full_*`, `scrap_failures_twitter.json`, `output_total/total_full_*`, `web_viewer/data.js`까지 명시한다 ([development.md](/D:/vibe-coding/scrap_sns/docs/development.md:27)).

실측에서도 기존 저장 데이터와 현재 `twitter-cli` 응답이 이미 어긋난 사례가 확인됐다. 예를 들어 `platform_id=2033919415771713715`는 현재 full 데이터의 `username=kana_option`, `full_text=한국어 본문`인데, 동일 ID에 대한 `twitter tweet --json -n 5` 첫 응답은 `author.screenName=itsolelehmann`, `text=https://t.co/kgo8wNoiDv`였다. 이런 상태라면 계획에는 최소한 다음 4가지가 포함돼야 한다.

- 영향받는 영구화 surface 목록
- 기존 데이터 재수집 또는 마이그레이션 필요 여부
- 실행 명령 또는 스크립트 경로
- 결과 검증 명령과 기대 출력

### 2. `utils/twitter_parser.py` 삭제 제안의 근거가 부족함

계획은 `utils/twitter_parser.py`를 “사용처 없음” 전제로 삭제 후보로 둔다 ([plan:19-21](C:/Users/ahnbu/.claude/plans/declarative-waddling-flask.md:19), [plan:139-142](C:/Users/ahnbu/.claude/plans/declarative-waddling-flask.md:139)). 그러나 현재 코드베이스에서 이 모듈은 상세 수집기 본체가 직접 import하고 있으며 ([twitter_scrap_single.py](/D:/vibe-coding/scrap_sns/twitter_scrap_single.py:10)), 단위/통합 테스트도 직접 의존한다 ([test_twitter_parser.py](/D:/vibe-coding/scrap_sns/tests/unit/test_twitter_parser.py:3), [test_parser_integration.py](/D:/vibe-coding/scrap_sns/tests/integration/test_parser_integration.py:13)).

문서도 아직 X 상세 HTML 파서를 `utils/twitter_parser.py`로 설명하고 있다 ([development.md](/D:/vibe-coding/scrap_sns/docs/development.md:116), [crawling_logic.md](/D:/vibe-coding/scrap_sns/docs/crawling_logic.md:54)). 따라서 삭제를 계획에 넣으려면, 단순 grep이 아니라 다음까지 같이 결정돼야 한다.

- 대체 테스트 자산
- 관련 문서 갱신 범위
- 레거시 fixture 유지 여부

### 3. 검증 시나리오가 실제 변경 경로를 보장하지 못함

계획의 핵심 검증은 `python twitter_scrap_single.py --limit 3`와 `python total_scrap.py --mode update`다 ([plan:153-164](C:/Users/ahnbu/.claude/plans/declarative-waddling-flask.md:153)). 하지만 현재 latest simple 파일 기준 미수집 항목 수는 `0`개였고, 상세 수집기 코드는 타깃이 없으면 수집 없이 종료한다 ([twitter_scrap_single.py](/D:/vibe-coding/scrap_sns/twitter_scrap_single.py:101)).

오케스트레이터도 동일 조건에서 X consumer를 건너뛴다 ([total_scrap.py](/D:/vibe-coding/scrap_sns/total_scrap.py:82), [total_scrap.py](/D:/vibe-coding/scrap_sns/total_scrap.py:107)). 즉 지금 계획의 검증은 “변경 코드가 실제로 실행되었다”는 증거가 되지 못한다.

### 4. `twitter-cli` 응답 해석 규칙이 결정 완료가 아님

계획은 `data[0]`을 메인 트윗으로 보고, 같은 작성자 트윗만 모아 스레드 체인으로 합친다 ([plan:72-81](C:/Users/ahnbu/.claude/plans/declarative-waddling-flask.md:72)). 실제 `twitter-cli` 구현은 `tweet` 명령이 `fetch_tweet_detail()` 결과 전체를 structured output으로 그대로 내보내고 ([twitter_cli/cli.py](/C:/Users/ahnbu/pipx/venvs/twitter-cli/Lib/site-packages/twitter_cli/cli.py:830), [twitter_cli/output.py](/C:/Users/ahnbu/pipx/venvs/twitter-cli/Lib/site-packages/twitter_cli/output.py:94)), 내부적으로는 conversation thread와 replies를 함께 반환한다 ([twitter_cli/client.py](/C:/Users/ahnbu/pipx/venvs/twitter-cli/Lib/site-packages/twitter_cli/client.py:358)).

실측에서도 같은 작성자와 타 작성자 reply가 섞여 나왔다. 이때 “same author”만으로는 실제 self-thread, 일반 대화 reply, quoted tweet 주변 문맥을 구분하지 못한다. 따라서 계획에는 적어도 아래가 들어가야 한다.

- 메인 트윗 식별 규칙
- 같은 작성자 reply를 포함할지 말지의 기준
- quoted tweet / retweet / reply chain 제외 규칙
- `--max` 값과 수집 범위 기준

### 5. 인증 운영 경로와 정본이 불명확함

계획은 `auth/x_cookies_*.json`에서 `auth_token`, `ct0`를 읽어 환경변수로 주입하는 방식을 새 기본으로 둔다 ([plan:29-49](C:/Users/ahnbu/.claude/plans/declarative-waddling-flask.md:29)). `twitter-cli`가 실제로 `TWITTER_AUTH_TOKEN`, `TWITTER_CT0`를 읽는 것은 코드로 확인됐다 ([twitter_cli/auth.py](/C:/Users/ahnbu/pipx/venvs/twitter-cli/Lib/site-packages/twitter_cli/auth.py:85)).

다만 레포에는 이미 persistent Chrome profile 기반 인증 갱신 흐름이 있고 ([renew_twitter_auth.py](/D:/vibe-coding/scrap_sns/renew_twitter_auth.py:5)), 쿠키를 Playwright persistent context에 주입하는 별도 스크립트도 있다 ([inject_x_cookies.py](/D:/vibe-coding/scrap_sns/inject_x_cookies.py:1)). 따라서 어떤 파일이 인증 정본인지, 쿠키 파일 갱신 주체가 무엇인지, consumer 전환 후 `renew_twitter_auth.py`와 `inject_x_cookies.py`를 어떻게 유지할지가 계획에 없다.

## 코드베이스 검증 결과

### 확증된 항목

- 현재 X 상세 수집기는 Playwright persistent context를 사용한다. `sync_playwright` import와 `launch_persistent_context(... headless=False, channel="chrome")`가 존재한다 ([twitter_scrap_single.py](/D:/vibe-coding/scrap_sns/twitter_scrap_single.py:8), [twitter_scrap_single.py](/D:/vibe-coding/scrap_sns/twitter_scrap_single.py:114)).
- `twitter-cli`는 Windows 환경에서 설치되어 있고 `tweet` 서브커맨드를 제공한다. 또한 환경변수 `TWITTER_AUTH_TOKEN`, `TWITTER_CT0`를 인증 소스로 지원한다 ([twitter_cli/auth.py](/C:/Users/ahnbu/pipx/venvs/twitter-cli/Lib/site-packages/twitter_cli/auth.py:4), [twitter_cli/auth.py](/C:/Users/ahnbu/pipx/venvs/twitter-cli/Lib/site-packages/twitter_cli/auth.py:87)).
- `utils/twitter_parser.py`는 아직 현행 테스트 자산이다. `pytest tests/unit/test_twitter_parser.py -q`, `pytest tests/integration/test_parser_integration.py -q -k twitter` 모두 통과했다. 해당 테스트는 각각 [test_twitter_parser.py](/D:/vibe-coding/scrap_sns/tests/unit/test_twitter_parser.py:11), [test_parser_integration.py](/D:/vibe-coding/scrap_sns/tests/integration/test_parser_integration.py:84)에 연결된다.
- 현재 X viewer는 `post.media[0]`가 `.mp4`를 포함하면 video placeholder로 처리하고, 그 외는 `wsrv.nl` 프록시를 사용한다 ([web_viewer/script.js](/D:/vibe-coding/scrap_sns/web_viewer/script.js:1048)). 따라서 CLI 전환 시 media URL shape 변화는 viewer 영향으로 이어질 수 있다.

### 반박 또는 계획과 다른 점

- “`utils/twitter_parser.py` 사용처 없음”은 현재 코드 기준으로 반박된다. 본체와 테스트가 사용 중이다 ([twitter_scrap_single.py](/D:/vibe-coding/scrap_sns/twitter_scrap_single.py:10), [test_twitter_parser.py](/D:/vibe-coding/scrap_sns/tests/unit/test_twitter_parser.py:3), [test_parser_integration.py](/D:/vibe-coding/scrap_sns/tests/integration/test_parser_integration.py:13)).
- “검증은 `--limit 3`로 충분”은 현재 데이터 상태에서는 반박된다. 미수집 항목이 `0`개이므로 실제 수집 경로를 보장하지 못한다 ([twitter_scrap_single.py](/D:/vibe-coding/scrap_sns/twitter_scrap_single.py:101), [total_scrap.py](/D:/vibe-coding/scrap_sns/total_scrap.py:83)).

### 검증 불가

- 계획 본문에 적힌 “3건 비교 검증 완료: 본문 100%, 미디어 100%, 작성자 100% 일치”는 현재 저장소 내 문서나 고정 fixture로 재현 근거를 찾지 못했다. 현 시점 기준으로는 “검증 불가”다.

## 권장 수정

1. 계획에 `마이그레이션/재수집` 섹션을 추가하라.
2. `utils/twitter_parser.py` 삭제는 제외하거나, 대체 테스트와 문서 갱신을 포함한 별도 작업으로 분리하라.
3. 검증은 `--limit` 실행이 아니라 `고정 tweet ID + 기대 author/text/media 스냅샷` 비교로 바꿔라.
4. `twitter-cli` 응답에서 무엇을 self-thread로 간주할지 규칙을 먼저 결정하라.
5. 인증 정본을 `x_user_data`로 유지할지 `x_cookies_*.json`로 전환할지 운영 기준을 문서화하라.
