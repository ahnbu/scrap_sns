# BACKLOG — 후속 작업 후보

AI는 새 작업 발견 시 이 파일에 추가하라.

| #   | 항목                            | 위치                                                 | 메모                                                                                                                               |
| --- | ----------------------------- | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Instagram CDN 403             | `server.py`, `web_viewer/script.js:handleImgError` | wsrv.nl 프록시 미사용 케이스 존재. server.py 이미지 프록시 엔드포인트 또는 local_images 다운로드 파이프라인 확장이 근본 해법                                             |
| 2   | Tailwind CDN 경고               | `index.html`                                       | `tailwind-built.css` 존재함에도 CDN script 병렬 로드 중. `<script src="https://cdn.tailwindcss.com?…">` 제거 여부 확인                           |
| 3   | Masonry 성능                    | `web_viewer/script.js`                             | 975개 포스트 렌더 시 setTimeout 500ms+ 발생. 가상 스크롤 또는 페이지네이션 도입                                                                          |
| 6   | `sns_tags.json` other 172건 분석 | `web_viewer/sns_tags.json`                         | tag key 복구 블록이 건드리지 않는 기타 키 172건. legacy `post_url` 형태인지 별도 drift인지 1회 스캔 필요                                                     |
| 7   | 자동 태그 마이그레이션 테스트 커버리지         | `tests/unit/test_web_viewer_auto_tagging.py`       | `test_migrate_legacy_tag_keys`가 happy path만 커버. `existing === ['keep'] + src === []` 보존 케이스 추가 필요 (canonical target 태그 파괴 회귀 방지) |
