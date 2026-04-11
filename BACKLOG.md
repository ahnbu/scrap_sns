# BACKLOG — 후속 작업 후보

AI는 새 작업 발견 시 이 파일에 추가하라.

| # | 항목 | 위치 | 메모 |
|---|------|------|------|
| 1 | Instagram CDN 403 | `server.py`, `web_viewer/script.js:handleImgError` | wsrv.nl 프록시 미사용 케이스 존재. server.py 이미지 프록시 엔드포인트 또는 local_images 다운로드 파이프라인 확장이 근본 해법 |
| 2 | Tailwind CDN 경고 | `index.html` | `tailwind-built.css` 존재함에도 CDN script 병렬 로드 중. `<script src="https://cdn.tailwindcss.com?…">` 제거 여부 확인 |
| 3 | Masonry 성능 | `web_viewer/script.js` | 975개 포스트 렌더 시 setTimeout 500ms+ 발생. 가상 스크롤 또는 페이지네이션 도입 |
| 4 | Twitter 날짜 버그 | `twitter_scrap_single.py:146-147` | Consumer가 `date`/`timestamp`를 `datetime.now()`로 덮어씀. Producer의 `created_at` 값을 보존해야 함 |
