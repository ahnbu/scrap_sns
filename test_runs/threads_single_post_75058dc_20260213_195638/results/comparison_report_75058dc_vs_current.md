# Threads 단건 수집 비교 리포트 (75058dc 기준)

- 생성시각: 2026-02-13T19:59:47.956750
- 대상 URL 수: 4
- 참조 로직 성공: 4/4, 총 아이템 9건
- 현재 로직 성공: 0/4, 총 아이템 0건

## 타깃별 비교

| target_code | 참조(item/reason) | 현재(item/reason) | 참조만 존재 code 수 |
|---|---:|---:|---:|
| DTochmuDcf7 | 2 / ok | 0 / no_items_extracted | 2 |
| DUm37rRDknp | 3 / ok | 0 / no_items_extracted | 3 |
| DUr86U3Ec1f | 2 / ok | 0 / no_items_extracted | 2 |
| DUrlabpic31 | 2 / ok | 0 / no_items_extracted | 2 |

## 핵심 차이

- 참조(75058dc 계열): `edges`, `containing_thread`, `thread_items` 3경로를 모두 탐색
- 현재(`thread_scrap_single.py`): `data.data.thread_items` 단일 경로에 의존
- 이번 4개 URL에서는 단일 경로에서 아이템이 비어 `no_items_extracted` 발생

## 재현 결과 파일

- 참조 실행 결과: `D:/vibe-coding/scrap_sns/test_runs/threads_single_post_75058dc_20260213_195638/results/scrap_single_post_test_result.json`
- 현재 실행 결과: `D:/vibe-coding/scrap_sns/test_runs/threads_single_post_75058dc_20260213_195638/results/thread_scrap_single_current_logic_result.json`
- 구조화 비교(JSON): `D:/vibe-coding/scrap_sns/test_runs/threads_single_post_75058dc_20260213_195638/results/comparison_report_75058dc_vs_current.json`