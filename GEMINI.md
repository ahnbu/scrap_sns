# SNS Scrap 프로젝트 운영 규칙 (GEMINI.md)

## 핵심 원칙

- 브라우저 제어와 파싱 로직을 분리한다. 추출 로직은 `utils/*_parser.py`에 둔다.
- 파서나 URL 정규화 로직을 바꿀 때는 관련 unit test를 먼저 확인하고 수정 후 다시 실행한다.
- 표준 데이터 스키마의 정본은 `utils/post_schema.py`다. 문서나 임의 dict 순서를 기준으로 삼지 않는다.

## 현재 활성 범위

- 플랫폼: Threads, LinkedIn, X(Twitter)
- 메인 오케스트레이터: `total_scrap.py`
- 뷰어 진입: `wscript sns_hub.vbs` 또는 `SNS허브_바로가기.lnk`
- API 서버: `server.py`

## 표준 Post 스키마

현재 필드 순서는 아래와 같다.

```python
[
    "sequence_id",
    "platform_id",
    "sns_platform",
    "code",
    "urn",
    "username",
    "display_name",
    "full_text",
    "media",
    "url",
    "created_at",
    "date",
    "crawled_at",
    "source",
    "local_images",
    "is_detail_collected",
    "is_merged_thread",
]
```

- 필수 필드: `sns_platform`, `username`, `url`, `created_at`
- 레거시 필드(`user`, `timestamp`, `post_url`, `source_url`)는 `normalize_post()`가 현재 스키마로 승격한다.
- Threads canonical URL은 `https://www.threads.com/@{username}/post/{code}`다.

## 개발 및 운영 워크플로우

1. 관련 테스트와 기존 구현을 먼저 확인한다.
2. 파서 또는 스키마를 수정한다.
3. 필요하면 `migrate_schema.py`, `migrate_threads_domain.py`로 기존 데이터를 점검한다.
4. `python -m utils.build_data_js`로 뷰어용 정적 데이터를 재생성한다.
5. 관련 pytest와 CLI 검증을 다시 실행한다.

## 주요 경로

- Parser: `utils/{platform}_parser.py`
- Tests: `tests/unit/test_*`, `tests/contract/test_schemas.py`
- Auth: `auth/auth_threads.json`, `auth/auth_linkedin.json`, `auth/x_user_data/`
- Viewer state: `web_viewer/data.js`, `web_viewer/sns_tags.json`

## 권장 검증

```powershell
pytest tests/unit
pytest tests/contract
pytest tests/e2e/test_api_security.py
node utils/query-sns.mjs --help
python migrate_threads_domain.py --dry-run
```

## 참조 문서

- `README.md` — 실행 진입점, 태그 저장, 주요 명령
- `docs/development.md` — 플랫폼별 데이터 구조·URL 형식
- `docs/crawling_logic.md` — 필드 정의와 전체 흐름

## 주의 사항

- `server.py`는 현재 API 제공이 중심이다. shipped HTML 진입은 레포 루트 `index.html` 기준으로 이해한다.
- 태그는 `localStorage`와 `web_viewer/sns_tags.json`을 함께 사용한다.
- X는 리다이렉트와 실제 사용자명 보정 때문에 URL과 본문이 단순 1:1이 아닐 수 있다.
