# BACKLOG — 후속 작업 후보

AI는 새 작업 발견 시 이 파일에 추가하라.

| 날짜         | 항목                            | 위치                                                 | 실행 용이성 | 기대효과  | 메모                                                                                                                               |
| ---------- | ----------------------------- | -------------------------------------------------- | ------ | ----- | -------------------------------------------------------------------------------------------------------------------------------- |
| 2026-04-12 | Instagram CDN 403             | `server.py`, `web_viewer/script.js:handleImgError` | `██░░░░` | `██████` | wsrv.nl 프록시 미사용 케이스 존재. server.py 이미지 프록시 엔드포인트 또는 local_images 다운로드 파이프라인 확장이 근본 해법                                             |
| 2026-04-12 | Masonry 성능                    | `web_viewer/script.js`                             | `██░░░░` | `████░░` | 975개 포스트 렌더 시 setTimeout 500ms+ 발생. 가상 스크롤 또는 페이지네이션 도입                                                                          |
| 2026-04-12 | `sns_tags.json` other 172건 분석 | `web_viewer/sns_tags.json`                         | `████░░` | `████░░` | tag key 복구 블록이 건드리지 않는 기타 키 172건. legacy `post_url` 형태인지 별도 drift인지 1회 스캔 필요                                                     |
| 2026-04-12 | 자동 태그 마이그레이션 테스트 커버리지         | `tests/unit/test_web_viewer_auto_tagging.py`       | `████░░` | `████░░` | `test_migrate_legacy_tag_keys`가 happy path만 커버. `existing === ['keep'] + src === []` 보존 케이스 추가 필요 (canonical target 태그 파괴 회귀 방지) |
| 2026-04-12 | Twitter 본문 오염 (봇 차단 리다이렉트)       | `twitter_scrap.py`, `twitter_scrap_single.py`      | `██░░░░` | `██████` | X 봇 차단으로 0.5~1초 내 리다이렉트 → 원본이 아닌 다른 페이지 본문 수집됨. 수집 79건 중 33건 중복 본문 경고. 오염 감지(본문 중복 체크) 또는 수집 재시도 로직 필요. 참고: SPEC `docs/specs/20260412_01_SNS-스크래퍼-수집누락-개선.md`, session `0ca38559-5818-41f1-ba30-f02f2fbe7d8d` |
| 2026-04-13 | Phase B: 태그 write (canonical key + write conflict) | `utils/query-sns.mjs`, `server.py`, `web_viewer/script.js:574-583` | `██░░░░` | `████░░` | `tag add/remove` 구현 전 선행 조건 4가지: (1) canonical key 규칙 문서화 (2) URL 정규화 로직 (3) write conflict 방안 확정 (4) write-path 테스트. plan: `~/.claude/plans/atomic-soaring-thacker.md` Phase B 섹션. 검수보고서: `docs/plan-check/20260412_atomic-soaring-thacker_검수보고서.md` |

> **컬럼 기준** — `실행 용이성`: `██████` 쉬움 / `████░░` 보통 / `██░░░░` 어려움 | `기대효과`: `██████` 높음 / `████░░` 보통 / `██░░░░` 낮음. 두 값의 합이 클수록 우선순위 높음. AI 초안이므로 실행 전 재평가 권장.
