---
template: design
version: 1.2
description: 특정 사용자의 링크드인 게시글을 스크랩하는 기능 (linkedin_scrap_by_user.py) 설계서
---

# linkedin_scrap_by_user 설계서

> **요약**: Playwright를 이용한 네트워크 가로채기 방식의 특정 사용자 활동 페이지 스크래퍼 설계
>
> **프로젝트**: scrap_sns
> **작성자**: Gemini CLI
> **날짜**: 2026-02-07
> **상태**: 완료

---

## 1. 시스템 아키텍처

### 1.1 개요

`linkedin_scrap.py`의 기본 골격을 유지하되, 특정 사용자의 공개 프로필 및 활동 탭(`recent-activity/all/`)에 최적화된 `LinkedinUserScraper` 클래스를 구현합니다.

### 1.2 구성 요소

- **CLI 파서**: `user`, `limit`, `duration` 인자를 받아 내부 변수로 할당합니다.
- **기간 파서**: `3d`, `1m`, `1y` 등의 문자열을 `timedelta` 객체로 변환합니다.
- **Playwright 엔진**: 헤드풀(Headless=False) 모드로 브라우저를 실행하고 네트워크 응답(`response`)을 가로챕니다.
- **데이터 처리기**: 가로챈 JSON 데이터(GraphQL)에서 게시글 정보를 추출하고, Snowflake ID를 날짜로 변환합니다.
- **저장 관리자**: 사용자 ID별로 독립된 폴더를 생성하고, 증분 업데이트 및 전체 병합 파일을 관리합니다.

---

## 2. 데이터 설계

### 2.1 저장 구조

```
output_linkedin_user/
└── {user_id}/
    └── python/
        ├── update/
        │   └── linkedin_python_update_20260207_123456.json (최신 수집분)
        └── linkedin_py_full_20260207.json (전체 병합본)
```

### 2.2 데이터 스키마 (JSON)

기본 데이터 필드는 다음과 같습니다:

- `code`: 활동 고유 ID (Activity URN)
- `username`: 게시글 작성자 이름
- `created_at`: Snowflake ID에서 추출한 생성 일시
- `time_text`: 상대적 시간 (예: "2시간 전")
- `full_text`: 정제된 게시글 본문
- `post_url`: 게시글 직접 링크
- `images`: 게시글에 포함된 이미지 URL 배열
- `sequence_id`: 정렬을 위한 순차 ID

---

## 3. UI/UX 및 인터페이스 설계

### 3.1 CLI 명령 인터페이스

```bash
python linkedin_scrap_by_user.py --user [사용자ID] --limit [개수] --duration [기간]
```

- `--user`: (필수) 링크드인 사용자 slug
- `--limit`: (선택) 최대 수집 개수 (기본값 0: 무제한)
- `--duration`: (선택) 수집 범위 (예: 3d, 1m, 1y. 숫자만 입력 시 d로 간주)

---

## 4. 상세 구현 로직

### 4.1 기간 해석 (Duration Parsing)

사용자가 입력한 `3m`을 90일로 계산하여 현재 시점으로부터의 기준 날짜(`stop_date`)를 설정합니다. 수집 중 게시글의 날짜가 이 기준보다 이전이면 수집을 중단합니다.

### 4.2 중단 조건 (Stop Conditions)

수집 루프 내에서 다음 조건 중 하나라도 충족되면 `self.stopped_early` 플래그를 활성화합니다:

1. 지정된 `limit` 개수만큼의 게시글이 수집되었을 때
2. 지정된 `duration` 범위를 벗어난 게시글이 발견되었을 때

### 4.3 데이터 추출 (Data Interception)

- `voyager/api/graphql` 요청 중 `feed.Update` 타입과 `EntityResultViewModel` 타입을 모두 감시합니다.
- 사용자의 활동 탭에서는 `feed.Update` 타입이 주로 발생하므로 이에 대한 상세 파싱 로직을 추가합니다.

---

## 5. 테스트 계획

### 5.1 테스트 시나리오

| 케이스             | 입력값            | 기대 결과                                                        |
| ------------------ | ----------------- | ---------------------------------------------------------------- |
| 특정 유저 수집     | `--user gb-jeong` | 해당 사용자의 폴더가 생성되고 게시글이 저장됨                    |
| 개수 제한 테스트   | `--limit 5`       | 정확히 5개 이상의 아이템이 감지되면 수집 프로세스 종료           |
| 증분 업데이트 확인 | 반복 실행         | `update` 폴더에 새 파일이 생기고, `full` 파일에 중복 없이 합쳐짐 |

---

## 6. 예외 처리

- 로그인 필요 시 콘솔에 안내 메시지를 출력하고 사용자 입력을 대기합니다.
- 데이터 로딩이 느릴 경우를 대비하여 `timeout` 및 재시도 로직을 적용합니다.
- 이미지가 없는 텍스트 전용 게시글도 정상적으로 수집하도록 예외를 관리합니다.
