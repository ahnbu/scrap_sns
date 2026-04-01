---
title: "threads_sequence_id_improvement Completion Report"
created: "2026-02-13 00:00"
---

# threads_sequence_id_improvement Completion Report

> Version: 1.0.0 | Created: 2026-02-13

## Summary
Threads의 '저장됨' 목록 물리적 순서를 `sequence_id`에 완벽하게 반영하는 개선 작업을 완료했습니다.

## Metrics
- Match Rate: 100%
- Iterations: 1 (Logic fix + NameError fix)
- Duration: < 1 day

## Key Achievements
1. **물리적 순서 고정**: 수집 시 화면에 보이는 순서를 그대로 리스트 인덱스로 확보하여 ID를 부여함으로써, 시간 데이터의 오차에 상관없이 Threads 사이트와 동일한 순서 보장.
2. **Reverse 부여 알고리즘**: 상단(최신) 게시글이 가장 큰 숫자를 갖도록 수집 큐를 뒤집어 번호를 매기는 최적의 로직 적용.
3. **중복 체크 안정성**: 기존 데이터와 신규 데이터 병합 시 순서가 흐트러지지 않도록 Order-preserving deduplication 구현.

## Lessons Learned
- 수집 자동화 시스템에서 '시간'보다 '물리적 노출 순서'가 사용자 경험(UX) 측면에서 더 중요한 기준이 될 수 있음을 확인.

## Next Steps
- 웹 뷰어에서 해당 `sequence_id`를 기준으로 정렬이 잘 되어 나오는지 사용자 최종 확인.
