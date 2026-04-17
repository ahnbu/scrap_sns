---
created: 2026-04-17
plan: nested-wandering-lake.md
session_id: 6f3270a3-72fe-45e0-9524-5102f0d18777
tags:
  - plan-check
  - tag
---

# 검수보고서: 태그 키 정비 (BL-0412-03 + BL-0412-04)

## Codex 검수 결과

가능성이 낮습니다. 이 plan대로면 `.com` 키는 0으로 만들 수 있어도, 동일 게시물 태그를 truly canonical URL로 통합하는 데는 실패하고 새 형태의 중복을 17건 남길 가능성이 큽니다.

**주요 결함**
- `Critical` `C:/Users/ahnbu/.claude/plans/nested-wandering-lake.md:41-62`의 핵심 아이디어가 `.com` 키를 단순히 `www.threads.net`으로 치환하는 방식인데, 이건 canonical 보장을 못 합니다. 실측으로 172건 중 155건만 현재 canonical과 정확히 일치했고, 8건은 현재 username이 바뀌어 다른 `.net` URL로 매핑되며, 9건은 현재 canonical 대신 기존 `/t/CODE` 레거시 키만 남아 있습니다. 이 방식대로면 문제를 없애는 게 아니라 namespace 중복을 17건 남깁니다. 근거: 현재 마이그레이션 로직은 `web_viewer/script.js:395-444`, 최신 canonical 소스는 `output_total/total_full_20260417.json`, 현재 태그는 `web_viewer/sns_tags.json`.
- `Critical` plan은 `:62`에서 "17건 `.com-only`는 `.net` 키로 이동"이라고 적었지만, 사실상 17건 전부가 "그냥 `.net`으로 바꾸면 끝"이 아닙니다. 8건은 code 기준 현재 canonical이 다른 username URL로 존재하고, 9건은 `/t/CODE`와 충돌합니다. 즉 분류 자체가 틀렸습니다.
- `Major` `:7`, `:17-35`는 `resolvePostUrl()` 정규화를 "근본 원인"처럼 쓰고 있지만, 현재 크롤러와 최신 산출물은 이미 `.net`만 생성합니다. `thread_scrap.py:457,562`도 `.net`을 만들고, `output_threads/python/threads_py_full_20260417.json` 등 최신 파일도 `.com URL`이 0건이었습니다. Step 1은 재발 방지용 hardening이지, 현재 172건의 직접 원인 진단으로는 과장입니다.
- `Major` 테스트 계획이 부족합니다. `:68-84`의 2개 테스트로는 Step 1이 바꾸는 `resolvePostUrl(post.url)` 분기를 직접 검증하지 못합니다. 현재 테스트 `tests/unit/test_web_viewer_auto_tagging.py`는 3개가 모두 통과하지만, `.com url` 입력, username 변경 canonical, `/t/CODE` fallback 케이스를 막지 못합니다.
- `Major` 검증 기준이 너무 약합니다. `:98-111`의 "`threads.com` 0건"은 통과해도, 같은 code가 두 키로 남는 상태를 놓칩니다. 실제로 단순 치환을 시뮬레이션하면 `.com`은 0이 되지만 code 기준 중복 namespace가 17건 남습니다.

**트레이드오프**
- 앱 로드 시 자동 마이그레이션은 별도 스크립트가 없어 운영이 단순합니다. 대신 현재 로드된 게시물 집합에 canonical 판단을 의존하므로, username 변경이나 오래된 post처럼 데이터셋 밖의 항목에서 오판 가능성이 큽니다.
- `canonByComDomain` 같은 새 맵 추가는 얻는 것보다 잃는 게 큽니다. 문제의 본질은 "도메인 치환 속도"가 아니라 "code 기준 canonical 선택"인데, plan은 여기서 빗나가 있어 과최적화 성향이 보입니다.

**권장 수정**
- `.com` 처리도 문자열 치환이 아니라 code 중심으로 잡아야 합니다. 우선순위는 `canonByCode.get(code)` → 기존 `/t/CODE` 키 → 마지막 fallback으로 domain swap이 맞습니다.
- 테스트는 최소 4개가 필요합니다. `.com url` 정규화, `.com + exact canonical`, `.com + username-changed canonical`, `.com + /t/CODE only`.

**검증 결과**
- 현재 코드에서 `.com` 문제는 실제 존재합니다. 최신 데이터로 `migrateLegacyTagKeys()`를 돌려도 `.com` 172건은 0건도 줄지 않았습니다. 근거: `web_viewer/script.js:418-419`.
- 현재 단위 테스트 3개는 `pytest tests/unit/test_web_viewer_auto_tagging.py -q`로 통과했습니다.
- 브라우저에서 실제 콘솔 메시지와 `syncTagsToServer()` roundtrip은 이번 세션에서 실행하지 않았으므로 검증 불가입니다. 코드 경로는 `web_viewer/script.js:437-440`, `1216-1232`에 존재합니다.

---

## Claude 코드베이스 검증

### Critical 1: 단순 도메인 치환으로 canonical 보장 불가 → 확증

실측 결과:
```
총 .com 키: 172건
both(exact match): 155건  — 단순 치환으로 해결
username mismatch: 7건    — code는 같지만 username이 바뀜
com-only: 9건             — .net 키 없음, /t/CODE 키와 매칭
  truly orphan: 0건
```

username 변경 사례 (`sns_tags.json` 실측):
- `@seulgi.kaang` → `@marketer.ai.seulki` (4건)
- `@gimminseog67` → `@miniminim71` (2건)
- `@__watermelonlover` → `@mega_fluke` (1건)

이 7건은 `.com` → `.net` 단순 치환 시 존재하지 않는 `.net` URL이 생성되어 새로운 고아 키가 됨. 기존 `canonByCode` 맵(`script.js:406`)이 code 기반으로 canonical을 이미 알고 있으므로, `.com` URL에서 code를 추출 → `canonByCode.get(code)`로 target을 찾는 것이 올바른 접근.

### Critical 2: 17건 분류 오류 → 확증 (실측은 16건)

Codex는 8건+9건=17건이라 했으나, 실측은 7건(username 변경)+9건(/t/CODE)=16건. 어느 쪽이든 "단순 치환으로 해결 불가"라는 결론은 동일.

9건의 `/t/CODE` 키는 기존 `canonByTSlash` 맵(`script.js:407`)이 처리 가능하므로, `.com` 키를 먼저 code 추출 → `canonByCode`로 해결하면 자연스럽게 canonical에 병합됨.

### Major: resolvePostUrl 정규화가 "근본 원인"은 과장 → 확증

`thread_scrap.py`를 확인하지 않아도, 현재 `.com` 키가 새로 생성되지 않는다면 `resolvePostUrl` 정규화는 방어적 hardening일 뿐. 다만 넣어서 손해는 없으므로 유지 권장.

### Major: 테스트 부족 → 확증

현재 plan의 2개 테스트에 추가로 필요한 시나리오:
1. `resolvePostUrl`에 `.com` URL 입력 → `.net` 반환 확인
2. `.com` 키 + username 변경된 canonical → code 기반 병합 확인
