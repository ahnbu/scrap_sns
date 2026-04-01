---
title: "linkedin_scrap_order_analysis 원인 진단 및 개선 설계서"
created: "2026-02-08 00:00"
template: design
version: 1.0
description: 링크드인 사용자 게시글 수집 순서 혼선 원인 진단 및 개선 설계
---

# linkedin_scrap_order_analysis 원인 진단 및 개선 설계서

> **요약**: 링크드인 API의 응답 구조와 현재 스크립트의 데이터 처리 방식 간의 차이로 인해 발생하는 순서 혼선 문제를 진단하고, 시간 기반 정렬을 통한 해결 방안을 제시합니다.
>
> **프로젝트**: scrap_sns
> **버전**: 1.0.0
> **작성자**: Gemini CLI
> **날짜**: 2026-02-08
> **상태**: 진행 중

---

## 1. 원인 진단 (Diagnosis)

### 1.1 JSON 구조적 특징 (`included` 배열 처리)
LinkedIn의 GraphQL 응답에서 실제 게시글 데이터는 `included`라는 평탄화된(Flattened) 배열에 담겨 옵니다. 
- 이 배열은 정규화된 객체들의 집합일 뿐이며, **배열 내 객체들의 인덱스 순서가 실제 피드의 시간 순서를 보장하지 않습니다.**
- 현재 코드는 `included` 배열을 처음부터 끝까지 순회하며 발견되는 즉시 `self.posts.append()` 하므로, API가 객체를 배열에 담은 임의의 순서대로 저장됩니다.

### 1.2 네트워크 비동기성 (Asynchronous Responses)
Playwright의 `page.on("response")`는 네트워크 응답이 도착하는 순서대로 이벤트를 발생시킵니다.
- 페이지 스크롤 시 발생하는 여러 번의 GraphQL 요청이 비동기적으로 완료될 경우, 나중에 요청한(더 과거의 데이터) 응답이 먼저 처리될 가능성이 미세하게 존재합니다.

### 1.3 LinkedIn 피드 로직 (Pinned or Algorithm)
- 사용자의 활동 피드 최상단에 '고정된 게시물(Pinned Post)'이 있을 경우, 이 게시물은 실제 작성 시간과 관계없이 가장 먼저 응답에 포함될 수 있습니다.

---

## 2. 개선 방안 (Improvement Plan)

### 2.1 스노우플레이크 ID (Snowflake ID) 기반 정렬
링크드인의 게시글 `code`(activity ID)는 Snowflake ID 구조를 따르며, 상위 비트에 생성 타임스탬프 정보를 포함하고 있습니다.
- **방안**: 수집이 완료된 직후(`save_results` 호출 시), `self.posts` 전체를 `code` 필드(숫자형 변환 후)를 기준으로 **내림차순(최신순) 정렬**한 뒤 `sequence_id`를 부여해야 합니다.

### 2.2 수집 데이터와 기존 데이터의 통합 정렬
현재 `update_full_version`에서 기존 데이터와 새 데이터를 병합할 때 단순히 `new_items + old_posts`를 수행하고 있습니다.
- **방안**: 병합 후 최종 리스트를 다시 한번 `code` 또는 `sequence_id` 기준으로 정렬하여 전체 무결성을 확보해야 합니다.

### 2.3 데이터 수집 시점의 정렬 vs 저장 시점의 정렬
- **결론**: 수집 중에는 실시간으로 정렬할 필요가 없습니다. 모든 네트워크 처리가 끝난 후, 파일을 디스크에 쓰기 직전에 한 번의 `sort()` 과정을 거치는 것이 성능과 로직 단순화 측면에서 유리합니다.

---

## 3. 상세 설계 가이드 (Conceptual)

1.  **데이터 정렬 단계 추가**: `save_results()` 메서드 시작 부분에서 `self.posts.sort(key=lambda x: x['code'], reverse=True)` 로직 배치.
2.  **ID 부여 시점 조정**: 정렬이 완료된 리스트를 대상으로 순차적인 `sequence_id` 부여.
3.  **날짜 추출 필드 활용**: `created_at` 필드가 존재하므로, `code` 정렬이 불안정할 경우 `created_at` 문자열을 기준으로 정렬 가능 (단, `code`가 더 정밀함).

---

## 4. 기대 효과

- 사용자는 항상 최신글부터 과거글 순으로 정렬된 JSON 데이터를 얻을 수 있음.
- `sequence_id`가 실제 시간 흐름과 일치하게 되어 데이터 분석 시 직관성이 높아짐.
- 데이터 병합 시 발생하는 순서 뒤섞임 문제를 근본적으로 해결.
