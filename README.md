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

X detail consumer 추가 준비:

```powershell
pipx install twitter-cli
twitter --help
```

환경 변수는 `.env.local`에 둡니다.

```env
THREADS_ID=...
THREADS_PW=...
```

인증 런타임 정본은 `C:\Users\ahnbu\.config\auth`입니다. 레포의 `auth/` 폴더는 이 경로를 가리키는 junction이며, runtime source를 바꾼 뒤에는 아래 명령으로 다시 동기화합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\sync_auth_runtime.ps1 `
  -SourceRoot (Get-Location).Path `
  -AuthHome "$env:USERPROFILE\.config\auth" `
  -LegacyAuthDir ".\auth"
```

## 인증 갱신

중앙 renew entrypoint는 `C:\Users\ahnbu\.config\auth\renew.py`입니다. 레포 루트의 `renew_auth.py`는 같은 스크립트를 호출하는 compatibility proxy입니다.

LinkedIn, Threads, Skool, X 세션을 갱신할 때:

```powershell
python "$env:USERPROFILE\.config\auth\renew.py" linkedin
python "$env:USERPROFILE\.config\auth\renew.py" threads
python "$env:USERPROFILE\.config\auth\renew.py" skool
python "$env:USERPROFILE\.config\auth\renew.py" x
```

Threads 인증은 producer와 consumer가 같은 storage_state를 공유합니다.

- canonical: `AUTH_HOME/threads/storage_state.json`
- compatibility: `AUTH_HOME/auth_threads.json`
- `thread_scrap.py`: `/saved` 타임라인 수집
- `thread_scrap_single.py`: 같은 storage_state의 `.threads.com` 쿠키를 `requests`에 주입

X(Twitter) 인증은 producer와 consumer 역할을 분리해 관리합니다.

- canonical profile: `AUTH_HOME/x/user_data/`
- canonical cookie link: `AUTH_HOME/x/cookies.json`
- compatibility cookie link: `AUTH_HOME/x_cookies_current.json`
- dated snapshots: `AUTH_HOME/x/cookies_YYYYMMDD_HHmm.json`
- `twitter_scrap.py`: persistent Chrome profile
- `twitter_scrap_single.py`: `AUTH_HOME/x/cookies.json`과 latest dated snapshot fallback -> `twitter-cli`
- `inject_x_cookies.py`: current cookie snapshot을 persistent profile에 재주입

X 수동 인증 갱신이 필요한 경우:

- `twitter_scrap_single.py` 상세 조회가 반복 실패
- `twitter-cli` 토큰 누락 메시지 발생
- `AUTH_HOME/x/cookies.json`에 `auth_token` 또는 `ct0` 누락
- X 로그인 만료, 보안 확인, 추가 인증 화면 발생

앱 로그인 버튼이나 `renew.py --web`을 쓰지 않고 직접 갱신할 때:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --user-data-dir="$env:USERPROFILE\.config\auth\x\user_data" `
  --new-window "https://x.com/i/flow/login"
```

Chrome 로그인/동기화 안내가 뜨면 Google 계정으로 로그인하지 말고 `로그인 안함`을 선택합니다. X 로그인 후 Chrome을 완전히 닫고 export/검증을 진행합니다.

수동 갱신 성공 기준:

- `AUTH_HOME/x/cookies.json`이 최신 `cookies_YYYYMMDD_HHmm.json`을 가리킴
- 쿠키에 `auth_token`, `ct0`가 모두 존재
- `twitter-cli` 상세 조회 성공

producer용 X Chrome 프로필을 다시 저장할 때:

```powershell
python "$env:USERPROFILE\.config\auth\renew.py" x
```

저장된 고정 쿠키 파일을 persistent profile에 주입할 때:

```powershell
python inject_x_cookies.py
```

## 실행

권장 뷰어 진입은 `SNS허브_바로가기.lnk` 또는 아래 명령입니다.

```powershell
npm run view
```

이 흐름은 `sns_hub.vbs`가 `/api/status`를 확인하고 필요 시 `python server.py`를 백그라운드로 띄운 뒤, `http://localhost:5000/`를 엽니다. 현재 shipped HTML 진입점은 루트 `index.html`이며, `server.py`는 API 제공이 중심입니다.

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

X consumer 토큰이 없으면 `twitter_scrap_single.py` 상세 수집은 건너뛰고, 기존 메타데이터 기준 full 동기화만 진행합니다.
Threads consumer는 Playwright 없이 `AUTH_HOME/threads/storage_state.json` 쿠키만 유효하면 실행됩니다.

## 웹 뷰어와 태그 저장

- `index.html`은 `web_viewer/script.js`를 로드해 게시물을 렌더링합니다.
- 메타 목록은 `GET /api/posts`로 읽고, 상세 본문과 미디어는 `GET /api/post/<sequence_id>`로 lazy-load 합니다.
- 검색은 `GET /api/search`, 자동 태그 일괄 적용은 `POST /api/auto-tag/apply`를 사용합니다.
- 태그, 강조 토글, 자동 태그 규칙은 `localStorage`와 `web_viewer/sns_tags.json`을 함께 사용합니다.
- 태그 동기화 API는 `/api/get-tags`, `/api/save-tags`입니다.
- 스크래퍼 트리거와 서버 상태 확인은 `/api/run-scrap`, `/api/status`를 사용합니다.
- 레거시 Threads 태그 키(`threads.net`, `/t/`)는 뷰어에서 `www.threads.com` canonical로 정규화합니다.

## 시간·정렬 기준

- `created_at`: 게시글이 플랫폼에 작성된 시간입니다. 웹 뷰어의 `작성일순` 기준입니다.
- `crawled_at`: 게시글이 이 프로젝트의 로컬 파일에 처음 수집된 시간입니다.
- `sequence_id`: 통합 결과 파일 안에서 다시 부여되는 로컬 순서 번호입니다.
- `platform_sequence_id`: 플랫폼별 수집 파일에서 보존한 순서 번호입니다.
- `platform_saved_at`: 실제 플랫폼에서 사용자가 저장한 시간입니다. 현재 스키마에는 없으며, 수집 가능성은 `BACKLOG.md`의 `BL-0504-01`에서 별도로 추적합니다.

현재 웹 뷰어의 `로컬 수집순`은 실제 플랫폼 저장시간순이 아니라 `crawled_at`과 플랫폼별 순서를 기준으로 만든 로컬 정렬입니다.

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
