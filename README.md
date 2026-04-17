# 🕷️ SNS Saved Posts Crawler (SNS 허브)

Threads, LinkedIn, X(Twitter) 플랫폼의 저장된 게시물을 자동으로 수집하고 관리하는 통합 크롤러 시스템입니다.

## 📂 프로젝트 구조

```text
scrap_sns/
├── auth/                 # SNS 세션 인증 정보 (Git 제외)
├── docs/                 # 프로젝트 문서 및 PDCA 보고서
├── output_threads/       # Threads 수집 결과 (JSON, MD)
├── output_linkedin/      # LinkedIn 수집 결과 (JSON, MD)
├── output_twitter/       # X(Twitter) 수집 결과 (JSON, MD)
├── output_total/         # 모든 플랫폼 통합 결과 및 웹 뷰어 데이터
├── tests/                # [New] 자동 테스트 코드 (pytest)
├── web_viewer/           # 수집된 데이터를 시각화하는 웹 대시보드
├── thread_scrap.py       # Threads 개별 스크래퍼
├── linkedin_scrap.py     # LinkedIn 개별 스크래퍼
├── total_scrap.py        # 통합 병렬 스크래퍼 (권장 실행 파일)
└── server.py             # 데이터 제공 및 스크래핑 제어 API 서버
```


## 🔐 세션 인증정보(Auth) 갱신

SNS 보안 정책으로 인해 로그인이 막히거나 세션이 만료된 경우, 수동으로 인증정보를 갱신해야 합니다. 상세 내용은 [인증정보 갱신 가이드](./docs/auth_renewal_guide.md)를 참조하세요.

### Threads & LinkedIn 갱신
`powershell
python renew_auth.py
`
브라우저에서 직접 로그인 후 터미널에 y를 입력하면 uth/*.json 파일이 업데이트됩니다.

### Twitter(X) 갱신
`powershell
python renew_twitter_auth.py
`
실제 설치된 Chrome을 열어 세션 데이터를 uth/x_user_data/에 직접 저장합니다.

## 🚀 시작하기

### 1. 요구사항
- Python 3.8+
- Playwright (브라우저 자동화)
- 각 SNS 계정 정보 (`.env.local` 파일)

### 2. 설치
```powershell
# 패키지 설치
pip install playwright python-dotenv requests pytest

# Playwright 브라우저 엔진 설치
playwright install chromium
```

### 3. 환경 설정 (`.env.local`)
```env
THREADS_ID=사용자ID
THREADS_PW=비밀번호
# LinkedIn은 첫 실행 시 브라우저에서 직접 로그인 권장
```

## 🛠️ 실행 가이드

### 통합 스크래핑 (권장)
모든 플랫폼을 병렬로 실행하며, 이미지 로컬 다운로드 및 웹 뷰어 데이터를 갱신합니다.
```powershell
# 증분 업데이트 (기본값)
python total_scrap.py --mode update

# 전체 데이터 재수집
python total_scrap.py --mode all
```
*실행 로그는 `logs/` 폴더 내 플랫폼별 파일(`.log`)로 실시간 저장됩니다.*

### 웹 뷰어 실행
기본 실행은 `SNS허브_바로가기.lnk`입니다. 더블클릭하면 `sns_hub.vbs`가 `python server.py`를 숨김 실행한 뒤 브라우저로 `index.html`을 엽니다.
```powershell
wscript sns_hub.vbs
```
CLI로만 실행하려면 `wscript sns_hub.vbs`를 사용하세요.

## 🧪 테스트 및 검증

프로젝트의 안정성을 위해 `pytest` 기반의 자동 테스트를 지원합니다.
```powershell
# 전체 테스트 실행
pytest

# 특정 영역 테스트
pytest tests/unit/     # 로직 테스트
pytest tests/contract/ # 데이터 스키마 검증
```

## 📜 주요 업데이트 (2026-03-10)
- **P0 수정**: `server.py` 변수 버그 수정, 메타데이터 키 불일치 해결, `argparse` import-safe 구조 개선.
- **P1 도입**: 자동 테스트 체계(`tests/`) 구축 및 설치/실행 문서 현행화.

