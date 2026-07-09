# utils 지침

## 범위

- 플랫폼별 parser/adapter, 표준 Post 스키마, post metadata, 로컬 조회 CLI를 다룬다.
- 루트 수집기와 서버가 재사용하는 계약이 많으므로, 작은 변경도 출력 JSON과 뷰어 API에 전파될 수 있다.

## 정본 파일

- `post_schema.py`: `STANDARD_FIELD_ORDER`, required fields, legacy field 승격의 정본
- `post_meta.py`: `/api/posts` 메타 응답과 `post_key`, `canonical_url`, thumbnail 생성의 정본
- `query-sns.mjs`: 로컬 SNS 조회 CLI 정본
- `threads_parser.py`, `linkedin_parser.py`, `twitter_parser.py`: 플랫폼별 원천 응답 파싱
- `threads_http_adapter.py`, `twitter_cli_adapter.py`: 외부 수집 경로 어댑터
- `auth_paths.py`, `auth_status.py`: 인증 런타임 경로와 상태 판정

## 변경 규칙

- 표준 필드 추가, 삭제, 순서 변경은 `post_schema.py`에서 시작하고 contract/unit test와 문서를 같이 맞춘다.
- `normalize_post()`의 legacy field 승격은 기존 output JSON 재처리 필요 여부를 판단한 뒤 바꾼다.
- Threads URL canonical 규칙은 `post_schema.py`, `post_meta.py`, `query-sns.mjs`, `web_viewer/script.js`가 같은 방향이어야 한다.
- `post_key` 생성 규칙을 바꾸면 `web_viewer/sns_user_metadata.json`의 기존 별표, 숨김, 메모 연결이 깨질 수 있다.
- CLI 출력 형식 변경은 사람이 읽는 `brief`, 기계가 읽는 `json`, export용 `md`를 분리해서 본다.

## 검증

- 스키마 변경: `pytest tests/contract tests/unit/test_post_schema.py`
- parser 변경: 해당 플랫폼 parser unit test와 integration test 실행
- CLI 변경: `node utils/query-sns.mjs --help`와 관련 `tests/verify_query_sns_cli.mjs` 또는 `tests/query_sns_search_helpers.test.mjs` 실행
- URL 정규화 변경: `pytest tests/unit/test_migrate_threads_domain.py tests/unit/test_web_viewer_resolve_post_url.py`

## 금지

- 표준 스키마를 각 수집기에서 임의로 재정의하지 않는다.
- 최신 `output_total` 하나만 보고 parser 변경의 성공을 판단하지 않는다.
- 인증 파일 경로를 repo-local `auth/` 실파일로 하드코딩하지 않는다. 정본은 사용자 config auth runtime이다.
