# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

개인 SNS 저장 게시물 수집기. Playwright 기반 Python 스크래퍼로 Threads, LinkedIn, Twitter/X, Substack의 게시물을 수집하고, Flask API + 바닐라 JS 웹 뷰어로 열람합니다.

## Commands

### 스크래핑 실행

```bash
# 전체 플랫폼 병렬 수집 (권장)
python total_scrap.py --mode update   # 증분 업데이트 (기본)
python total_scrap.py --mode all      # 전체 재수집

# 개별 플랫폼
python thread_scrap.py --mode update          # Threads 목록 수집 (Producer)
python thread_scrap_single.py                 # Threads 상세 수집 (Consumer)
python linkedin_scrap.py --mode update        # LinkedIn 저장 게시물
python twitter_scrap.py --mode update         # Twitter/X (Producer)
python twitter_scrap_single.py                # Twitter/X (Consumer)

# 특정 사용자 수집
python linkedin_scrap_by_user.py --user {slug} --limit 50 --duration 3m
python substack_scrap_by_user.py --user {user_id} --limit 0
```

### 웹 뷰어 서버

```bash
python server.py          # Flask API 서버 (port 5000)
# 브라우저에서 web_viewer/index.html 열기
```

### 유틸리티

```bash
python utils/json_to_md.py    # JSON → Markdown 변환
python migrate_schema.py      # 스키마 필드 순서 정규화
```

## Architecture

### 데이터 플로우

```
SNS 플랫폼
  → Producer 스크래퍼 (목록 수집)
    → output_{platform}/python/update/  (증분 파일)
  → Consumer 스크래퍼 (상세 수집, Threads/Twitter만)
    → output_{platform}/python/{platform}_py_full_{date}.json
  → total_scrap.py (병합 오케스트레이터)
    → output_total/total_full_{date}.json
  → Flask API (server.py)
  → Web Viewer (web_viewer/)
```

### 핵심 파일

| 파일 | 역할 |
|------|------|
| `total_scrap.py` | 전체 플랫폼 병렬 실행 오케스트레이터 |
| `thread_scrap.py` | Threads 목록 수집 (Producer) |
| `thread_scrap_single.py` | Threads 개별 게시물 상세 수집 (Consumer, async) |
| `linkedin_scrap.py` | LinkedIn 저장 게시물 |
| `twitter_scrap.py` | Twitter/X 수집 (Producer) |
| `server.py` | Flask REST API (port 5000) |
| `web_viewer/script.js` | 웹 뷰어 메인 로직 |
| `utils/json_to_md.py` | JSON → Markdown 변환 유틸 |

### 2단계 수집 패턴 (Threads, Twitter)

Producer → Consumer 구조로 동작:
1. **Producer** (`thread_scrap.py`, `twitter_scrap.py`): 목록 페이지 스크롤하며 기본 정보 수집
2. **Consumer** (`thread_scrap_single.py`, `twitter_scrap_single.py`): 미수집 항목 (`is_detail_collected: false`)을 병렬 탭으로 상세 수집
3. 실패 이력은 `scrap_failures_{platform}.json`에 기록, 3회 이상 실패 시 건너뜀

### 표준 Post 스키마 (필드 순서 엄수)

```python
STANDARD_FIELD_ORDER = [
    "sequence_id", "platform_id", "sns_platform", "username", "display_name",
    "full_text", "media", "url", "created_at", "date", "crawled_at", "source", "local_images"
]
```

새 필드 추가 시 `migrate_schema.py`로 기존 데이터 정규화 필요.

### 인증 세션

- `auth/auth_threads.json` - Playwright browser storage state (Threads)
- `auth/auth_linkedin.json` - Playwright browser storage state (LinkedIn)
- `auth/` 폴더 전체 gitignore됨. 초기 실행 시 로그인 UI가 열리고 세션 저장됨.
- `.env.local`: `THREADS_ID`, `THREADS_PW` 환경변수 (일부 스크래퍼에서 자동 로그인용)

### 출력 디렉토리 구조

```
output_threads/python/
  update/          # 증분 파일 (gitignore)
  threads_py_full_{date}.json   # 전체 누적 파일
output_linkedin/python/          # 같은 구조
output_twitter/python/           # 같은 구조
output_linkedin_user/{slug}/     # 사용자별
output_substack/{user_id}/       # Substack 사용자별
output_total/
  total_full_{date}.json         # 웹 뷰어가 읽는 최종 병합 파일
  update/                        # 증분 (gitignore)
```

### 웹 뷰어 (`web_viewer/`)

- `script.js`: 마소니 그리드, 검색, 플랫폼 필터, 즐겨찾기/태그/투두 (localStorage 저장)
- `data.js`: 최신 `total_full_*.json`을 JS 변수로 변환한 정적 파일
- `sns_tags.json`: 태그 데이터 (Flask API로 read/write)
- Tailwind CSS 사용 (`tailwind-input.css` → `tailwind-built.css`)

### Windows 특화 사항

- 모든 파일 I/O: `encoding='utf-8'` 또는 `encoding='utf-8-sig'` 명시
- subprocess 실행: `PYTHONIOENCODING=utf-8` 환경변수 필수
- 브라우저 위치: `WINDOW_X = 5000` (화면 밖 배치로 사용자 방해 최소화)
- 프로세스 종료: `taskkill /F /T /PID` 사용

## 개발 시 유의사항

- `tmp/`, `temp_code/`, `temp-code/` 폴더는 실험용 임시 코드 (gitignore). 참조는 가능하나 수정 대상이 아님.
- `test_runs/` 폴더: 특정 시점의 테스트 스냅샷 보관용.
- 스크래퍼 CLI에서 `--mode all`은 전체 재수집이므로 데이터 용량 주의.
- `total_scrap.py`는 로그를 `logs/{platform}.log`에 저장 (gitignore).
