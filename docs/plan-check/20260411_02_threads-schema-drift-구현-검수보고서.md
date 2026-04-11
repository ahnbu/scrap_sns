---
title: Threads 스키마 drift 정비 구현 검수보고서
created: 2026-04-11
session_id: 54973faf-dfdf-4f72-9cf5-edd416fd5394
plan: C:/Users/ahnbu/.claude/plans/temporal-weaving-hartmanis.md
spec: D:/vibe-coding/scrap_sns/docs/specs/20260411_01_threads-schema-drift-정비.md
prev_review: D:/vibe-coding/scrap_sns/docs/plan-check/20260411_temporal-weaving-hartmanis_검수보고서.md
reviewer: Claude (Sonnet 4.6) 실코드·실데이터 검증
---

# Threads 스키마 drift 정비 구현 검수보고서

## 종합 판정

**대체로 성공 + 1개 기능 파손 (수정 완료) + 3개 품질·노이즈 이슈**

Plan v2의 7개 성공 기준 중 5개를 실증 통과, 2개(5·7)는 코드/데이터 정적 분석으로 확증. 검수 중 발견한 Issue 1(기능 파손)은 본 세션에서 1줄 수정으로 해결 완료.

## 구현 완료 사항 (커밋 6개 순차)

| # | Commit | 내용 |
|---|---|---|
| 1 | `6edc229 feat(schema)` | `utils/post_schema.py` + `utils/build_data_js.py` + `migrate_schema.py` 신설 |
| 2 | `868543a fix(threads)` | 3층 게이트 (`threads_parser.py`, `merge_thread_items`, `_assert_threads_schema`) + `thread_scrap.py` backfill |
| 3 | `885ce42 fix(viewer)` | `script.js` 4지점 fallback + `resolvePostUrl` 헬퍼 + 단위 테스트 |
| 4 | `0ffbe96 chore(gitignore)` | 2단 negation 예외 추가 |
| 5 | `1ea0599 chore(data)` | Threads 583건 마이그레이션 결과 + data.js 재생성 |
| 6 | `b45ba48 chore(cleanup)` | `web_viewer/convert_data.py` → `_deprecated/` 이동 |

추가로 `archive/pre-cleanup-20260411` 브랜치 + `D:/vibe-coding/scrap_sns_backup_20260411/` 폴더 백업 확인.

## 성공 사항 (실증)

### 구조 검증
- **브랜치 백업**: `archive/pre-cleanup-20260411` 로컬+원격, top commit `39366a7` (작업 직전 main)
- **폴더 백업**: `D:/vibe-coding/scrap_sns_backup_20260411` + `auth/` 포함
- **CHANGELOG**: 6행 최상단 추가, 표 형식, CLAUDE.md 양식 준수
- **커밋 분리**: 6개 각 한 관심사, Co-Authored-By Codex 포함

### 파일 변경 검증
- `utils/post_schema.py` 신설, plan과 거의 동일. `REQUIRED_FIELDS`에 `full_text` 미포함, 대신 `full_text` or `media` 중 하나 필수 로직 — **plan 대비 개선** (이미지 전용 게시물 허용)
- `utils/build_data_js.py` 신설, 전수 validate 후 write
- `migrate_schema.py` 복구, `--dry-run`/`--apply`, `still_bad_samples` 출력
- `utils/threads_parser.py:97-112` 층 1 완벽 (표준 키 직접 작성, `source: "consumer_detail"`)
- `thread_scrap_single.py:104` 층 2 (`normalize_post`)
- `thread_scrap_single.py:67, :155, :215, :259, :267, :393` 층 3 `_assert_threads_schema` 5곳 설치
- `web_viewer/script.js` 4지점 (`:498, :590, :637, :1314`) fallback + `resolvePostUrl:514-523`
- `.gitignore:54-57` 2단 negation 정확
- `_deprecated/convert_data.py` `git mv` 이력 보존

### 실행 검증
| 검증 | 결과 |
|---|---|
| `total_full_20260411.json` 전수 `validate_post` | ✅ invalid 0/975 |
| 레거시 키(`user`/`timestamp`/`post_url`) 잔존 | ✅ 0건 |
| `legacy_migration` 마커 | ✅ 583건 |
| 샘플: `winter_kyul` + 합성 URL | ✅ 정확 |
| `python -m utils.build_data_js` | ✅ `OK: 975 posts → web_viewer/data.js` |
| `python migrate_schema.py --target ... (dry-run)` | ✅ `changed=0/659 still_bad=0` (이미 완료) |
| `_assert_threads_schema` 3케이스(valid/invalid-raise/linkedin-skip) | ✅ 전부 기대대로 |
| `web_viewer/data.js` Node 파싱 (BOM strip 후) | ✅ threads 659 전원 username/url/created_at 존재, 비표준 URL 0건 |
| `index.html:674-675` → `web_viewer/data.js` + `web_viewer/script.js` 로드 경로 | ✅ 확인 |
| LinkedIn/X 파일 변경 | ✅ `git diff` 0건 |

## 발견된 이슈

### Issue 1 — [기능 파손 → 본 세션에서 수정 완료]

**위치**: `thread_scrap.py:128-136` backfill `simple_item`

**증상**: `sns_platform` 필드 누락 → `normalize_post` 후에도 `""`로 남음 → `validate_post`가 `sns_platform` 필수 미충족 → 모든 backfill 레코드 skip → `existing_posts = []` (0개 백필, 조용한 실패)

**영향도**: 평상시 simple DB 파일이 있어 이 fallback 경로는 거의 타지 않음. simple 파일이 없을 때만 backfill이 동작하는데, 그때 전면 실패. 스크래퍼 런타임 에러는 없으므로 크리티컬 아님.

**수정** (2026-04-11 본 세션):
```python
simple_item = {
    "code": p.get('platform_id') or p.get('code'),
    "sns_platform": "threads",   # ← 추가
    "username": p.get('username'),
    ...
}
```

**검증**:
```
missing: []
sns_platform: 'threads'
pass
```

### Issue 2 — [품질, 미수정] `data.js` UTF-8 BOM

**위치**: `utils/build_data_js.py:33` `encoding='utf-8-sig'`

`data.js` 첫 바이트가 `\ufeff` (BOM). 브라우저 `<script>` 태그 로드는 BOM 허용 → 현재 웹 뷰어는 정상 동작. 단 Node `JSON.parse`와 일부 도구 연동 시 BOM strip 필요.

**영향도**: 기능에 즉시 영향 없음. 향후 도구 연동 불편 유발 가능.

**수정 대기**: `encoding='utf-8-sig'` → `'utf-8'` (write만). 기존 `total_scrap.py:278`과 일관성 고려 후 별도 결정.

### Observation O1 — CLAUDE.md 문서 불일치 → 해결됨

**이전 상태**: CLAUDE.md에 "브라우저에서 `web_viewer/index.html` 열기"로 적혀있으나, 실제 진입점은 레포 루트 `index.html`. `web_viewer/` 폴더에는 `index.html` 파일이 없음.

**해결**: 본 세션 CLAUDE.md 업데이트에서 `index.html` 경로를 레포 루트로 정정하고, 핵심 파일 표에 `index.html`을 명시 추가.

### Observation O2 — archive 브랜치 "스냅샷 깊이"

Plan Step 0-a는 `git add -A && git commit`으로 unstaged까지 스냅샷할 계획이었으나, 실제로는 브랜치만 생성되어 있음 (top commit = `39366a7` = 작업 직전 main HEAD 그대로). Git-tracked 파일 diff 복원에는 문제없으나, unstaged였던 파일 상태는 브랜치로 복원 불가. **폴더 백업**이 별도 존재하므로 실제 롤백 안전성은 유지됨.

### Observation O3 — `run()` 내 레거시 fallback 잔존

`thread_scrap_single.py:346` `p.get('user') or p.get('username')` — 마이그레이션 후에는 `user` 필드가 존재하지 않지만 여전히 fallback 체인에 남아있음. 동작상 문제 없으나 데드 코드. 의도적 호환 주석 권장.

### 노이즈 (크리티컬 아님)
- `implementation_plan.md` 루트 → `docs/` 이동 잔해 (이번 plan 범위 밖, 별도 정리 필요)
- `.playwright-mcp/` 폴더 untracked (gitignore 추가 또는 정리)

## Plan 성공 기준 7가지 최종 결과

| # | 성공 기준 | 결과 | 증거 |
|---|---|---|---|
| 1 | Threads "Unknown" 0건 | ✅ | data.js 검증: no_username=0 |
| 2 | View Original 5건 정상 | ✅ | threads 659 전원 표준 URL, non-threads.net 0건 |
| 3 | 전 975건 `validate_post` 통과 | ✅ | Python 전수 검증 invalid=0 |
| 4 | LinkedIn/X 회귀 없음 | ✅ | 파일 변경 없음 + data.js에 no_username 0 |
| 5 | 신규 5건 표준 스키마 | 🟡 | 재수집 미실행. 층 1/2/3 코드 리뷰로 정적 확증 |
| 6 | 백업 존재 | ✅ | archive 브랜치 + 폴더 백업 모두 확인 |
| 7 | Fallback 미발동 | ✅ | 모든 Threads 레코드에 `post.url` 존재 → `resolvePostUrl` 첫 줄에서 반환 |

## 후속 권장 조치

1. **[완료]** Issue 1 수정 (본 세션) — `thread_scrap.py:128-136`에 `sns_platform` 추가
2. **[완료]** CLAUDE.md 업데이트 (본 세션) — 진입점 경로 정정, 3층 게이트 설명 추가, post_schema.py/build_data_js.py 언급
3. **[선택]** Issue 2 — `utils/build_data_js.py:33` `utf-8-sig` → `utf-8` (일관성 고려)
4. **[정리]** `implementation_plan.md` 이동 건 별도 커밋
5. **[정리]** `.playwright-mcp/` gitignore 추가
6. **[선택]** 소규모 재수집 `python thread_scrap.py --mode update` 1회로 성공 기준 5 실증

## 총평

구현 품질이 매우 높습니다. Plan v2의 3층 게이트 전략이 정확히 구현됐고, 가장 중요한 층 1(`threads_parser.py`의 item 빌더)이 plan의 추정과 일치하게 레거시 키를 쓰고 있었으며 정확히 표준 키로 교체됐습니다. Codex가 plan에 없던 단위 테스트까지 추가한 건 추가 점수.

Issue 1은 Codex와 plan 작성자(본인) 모두 놓친 `sns_platform` 필드 누락이었고, 본 세션에서 1줄 수정으로 해결. 이로써 plan v2의 모든 의도가 실제 코드에 반영됐습니다.
