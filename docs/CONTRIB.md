# 개발 가이드 (CONTRIB.md)

이 문서는 프로젝트 개발 환경 구축 및 기여를 위한 가이드입니다.

## 1. 개발 환경 구축

- **언어**: Python 3.10+
- **런타임**: Playwright (브라우저 자동화)
- **런타임 설치**:
  ```bash
  pip install playwright-core playwriter
  playwright install chromium
  ```

## 2. 사용 가능한 스크립트

`package.json`의 `npm run` 명령어를 통해 주요 작업을 수행할 수 있습니다.

| 명령어                   | 실제 동작                  | 설명                             |
| :----------------------- | :------------------------- | :------------------------------- |
| `npm run start`          | `python server.py`         | Flask 백엔드 서버 실행           |
| `npm run view`           | `run_viewer.bat`           | 뷰어 런처 실행 (서버 + 브라우저) |
| `npm run stop`           | `stop_viewer.bat`          | 실행 중인 뷰어 및 서버 강제 종료 |
| `npm run scrap:threads`  | `python threads_scrap.py`  | Threads 데이터 수집 실행         |
| `npm run scrap:linkedin` | `python linkedin_scrap.py` | LinkedIn 데이터 수집 실행        |
| `npm run scrap:all`      | `python total_scrap.py`    | 전체 플랫폼 통합 수집 실행       |

## 3. 환경 변수 설정

`.env.example` 파일을 복사하여 `.env.local`을 생성하고 다음 정보를 입력합니다.

- `THREADS_ID`: Threads 계정 이메일
- `THREADS_PW`: Threads 계정 비밀번호

## 4. 코드 스타일 및 문서 규칙

- **Mermaid 다이어그램**: [Mermaid Rules](file:///c:/Users/ahnbu/.gemini/antigravity/basic_pj_rules/mermaid.md)를 준수하십시오.
  - 특수 문자 포함 레이블은 큰따옴표(`""`)로 감싸야 합니다.
  - VSCode 렌더링 호환성을 위해 `themeVariables` 설정을 적극 활용하십시오.
