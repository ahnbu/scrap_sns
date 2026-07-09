# web_viewer 지침

## 범위

- 브라우저 UI 상태, 태그/카탈로그/사용자 메타데이터 JSON, Tailwind 산출 CSS를 다룬다.
- 서버 API 계약은 `scrap_sns_server.py`가 정본이고, 이 폴더는 그 API를 소비하는 뷰어 surface다.

## 정본 파일

- `script.js`: 검색, 필터, 정렬, 태그, 별표, 숨김, 메모, 수집 결과 모달의 주 로직
- `style.css`: 뷰어 고유 스타일
- `tailwind-input.css`: Tailwind 입력 CSS
- `tailwind-built.css`: 빌드 산출 CSS
- `sns_tags.json`: 게시물 URL 기준 태그 저장소
- `sns_tag_catalog.json`: 태그명, 강조 표시, alias, 키워드 저장소
- `sns_user_metadata.json`: `post_key` 기준 별표, 숨김, 메모 저장소

## 변경 규칙

- 태그 저장 키를 바꿀 때는 `resolvePostUrl()`와 `migrateLegacyTagKeys()`의 Threads alias 마이그레이션을 같이 확인한다.
- 별표, 숨김, 메모는 URL이 아니라 `post_key` 기준이다. `sns_user_metadata.json` 구조 변경은 서버 API와 테스트를 같이 맞춘다.
- `localStorage`와 JSON 파일을 함께 쓰는 상태는 한쪽만 갱신하지 않는다.
- 검색, 필터, 정렬, 태그 UI 변경은 DOM 렌더만 보지 말고 `/api/posts`, `/api/search`, `/api/save-tags`, `/api/save-user-metadata` 흐름까지 확인한다.
- `tailwind-built.css`를 손으로 부분 수정하지 않는다. 스타일 의도는 입력 CSS나 HTML/JS class에서 관리한다.

## 검증

- UI 로직 단위 변경: 관련 `tests/unit/test_web_viewer_*.py` 실행
- 검색/태그 API 연동 변경: `tests/integration/test_search_api.py`, `tests/integration/test_auto_tag_apply_api.py`, `tests/integration/test_tag_catalog_api.py` 중 관련 테스트 실행
- 실제 사용자 경험 변경: `npm run view`로 서버를 재시작하고 `http://localhost:5000/`에서 입력, 클릭, 결과 표시를 확인

## 금지

- `sns_tags.json`, `sns_tag_catalog.json`, `sns_user_metadata.json`의 기존 키를 migration 없이 삭제하지 않는다.
- 뷰어 변경 완료를 API 응답만으로 선언하지 않는다.
- 수집 결과 JSON과 뷰어 표시 건수의 불일치를 단순 캐시 문제로 가정하지 않는다.
