# SNS 허브

Threads, LinkedIn, X(Twitter)의 저장 게시물을 수집하고, 통합 JSON과 로컬 웹 뷰어로 관리하는 프로젝트입니다.

## 현재 구성

- 수집기: `thread_scrap.py`, `thread_scrap_single.py`, `linkedin_scrap.py`, `twitter_scrap.py`, `twitter_scrap_single.py`, `total_scrap.py`
- 뷰어/API: `index.html`, `web_viewer/`, `server.py`
- 데이터 산출물: `output_threads/`, `output_linkedin/`, `output_twitter/`, `output_total/`
- 참조 문서: `docs/development.md`, `docs/crawling_logic.md`
- 자동 검증: `tests/`

## 설치

```powershell
pip install -r requirements.txt
playwright install chromium
```

프런트엔드 자산을 다시 빌드하거나 `npm run *` 래퍼를 사용할 예정이면 추가로 아래를 실행합니다.

```powershell
npm install
```

환경 변수는 `.env.local`에 둡니다.

```env
THREADS_ID=...
THREADS_PW=...
```

## 인증 갱신

Threads와 LinkedIn 세션을 다시 저장할 때:

```powershell
python renew_auth.py
```

X(Twitter) Chrome 프로필을 다시 저장할 때:

```powershell
python renew_twitter_auth.py
```

## 실행

권장 뷰어 진입은 `SNS허브_바로가기.lnk` 또는 아래 명령입니다.

```powershell
npm run view
```

이 흐름은 `sns_hub.vbs`가 `python server.py`를 백그라운드로 띄우고, `/api/status` 확인 후 레포 루트의 `index.html`을 엽니다. 현재 shipped HTML 진입점은 루트 `index.html`이며, `server.py`는 API 제공이 중심입니다.

서버만 따로 올리거나 종료하려면:

```powershell
npm run start
npm run stop
```

`run_viewer.bat`는 수동 실행용 보조 런처입니다. 기본 진입 문서로 가정하지 마세요.

## 크롤링

전체 병렬 수집:

```powershell
python total_scrap.py --mode update
python total_scrap.py --mode all
```

개별 실행:

```powershell
python thread_scrap.py --mode update
python thread_scrap_single.py
python linkedin_scrap.py --mode update
python twitter_scrap.py --mode update
python twitter_scrap_single.py
```

`npm run scrap:threads`, `npm run scrap:linkedin`, `npm run scrap:all`도 같은 스크립트를 감싸는 래퍼입니다.

## 웹 뷰어와 태그 저장

- `index.html`은 `web_viewer/script.js`를 로드해 게시물을 렌더링합니다.
- 최신 데이터는 `/api/latest-data` 또는 `web_viewer/data.js`를 통해 읽습니다.
- 태그, 강조 토글, 자동 태그 규칙은 `localStorage`와 `web_viewer/sns_tags.json`을 함께 사용합니다.
- 태그 동기화 API는 `/api/get-tags`, `/api/save-tags`입니다.
- 스크래퍼 트리거와 서버 상태 확인은 `/api/run-scrap`, `/api/status`를 사용합니다.
- 레거시 Threads 태그 키(`threads.net`, `/t/`)는 뷰어에서 `www.threads.com` canonical로 정규화합니다.

## 표준 데이터 스키마

정본은 `utils/post_schema.py`입니다.

```python
STANDARD_FIELD_ORDER = [
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
- Threads canonical URL: `https://www.threads.com/@{username}/post/{code}`
- 레거시 필드(`user`, `timestamp`, `post_url`, `source_url`)는 `normalize_post()`에서 현재 스키마로 승격됩니다.

## 유틸리티

SNS 데이터 조회 CLI:

```powershell
node utils/query-sns.mjs --help
```

레거시 스키마/도메인 점검:

```powershell
python migrate_schema.py --target "output_total/total_full_*.json"
python migrate_threads_domain.py --dry-run
```

뷰어용 정적 데이터 재생성:

```powershell
python -m utils.build_data_js
```

## 테스트

```powershell
pytest --collect-only
pytest tests/unit
pytest tests/contract
pytest tests/e2e/test_api_security.py
pytest tests/smoke
```

UI 세부 검증 스크립트와 CLI 검증 스크립트도 `tests/ui_verification.py`, `tests/verify_query_sns_cli.mjs`에 있습니다.

## 참조 문서

- [개발 가이드](./docs/development.md): 플랫폼별 데이터 구조, canonical URL, 영구화 surface
- [크롤링 로직](./docs/crawling_logic.md): Producer/Consumer 흐름, 병합, 뷰어 연동
- [CHANGELOG](./CHANGELOG.md): 변경 이력
- [BACKLOG](./BACKLOG.md): 후속 작업 후보
