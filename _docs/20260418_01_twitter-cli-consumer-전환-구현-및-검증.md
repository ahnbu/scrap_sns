---
title: twitter-cli consumer 전환 구현 및 검증 기록
created: 2026-04-18 15:40
tags:
  - record
  - twitter-cli
  - x
session_id: codex:019d9efb-e85f-7b82-bb66-7ae7de823056
session_path: C:/Users/ahnbu/.codex/sessions/2026/04/18/rollout-2026-04-18T14-06-42-019d9efb-e85f-7b82-bb66-7ae7de823056.jsonl


ai: codex
---

# twitter-cli consumer 전환 구현 및 검증 기록

## 발단: 사용자 요청

사용자는 X detail consumer를 Playwright 기반 browser flow에서 `twitter-cli` 기반 browserless flow로 전환하는 plan을 저장한 뒤, 그 plan을 `Subagent-Driven` 방식으로 실행하라고 요청했다.

작업 목표는 `twitter_scrap_single.py`를 focal tweet only 규칙으로 전환하면서 기존 persistence 파일 구조와 실패 관리 흐름은 유지하는 것이었다. 문서화는 [[superpowers/plans/20260418_01_twitter-cli-consumer-전환계획]]을 기준으로 하고, 구현 후 실제 검증 결과를 남기는 방식으로 정리했다.

## 작업 상세내역

1. `utils/twitter_cli_adapter.py`를 추가해 `auth/x_cookies_*.json`에서 토큰을 읽고 `twitter tweet <url> --json` 실행 결과를 focal tweet 기준으로 정규화하도록 분리했다. 이 단계에서 `data[0]`만 저장하고 self-thread 병합은 의도적으로 제외했다.

2. `twitter_scrap_single.py`에서 Playwright runtime 의존을 제거하고 adapter를 주입했다. 토큰 누락 시에는 상세 수집만 건너뛰고 full/simple 동기화는 계속되게 했고, fetch 예외 시에는 실패 카운트를 유지하도록 정리했다.

3. fixture와 테스트를 새 흐름에 맞춰 추가했다. `tests/fixtures/twitter_cli/*.json`, `tests/unit/test_twitter_cli_adapter.py`, `tests/integration/test_twitter_scrap_single_cli.py`를 추가해 token loading, URL normalization, failure persistence, token-missing skip, full merge 경로를 검증했다.

4. 운영 문서를 현재 구현 기준으로 현행화했다. `README.md`, [[development]], [[crawling_logic]]에 `twitter-cli` 설치 확인, producer/consumer auth 분리, focal tweet only 규칙, `created_at` fallback, consumer token missing 시 skip 동작을 반영했다.

5. 문서/검증 단계에서 `docs/` 하위에 사용자 소유 수정이 다수 존재함을 확인했다. 따라서 이번 구현 커밋은 기능 코드와 관련 문서 커밋 3개만 만들고, 사용자 소유 `docs/` 작업트리 변경은 범위에서 제외했다.

## 의사결정 기록

| 항목 | 검토안 | 채택안 | 근거 | 트레이드오프 |
|------|--------|--------|------|--------------|
| 상세 수집 방식 | Playwright 상세 페이지 파싱 유지, `twitter-cli` 전환 | `twitter-cli` 전환 | 브라우저 의존을 줄이고 focal tweet 데이터만 안정적으로 수집할 수 있다 | thread 병합 정보는 얻지 못한다 |
| thread 처리 범위 | same-author reply chain 복원, focal tweet only | focal tweet only | `twitter-cli` structured output에는 parent-reply 메타데이터가 부족하다 | 기존 merged-thread 행동과 완전 동일하지 않다 |
| media 저장 규칙 | 전부 이미지 썸네일 유지, media type별 분기 | `photo -> wsrv`, `video/animated_gif -> raw URL` | 현재 viewer가 `.mp4`를 이미 처리한다 | 새 video row는 과거 thumbnail row와 표현이 달라질 수 있다 |
| 토큰 누락 시 동작 | 즉시 종료, 상세 수집만 skip 후 동기화 지속 | 상세 수집만 skip 후 동기화 지속 | metadata/full sync를 막지 않는 편이 운영상 안전하다 | 상세 보강 누락 상태가 남을 수 있다 |
| 커밋 범위 | 현재 `docs/` 변경 전체 포함, 새 문서/필수 변경만 포함 | 새 문서와 구현 범위만 포함 | 사용자 소유 `docs/` 변경을 섞으면 안 된다 | 문서 저장 후 커밋 대상을 명시적으로 좁혀야 한다 |

- 결정: focal tweet only `twitter-cli` consumer로 전환하고, 코드/검증/운영 문서를 한 묶음으로 정리했다.
- 근거: [[superpowers/plans/20260418_01_twitter-cli-consumer-전환계획]]의 scope lock과 실제 fixture 검증 결과가 같은 방향을 지지했다.
- 트레이드오프: 브라우저 의존은 줄었지만, `twitter-cli` upstream structured output 계약에 일부 의존하게 됐다.

## 검증계획과 실행결과

> compare-table 스킬 이모지 포맷 적용 (✅❌⚠️⏳)

| 검증 항목 | 검증 방법 | 결과 | 비고 |
|-----------|-----------|------|------|
| Adapter 단위 검증 | `pytest tests/unit/test_twitter_cli_adapter.py -q` | ✅ 통과 | `11 passed` |
| Consumer 통합 검증 | `pytest tests/integration/test_twitter_scrap_single_cli.py tests/unit/test_twitter_parser.py tests/integration/test_parser_integration.py -q` | ✅ 통과 | `12 passed` |
| 최종 회귀 묶음 | `pytest tests/unit/test_twitter_cli_adapter.py tests/integration/test_twitter_scrap_single_cli.py tests/unit/test_twitter_parser.py tests/integration/test_parser_integration.py tests/contract/test_schemas.py -q` | ✅ 통과 | `24 passed` |
| 전체 수집 업데이트 | `python total_scrap.py --mode update` | ✅ 완료 | X 상세 대상 0건이면 producer만 실행, 전체 병합 종료 |
| Viewer cache 재생성 | `python -m utils.build_data_js` | ✅ 통과 | `OK: 1078 posts` |
| 최종 코드 리뷰 | commit range `ab9b3eb..a84c76f` 리뷰 | ✅ findings 없음 | `Ready to merge: yes` |
| JSON2MD 경고 확인 | `python total_scrap.py --mode update` 로그 확인 | ⚠️ 경고 | `output_total/total_full_20260418.json` BOM 경고가 남음 |

## 최종 검수 보고서

검수 시점 메모: 아래 내용은 사용자 제공 최종 검수 보고서 기준을 보존한 것이다. 보고서의 커밋 수와 참고사항은 `a84c76f` 시점 기준이며, 이후 문서 저장/정리 커밋은 별도다.

### 테스트 결과

| 테스트 | 결과 |
|------|------|
| `tests/unit/test_twitter_cli_adapter.py` (11건) | ✅ passed |
| `tests/integration/test_twitter_scrap_single_cli.py` (6건) | ✅ passed |
| `tests/unit/test_twitter_parser.py` (2건, 레거시) | ✅ passed |
| `tests/integration/test_parser_integration.py` (4건, 레거시) | ✅ passed |
| `tests/contract/test_schemas.py` (1건) | ✅ passed |
| 총 24건 | ✅ `0.4초` |

### Plan 체크리스트 대조

| Exit Criteria | 충족 |
|------|------|
| `twitter_scrap_single.py`가 Playwright 없이 실행 | ✅ Playwright import 완전 제거 확인 |
| `utils/twitter_cli_adapter.py` 생성 | ✅ 102줄, DI 패턴 |
| Fixture 3건 승격 | ✅ `tests/fixtures/twitter_cli/` 확인 |
| `utils/twitter_parser.py` + 테스트 유지 | ✅ 파일 3개 모두 존재 |
| README 인증 분리 문서화 | ✅ producer/consumer 역할 명시 |
| `docs/development.md` 현행화 | ✅ `twitter-cli`, focal tweet 반영 |
| `docs/crawling_logic.md` 현행화 | ✅ `twitter-cli` 기반 flow 반영 |
| CHANGELOG 업데이트 | ✅ 2개 커밋 |
| self-thread parity 미주장 | ✅ focal tweet만 |

### 크리티컬 이슈

- 없음

### 비크리티컬 참고사항

| 항목 | 설명 | 영향 |
|------|------|------|
| Task 3 docs 커밋 누락 | plan에는 3개 커밋(adapter/consumer/docs)이지만 실제는 2개(feat, fix)였고, docs 변경이 fix 커밋에 포함된 것으로 보인다는 지적 | 없음 — 코드 정합성 영향 없음 |
| uncommitted plan 파일 변경 | `docs/01-plan/` 하위 `.plan.md` 파일들이 modified 상태라는 지적 | 없음 — 이번 작업과 무관한 기존 파일 |

### 결론

- 구현 완료
- 크리티컬 이슈 없음
- 운영 투입 가능

## 커밋 기록

- `108726c` `feat(twitter-cli): X consumer CLI adapter 추가`
- `ee9fb37` `fix(twitter-single): browserless detail collection으로 전환`
- `a84c76f` `docs(twitter-cli): consumer auth와 persistence 규칙 문서화`

## 리스크 및 미해결 이슈

- `twitter-cli` structured output에서 focal tweet이 항상 `data[0]`이라는 외부 계약에 의존한다. 현재 로컬 설치본 `0.8.5`와 fixture 기준으로는 맞지만 upstream 변경 시 회귀 가능성이 있다.
- `python total_scrap.py --mode update` 실행 시 JSON2MD가 BOM 경고를 낸다. data 병합과 `web_viewer/data.js` 재생성은 성공했지만, 후속 정리가 필요하다.
- `inject_x_cookies.py`는 여전히 고정 파일을 바라보므로 문서와 구현은 일치하지만 운영 유연성은 낮다.

## 다음 액션

- JSON2MD BOM 경고 원인을 따로 분리해 재현하고 수정 여부를 판단한다.
- `twitter-cli` upstream schema/order 변경 여부를 주기적으로 확인하고, 필요하면 fixture를 갱신한다.
- X consumer auth 운영을 더 유연하게 만들 필요가 생기면 `inject_x_cookies.py`의 고정 파일 의존을 별도 작업으로 분리한다.

## 참고 자료

| 출처 | 용도 |
|------|------|
| [[superpowers/plans/20260418_01_twitter-cli-consumer-전환계획]] | 구현 목표, scope lock, 검증 명령의 기준 |
| [[plan-check/20260418_declarative-waddling-flask_검수보고서]] | 초기 plan 검수 지적과 수정 포인트 추적 |
| [[development]] | X consumer source, media rule, `created_at` fallback 확인 |
| [[crawling_logic]] | X producer/consumer 단계와 focal tweet only 규칙 확인 |
| [[20260417_06_범위외-회귀-9건-구현-및-검증]] | 기존 작업기록 문서 구조와 기록 스타일 참조 |
