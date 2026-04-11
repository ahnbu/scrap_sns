---
title: Threads 스키마 drift 정비 실행 기록
created: 2026-04-11 18:43
session_id: codex:019d7bd4-e347-77c3-af09-5033cb06b679
session_path: C:/Users/ahnbu/.codex/sessions/2026/04/11/rollout-2026-04-11T18-17-22-019d7bd4-e347-77c3-af09-5033cb06b679.jsonl
plan: C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md
spec: D:/vibe-coding/scrap_sns/docs/specs/20260411_01_threads-schema-drift-정비.md
ai: codex
---

# Threads 스키마 drift 정비 실행 기록

## 발단: 사용자 요청

사용자는 `C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md` plan과 `docs/specs/20260411_01_threads-schema-drift-정비.md` spec을 근거로 Threads 스키마 drift 정비를 그대로 실행하라고 요청했다.

목표는 Threads 659건 중 583건에 남아 있던 `Unknown` 사용자명과 `href="#"` 문제를 정리하고, 같은 drift가 다시 발생하지 않도록 생성 경로와 저장 경로 모두에 재발 방지 장치를 심는 것이었다.

## 작업 상세내역

Step 0에서 사전 확인과 백업을 먼저 수행했다. `utils/threads_parser.py:extract_posts_from_node`가 실제로 `user`, `timestamp` 같은 레거시 키를 생성하고 있음을 확인했고, `web_viewer/convert_data.py`는 import 참조가 없음을 확인했다. 이어서 `archive/pre-cleanup-20260411` 브랜치를 만들고 원격까지 push했으며, `D:/vibe-coding/scrap_sns_backup_20260411` 폴더 백업도 생성했다.

구현은 TDD 순서로 진행했다. 먼저 `tests/unit/test_post_schema.py`, `tests/unit/test_threads_schema_guard.py`, `tests/unit/test_web_viewer_resolve_post_url.py`를 추가하고, RED 상태에서 `utils.post_schema` 부재와 `_assert_threads_schema` 부재를 확인한 뒤 코드를 채웠다. 이후 `utils/post_schema.py`, `utils/build_data_js.py`, `migrate_schema.py`를 추가하고, `utils/threads_parser.py`, `thread_scrap_single.py`, `thread_scrap.py`, `web_viewer/script.js`를 수정해 GREEN으로 올렸다.

실행 중 plan과 다른 보정이 1건 있었다. `migrate_schema.py --dry-run` 결과 `DTBvORnkpUy` 1건이 `full_text` 누락으로 `still_bad=1`로 남았는데, 실제 데이터를 확인해보니 레거시 손상 데이터가 아니라 정상적인 `image-only` Threads 게시물이었다. 이에 따라 `validate_post()`를 `full_text` 단독 필수에서 `full_text or media` 조건으로 수정했다. 이 변경은 기존 수집 로직과 실제 데이터 정합성에 맞춘 보정이다.

데이터 적용은 `migrate_schema.py --apply`로 `output_threads/python/threads_py_full_*.json`과 `output_total/total_full_*.json`에 수행했고, 이후 `python -m utils.build_data_js`로 `web_viewer/data.js`를 다시 생성했다. `.gitignore`는 `output_total/total_full_*.json`만 추적되도록 2단 negation으로 수정했고, `web_viewer/convert_data.py`는 `_deprecated/convert_data.py`로 이동했다.

커밋은 cp 절차에 맞춰 6개 관심사로 분리했다. `feat(schema)`, `fix(threads)`, `fix(viewer)`, `chore(gitignore)`, `chore(data)`, `chore(cleanup)` 순서로 커밋하고 모두 `main`에 push했다. 커밋 SHA는 `6edc229`, `868543a`, `885ce42`, `0ffbe96`, `1ea0599`, `b45ba48`이다.

## 의사결정 기록

- 결정: Plan v2의 순서를 유지해 `게이트 심기 → 마이그레이션 → data.js 재생성` 순서로 진행했다.
- 근거: 마이그레이션을 먼저 하면 다음 상세수집에서 레거시 레코드가 다시 유입될 수 있으므로, 생성 경로와 write 지점을 먼저 닫아야 재발 방지가 성립한다.
- 트레이드오프: 구현 복잡도는 소폭 늘었지만, parser 원인 수정 + merge normalize + write gate 3층으로 나눠서 drift 재발 시점을 즉시 드러내도록 만들 수 있었다.

- 결정: `validate_post()`는 `full_text`만이 아니라 `media`만 있는 게시물도 정상으로 인정하도록 수정했다.
- 근거: 실제 Threads 데이터에 이미지 전용 게시물이 존재했고, 기존 수집 로직도 텍스트 없이 `media`만 있으면 유효로 처리하고 있었다.
- 트레이드오프: 검증 규칙은 약간 더 관대해졌지만, 실제 데이터 모델과 수집기 동작을 반영하는 방향이라 false positive를 줄였다.

- 결정: `resolvePostUrl()`과 `post.user` fallback은 데이터 정본 교정 후에도 유지했다.
- 근거: 정상 상태에서는 no-op이고, 이후 drift가 다시 들어오면 카드 UI에서 조기 경고 역할을 한다.
- 트레이드오프: 뷰어에 fallback 분기가 남지만, 사용자 체감 장애를 줄이면서 원인 추적도 가능하게 한다.

## 검증계획과 실행결과

| 검증 항목 | 검증 방법 | 결과 | 비고 |
|-----------|-----------|------|------|
| 스키마 유틸/게이트 회귀 | `python -m pytest tests/unit/test_post_schema.py tests/unit/test_web_viewer_resolve_post_url.py tests/unit/test_threads_schema_guard.py tests/unit/test_threads_parser.py` | ✅ 통과 | 11 passed |
| 통합 데이터 스키마 | `python -c`로 `output_total/total_full_20260411.json` 975건 전체에 `validate_post` 적용 | ✅ 통과 | `PASS: all 975 posts validate_post clean` |
| data.js 파싱 검증 | `node -e`로 `web_viewer/data.js` 파싱 후 Threads username/url 누락 수 집계 | ✅ 통과 | `threads=659`, `no_username=0`, `no_url=0` |
| Threads 카드 DOM 검증 | Playwright로 `index.html` 로드 후 Threads 필터 적용, `article h3`의 `Unknown` 카운트 확인 | ✅ 통과 | `total=659`, `unknown=0` |
| 원본 링크 샘플 검증 | 같은 Playwright 세션에서 `View Original` 5건의 `href` 형식 확인 | ✅ 통과 | 5건 모두 `https://www.threads.net/@.../post/...` |
| LinkedIn/X 회귀 확인 | `git diff --stat -- linkedin_scrap.py twitter_scrap.py twitter_scrap_single.py utils/linkedin_parser.py` | ✅ 통과 | 출력 없음 |
| 백업 존재 확인 | `git branch -a`와 폴더 경로 확인 | ✅ 통과 | archive 브랜치 로컬/원격 존재, 폴더 백업 존재 |
| 신규 재수집 실전 검증 | 실제 `thread_scrap.py --mode update` 재실행 | ⚠️ 미실행 | 네트워크/인증 의존 단계라 이번 turn에서는 생략 |

## 리스크 및 미해결 이슈

- 실제 네트워크 재수집(step 9-f)은 이번 turn에서 실행하지 않았다. schema gate가 새 수집에도 그대로 동작하는지에 대한 최종 실전 검증은 별도 실행이 필요하다.
- 현재 워크트리에는 이번 doc-save-cp 작업과 직접 관련 없는 변경이 남아 있다: `implementation_plan.md` 삭제, `docs/implementation_plan.md` 생성, `.playwright-mcp/` 산출물. 이번 turn에서는 건드리지 않았다.
- 검증용으로 띄운 임시 정적 서버 `127.0.0.1:8765`는 세션 종료 시 정리되지 않을 수 있다.

## 다음 액션

- 필요 시 `python thread_scrap.py --mode update`를 1회 실행해 신규 수집 데이터가 `_assert_threads_schema`를 그대로 통과하는지 확인한다.
- `implementation_plan.md` 관련 이동/삭제가 의도된 변경인지 확인한 뒤 별도 커밋으로 분리한다.
- `.playwright-mcp/` 산출물 보존이 불필요하면 별도 판단 후 정리한다.

## 참고 자료

| 출처 | 용도 |
|------|------|
| `C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md` | 구현 순서, 게이트 전략, 검증 항목의 기준 |
| `D:/vibe-coding/scrap_sns/docs/specs/20260411_01_threads-schema-drift-정비.md` | 요구사항, 성공 기준, 허용 범위의 근거 |
| `D:/vibe-coding/scrap_sns/docs/plan-check/20260411_temporal-weaving-hartmanis_검수보고서.md` | v1 오진과 v2 교정 포인트 확인 |
| `D:/vibe-coding/scrap_sns/utils/threads_parser.py` | 레거시 키 생성 원인 확인 |
| `D:/vibe-coding/scrap_sns/thread_scrap_single.py` | merge/write 영구화 지점 확인 |

---

> Plan 원문 — 원본: C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md

# (Plan) Threads 스키마 drift 정비 + 재발방지 인프라 (v2)

**SPEC**: `D:/vibe-coding/scrap_sns/docs/specs/20260411_01_threads-schema-drift-정비.md`
**Session**: 54973faf-dfdf-4f72-9cf5-edd416fd5394
**이전 plan의 검수 결과**: `D:/vibe-coding/scrap_sns/docs/plan-check/20260411_temporal-weaving-hartmanis_검수보고서.md`
**Branch**: `archive/pre-cleanup-20260411` (백업) → `main`에서 작업

## Context

웹 뷰어에서 Threads 659건 중 583건(88%)이 "Unknown" + `href="#"` 표시. v1 plan은 원인을 `thread_scrap.py:127-135` backfill로 오진했으나 plan-check 검증 결과:

- **583건 전원 `is_merged_thread: true` + `source` 필드 누락 + `original_item_count` 필드 보유**
- **진짜 원인**: `utils/threads_parser.py:extract_posts_from_node`가 item dict를 레거시 키(`user`, `timestamp`, `code`)로 생성 → `thread_scrap_single.py:merge_thread_items:79`의 `root.copy()`가 그대로 상속 → `:135` `json.dump`로 영구화
- **`thread_scrap.py:127-135` backfill은 부차적**: source 필드 누락은 기록했을 것이나 `original_item_count` 없음으로 구분 가능. 여전히 정합성 낮아 수정 대상이지만 근본 원인 아님

v1 plan의 Codex 검수가 지적한 치명 결함 4가지 중 **"레거시 생성원 오진"이 가장 심각**했고, v2는 이를 최우선으로 수정한다. 추가로 v1의 엄격/관대 모드 혼동, 실행 불가 검증 스크립트, CLAUDE.md 규정 위반 예시도 모두 교정.

## 실행 순서의 원칙 (v1 대비 변경)

```
v1: 백업 → 유틸 신설 → 마이그레이션 → data.js → 뷰어 fallback → 게이트 → 검증
    ❌ 마이그레이션 직후 Consumer 실행 시 또 레거시 생성

v2: 백업 → 유틸 신설 → [게이트 심기: 원인층 + 중간층 + 영구화층] → 마이그레이션 → data.js → 뷰어 fallback → 검증
    ✅ 게이트가 먼저 닫혀 있으므로 마이그레이션 후 어떤 Consumer 실행도 안전
```

**핵심**: 재발 방지 게이트(Step 4 3층)가 데이터 교정(Step 5)보다 **먼저** 실행되어야 한다. 반대 순서는 마이그레이션 직후 다음 상세수집이 또 레거시 양산.
