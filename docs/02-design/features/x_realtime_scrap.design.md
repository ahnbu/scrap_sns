---
title: "Design: X(Twitter) 북마크 실시간 크롤러 (Playwright)"
created: "2026-02-12 12:07"
---

# Design: X(Twitter) 북마크 실시간 크롤러 (Playwright)

이 문서는 Playwright를 활용하여 X(Twitter) 북마크를 실시간으로 스크래핑하기 위한 상세 설계 내용을 담고 있습니다.

## 1. 환경 설정 (Configuration)
- `WINDOW_X`: 0 (초기 확인용)
- `WINDOW_Y`: 0
- `WINDOW_WIDTH`: 900
- `WINDOW_HEIGHT`: 600
- `AUTH_FILE`: `auth/auth_twitter.json`
- `TARGET_LIMIT`: 수집 목표 개수 (0은 무제한)

## 2. 주요 로직 설계

### 2.1 브라우저 구동 및 인증 (Authentication)
1. `sync_playwright`를 사용하여 크롬 브라우저 실행.
2. `storage_state`가 존재하면 로드하여 세션 복구.
3. `https://x.com/i/bookmarks`로 이동.
4. 만약 로그인 페이지가 나타나면, 사용자가 로그인할 때까지 대기 (`page.wait_for_url` 또는 특정 요소 감지).
5. 로그인 성공 시 `storage_state`를 `AUTH_FILE`에 저장.

### 2.2 실시간 데이터 가로채기 (Packet Interception)
- `page.on("response", handler)` 등록.
- `handler` 내에서 URL에 `Bookmarks?variables=`가 포함되어 있는지 확인.
- 조건 만족 시 `response.json()`을 추출하여 기존 `extract_from_json` 로직 실행.

### 2.3 무한 스크롤 및 종료 조건
- **루프 실행**:
    1. 현재 `page.content()`를 가져와 `extract_from_html` 실행 (DOM 기반 수집).
    2. 중복을 제외한 신규 게시글 수 카운트.
    3. `--mode update` 인 경우: 수집된 게시글 중 기존 DB의 최신 게시글 ID가 발견되면 즉시 루프 종료.
    4. 하단으로 스크롤 수행 및 랜덤 지연 (`time.sleep`).
    5. `TARGET_LIMIT` 도달 시 종료.

## 3. 데이터 통합 및 저장 방식
- `all_posts_map`: `url`을 키로 사용하는 딕셔너리를 유지하여 실시간으로 중복 제거 및 데이터 병합.
- 최종 수집 완료 후 기존 `twitter_py_full_*.json`과 병합하여 새로운 Full 버전 및 Update 버전 생성.

## 4. 예외 처리
- **네트워크 에러**: 타임아웃 발생 시 재시도 로직.
- **차단 감지**: 게시물이 로딩되지 않거나 "잠시 후 다시 시도" 메시지 발생 시 알림 및 대기.
