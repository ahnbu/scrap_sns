---
title: "Plan: total_scrap.py vs threads_scrap.py 실행 로직 차이 분석"
created: "2026-02-11 15:16"
---

# Plan: total_scrap.py vs threads_scrap.py 실행 로직 차이 분석

`total_scrap.py`를 통해 실행할 때와 `threads_scrap.py`를 단독 실행할 때 발생하는 동작 차이(특히 데이터 수집 여부 및 처리 방식)의 원인을 분석하고 해결 방안을 수립합니다.

## 1. 현상 분석
`threads_의심로그.md` 분석 결과:
- **`total_scrap.py` 실행 시**: `threads_scrap.py` 실행 -> `scrap_single_post.py` 실행 -> `merge_results` -> `save_total` 순서로 진행됨. 이 과정에서 "Simple에서 20개의 신규 데이터를 Full DB로 가져왔습니다"와 같은 메시지가 출력되며 대량의 데이터 처리가 일어남.
- **`threads_scrap.py` 단독 실행 시**: "수집된 데이터가 없습니다" 메시지와 함께 11초 만에 종료됨.
- **의문점**: `total_scrap.py` 내부에서 `threads_scrap.py`를 호출하는데, 왜 전체 실행 시에는 더 많은 작업(Consumer/Promotion)이 수반되는 것처럼 보이는가?

## 2. 가설 (Hypotheses)
- **가설 1: 호출 구조의 차이**: `total_scrap.py`는 `threads_scrap.py` (Producer) 이후에 `scrap_single_post.py` (Consumer)를 연달아 실행함. 단독 실행 시에는 Consumer 단계가 누락되어 최종 병합이 일어나지 않는 것임.
- **가설 2: 환경 변수 또는 인자 전달**: `total_scrap.py`에서 `subprocess`로 호출할 때 전달되는 인자나 실행 환경(인코딩 등)이 단독 실행과 미세하게 다를 수 있음.
- **가설 3: 데이터 상태 의존성**: `total_scrap.py`는 병합 및 이미지 다운로드(`download_images`) 로직을 포함하고 있어, 단순히 데이터를 수집하는 `threads_scrap.py`보다 결과물이 더 풍부하게 보임.

## 3. 분석 계획
1.  **코드 정밀 분석**: `total_scrap.py`의 `run_scrapers` 함수가 `threads_scrap.py`와 `scrap_single_post.py`를 어떤 순서와 인자로 호출하는지 재확인.
2.  **로그 상세 비교**: 두 실행 방식에서 출력되는 "기준 게시물(Stop Code)" 목록이 일치하는지 확인.
3.  **데이터 흐름 추적**: `threads_scrap.py`가 생성하는 중간 파일(Simple JSON)이 `scrap_single_post.py`에 의해 어떻게 소비되는지 확인.

## 4. 기대 결과
- 두 방식의 실행 로직 차이를 명확히 규명.
- 단독 실행 시에도 전체 프로세스(수집+병합)를 수행하고 싶을 경우의 가이드라인 제시.
- 불필요한 중복 실행이나 데이터 누락 방지.
