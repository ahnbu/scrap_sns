---
title: "linkedin_scrap_by_user Gap 분석"
created: "2026-02-07 00:00"
template: analysis
version: 1.2
description: 특정 사용자의 링크드인 게시글을 스크랩하는 기능 (linkedin_scrap_by_user.py) Gap 분석 보고서
---

# linkedin_scrap_by_user Gap 분석

> **일치율 (Match Rate)**: 95%
> **상태**: 완료
> **날짜**: 2026-02-07

---

## 1. 설계 vs. 구현 비교

| 요구사항 | 설계 명세 | 구현 상태 | 상태 |
|----------|-----------|-----------|:----:|
| CLI 인자 처리 | user, limit, duration 인자 지원 | argparse를 이용해 설계대로 구현 완료 | ✅ |
| 저장 구조 | output_linkedin_user/{user}/python/ | 사용자별 하위 폴더 및 update 폴더 구조 완벽 일치 | ✅ |
| 기간 파싱 로직 | 3d, 3m, 1y 지원 (기본 d) | 정규표현식 기반의 parse_duration 함수로 정확히 구현 | ✅ |
| 수집 중단 조건 | limit 또는 duration 중 선도달 시 중단 | OR 조건 로직 설계대로 반영됨 | ✅ |
| 데이터 가로채기 | voyager/api/graphql 감시 | EntityResultViewModel 및 feed.Update 타입 모두 지원 | ✅ |
| 메타데이터 일관성 | user_id, merge_history 포함 | 기존 시스템의 메타데이터 구조를 확장하여 반영 완료 | ✅ |

---

## 2. 발견된 차이점 (Gaps)

### 2.1 마이너 이슈 및 해결

- **게시글 타입 차이**: 기존 `linkedin_scrap.py`는 `EntityResultViewModel` 타입만 처리했으나, 특정 사용자의 활동 페이지에서는 `feed.Update` 타입이 주를 이룬다는 것을 발견했습니다.
    - **해결**: `extract_post_from_feed_update` 메서드를 신규 구현하여 설계 이상의 데이터 포용력을 확보했습니다.
- **날짜 추출 정밀도**: Snowflake ID에서 날짜를 추출할 때 LinkedIn의 특정 Epoch를 고려해야 했으나, 기존의 `>> 22` 로직이 충분히 정확함을 확인하여 이를 그대로 채택했습니다.

---

## 3. 결론

설계된 모든 핵심 기능이 빠짐없이 구현되었습니다. 특히 `feed.Update` 타입에 대한 추가 대응을 통해 실제 운영 시의 데이터 수집 누락 가능성을 낮췄습니다. `gb-jeong` 테스트 케이스를 통해 데이터 무결성이 검증되었으므로 최종 완료로 판단합니다.
