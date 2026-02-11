# Plan: LinkedIn Scraper Mode Fix & Performance Optimization

LinkedIn 스크래퍼가 `update` 모드임에도 불구하고 `all` 모드로 작동하는 버그를 수정하고, 전체적인 실행 속도를 개선합니다.

## 1. 문제 분석 (Root Cause)
`linkedin_scrap.py`의 코드를 분석한 결과:
- **하드코딩된 변수**: 25행에서 `CRAWL_MODE = "all"`로 하드코딩되어 있습니다. `--mode update` 인자를 받아도 이 변수가 덮어쓰여 실질적으로 항상 `all` 모드로 작동합니다.
- **주석처리된 올바른 로직**: 24행에 올바른 로직(`CRAWL_MODE = "update only" if args.mode == "update" else "all"`)이 주석처리되어 있습니다.
- **조기 종료 로직 미작동**: `CRAWL_MODE`가 `all`로 고정되어 있어, 기존 게시물을 발견해도 수집을 중단하지 않고 끝까지 스크롤하여 성능 저하가 발생합니다.

## 2. 해결 방안
- **모드 변수 수정**: 하드코딩된 `CRAWL_MODE = "all"`을 제거하고, 명령행 인자(`args.mode`)를 따르도록 복구합니다.
- **비교 로직 정합성**: `CRAWL_MODE` 값과 조건문(`"update only"` vs `"update"`)의 문자열 일치 여부를 확인하여 조기 종료(`stopped_early`)가 정상 작동하도록 합니다.

## 3. 실행 단계
1. `linkedin_scrap.py` 파일의 `CRAWL_MODE` 설정 부분을 수정합니다.
2. `total_scrap.py`를 실행하여 LinkedIn이 기존 데이터를 발견했을 때 즉시 중단되는지 확인합니다.
3. 소요 시간을 비교하여 성능 개선을 검증합니다.

## 4. 기대 결과
- LinkedIn 수집 시 이미 수집된 게시물을 발견하면 즉시 중단 (최신 게시물만 수집).
- 전체 스크래핑 시간 대폭 단축.
- `update` 모드 인자의 정상 작동 보장.
