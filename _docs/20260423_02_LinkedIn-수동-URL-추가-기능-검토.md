---
title: LinkedIn 수동 URL 추가 기능 검토
created: 2026-04-23 19:57
tags:
  - scrap-sns
session_id: codex:019db9d6-cd50-7c73-b637-aec481004bc4
session_path: C:/Users/ahnbu/.codex/sessions/2026/04/23/rollout-2026-04-23T19-15-55-019db9d6-cd50-7c73-b637-aec481004bc4.jsonl


ai: codex
---

# LinkedIn 수동 URL 추가 기능 검토

## 발단: 사용자 요청

LinkedIn에서 북마크를 눌러도 저장 게시물 목록에 들어가지 않는 사례가 있어, 사용자가 URL을 직접 입력하면 SNS 허브 데이터에 스크랩으로 추가되는 보완 기능을 검토했다.

예시 URL은 `https://www.linkedin.com/posts/...ugcPost-7452699495232008193...` 형태였고, 로컬 최신 LinkedIn/통합 산출물에서 `platform_id=7452699495232008193`가 아직 존재하지 않음을 확인했다.

## 작업 상세내역

확인한 현행 구조:

- LinkedIn 수집기는 저장 목록 페이지의 Voyager GraphQL 응답을 가로채 `utils/linkedin_parser.py`의 `parse_linkedin_post()`로 표준 post를 만든다.
- 서버는 최신 `output_total/total_full_*.json`을 읽어 `/api/posts`, `/api/post/<sequence_id>`, `/api/search`로 제공한다.
- 뷰어 상태는 URL 키 기반으로 `sns_tags.json`, `localStorage`의 즐겨찾기·숨김·접기·TODO 상태와 연결된다.
- `total_scrap.py`는 플랫폼별 full 파일을 다시 병합하면서 `platform_id` 기준으로 중복을 제거하고, 통합 `sequence_id`를 다시 부여한다.

검토 중 사용자와 합의한 UI 방향:

- 헤더의 `업데이트` 버튼에서 텍스트 `업데이트`를 제거하고 sync 아이콘만 남긴다.
- 업데이트 버튼과 Settings 버튼 사이에 `+` 추가 버튼을 둔다.
- `+` 클릭 시 URL 입력 UI가 열리고, LinkedIn URL을 넣으면 단건 스크랩이 반영되는 구조를 지향한다.

## 의사결정 기록

| 선택지 | 장점 | 리스크 | 판단 |
|---|---|---|---|
| 헤더 `+` 버튼 + 단건 LinkedIn URL 추가 | 접근성이 좋고 북마크 누락 대응이 빠름 | 수동 데이터가 일반 북마크 수집 데이터와 섞임 | ✅ 채택 후보 |
| Settings 내부 `URL 추가` 탭 | 예외 기능이라는 성격이 명확함 | 사용자가 자주 쓰기에는 접근이 느림 | 보조 후보 |
| URL placeholder만 저장 | 구현이 가장 쉬움 | 본문·이미지·검색 품질이 낮고 나중에 정본화 비용 발생 | ❌ 제외 |
| Threads/X까지 포함한 범용 수동 추가 | 장기 확장성이 있음 | X 봇 차단, Threads consumer 흐름까지 얽혀 1차 범위가 과함 | ❌ 1차 제외 |

> 정렬 기준: 현재 문제는 LinkedIn 북마크 누락 보완이므로, 사용자가 빠르게 추가할 수 있는지와 기존 데이터 정합성을 동시에 우선했다.

- 결정: 구현은 나중에 진행한다. 이번 세션에서는 검토 내역 문서화와 백로그 등록까지만 수행한다.
- 권장안: 1차 구현은 LinkedIn 전용으로 좁히고, URL은 반드시 `activity_id` 기준으로 정규화한다.
- 트레이드오프: 빠른 수동 보완 경로를 얻는 대신, manual ledger·write lock·canonical URL 정책 같은 데이터 안전장치가 필요하다.

## 실행계획 원문

아래 내용은 linked plan 파일이 아니라 실행 전 TodoList/update_plan을 보존한 것이다.

- completed: 기존 LinkedIn 수집 흐름과 저장 파일 surface가 확인됨
- completed: 뷰어/API에서 URL 입력 기능을 붙일 위치가 확인됨
- completed: 마이그레이션·검증 범위와 권장 적용안이 정리됨

## 검증계획과 실행결과

| 검증 항목 | 검증 방법 | 결과 | 비고 |
|-----------|-----------|------|------|
| URL 정규화 | `/posts/...ugcPost-<id>`와 `/feed/update/urn:li:activity:<id>`가 같은 `platform_id`로 귀결되는지 테스트 | ⏳ 미실행 | 구현 시 신규 unit test 필요 |
| 중복 방지 | 같은 URL 재입력과 다른 URL 형태 재입력 모두 중복 추가되지 않는지 확인 | ⏳ 미실행 | `platform_id` 기준 |
| 수동 데이터 보존 | 전체 재크롤링 후 manual URL 항목이 사라지지 않는지 확인 | ⏳ 미실행 | manual ledger 필요 |
| API 보안 | LinkedIn 외 도메인, `file:`, `localhost`, redirect 악용 입력이 거부되는지 확인 | ⏳ 미실행 | `tests/e2e/test_api_security.py` 확장 |
| 뷰어 회귀 | 태그·즐겨찾기·숨김·TODO 상태가 canonical URL 기준으로 유지되는지 확인 | ⏳ 미실행 | Playwright 또는 JS unit test |

## 리스크 및 미해결 이슈

- 전체 재크롤링 손실: LinkedIn `all` 모드가 저장 목록 기반으로 full 파일을 재구성하면, 저장 목록에 없는 수동 추가 글이 사라질 수 있다. `manual_linkedin_urls.json` 같은 별도 ledger가 필요하다.
- 중복 감지 노이즈: LinkedIn은 같은 글도 `/posts/...ugcPost-<id>`, `/feed/update/urn:li:activity:<id>`, query 포함 URL 등으로 달라진다. URL 문자열이 아니라 `activity_id`로 중복 감지해야 한다.
- 상태 키 분리: 뷰어의 태그·즐겨찾기·숨김·접기·TODO가 URL 키에 묶여 있다. 수동 URL과 정규 수집 URL이 달라지면 같은 글의 상태가 분리된다.
- 동시 쓰기 위험: `/api/run-scrap` 실행 중 수동 URL 추가가 동시에 `output_linkedin` 또는 `output_total`을 쓰면 최신 결과가 덮이거나 누락될 수 있다. 서버 write lock이 필요하다.
- 입력 보안: 새 API가 사용자 입력 URL을 인증 세션으로 열게 되므로 LinkedIn 도메인 allowlist와 scheme 검증이 필요하다.
- 실패 처리: LinkedIn 인증 만료, 삭제/비공개 게시물, GraphQL 응답 미발생 시 사용자에게 실패 원인을 구분해서 보여줘야 한다.

## 다음 액션

- 백로그 항목 `BL-0423-01`로 보류 등록한다.
- 구현 착수 시 먼저 `activity_id` 추출 유틸과 manual ledger 설계를 확정한다.
- 그 다음 `POST /api/manual-scrap` API, 헤더 `+` 버튼 UI, 중복/보안/전체 재크롤링 보존 테스트를 순서대로 추가한다.

## 참고 자료

| 출처 | 용도 |
|------|------|
| [[development|SNS Crawler 개발 기준]] | 영구화 surface와 표준 post 스키마 확인 |
| [[crawling_logic|SNS Crawler 크롤링 로직]] | LinkedIn 수집·병합·뷰어 연동 흐름 확인 |
| `linkedin_scrap.py` | LinkedIn 저장 목록 GraphQL 수집 흐름 확인 |
| `utils/linkedin_parser.py` | LinkedIn post 파싱 필드 확인 |
| `total_scrap.py` | 플랫폼별 full 병합과 중복 제거 기준 확인 |
| `server.py` | `/api/run-scrap`, `/api/posts`, `/api/post/<sequence_id>` API surface 확인 |
| `web_viewer/script.js`, `index.html` | 헤더 버튼 위치와 URL 기반 UI 상태 저장 방식 확인 |
