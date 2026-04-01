---
title: "[Plan] TODO 관리 기능 구현 (순환 토글 방식)"
created: "2026-02-12 11:13"
---

# [Plan] TODO 관리 기능 구현 (순환 토글 방식)

## 1. 개요
사용자가 게시물을 할 일(TODO)로 관리할 수 있도록 순환 토글 방식의 인터페이스를 구현합니다. 하나의 아이콘으로 상태를 전환하며, 전용 필터를 통해 효율적인 업무/정보 처리를 돕습니다.

## 2. 조사 결과 및 분석
- **선택된 방식**: 옵션 1 (순환 토글)
- **상태 정의**:
    1. **Normal (None)**: 기본 상태. 할 일로 지정되지 않음.
    2. **Pending (Todo)**: 할 일로 지정됨. 아직 처리 전. (아이콘: `pending`, 색상: 주황색)
    3. **Completed (Done)**: 할 일 완료. (아이콘: `task_alt`, 색상: 초록색)
- **필터링 요구사항**: 상단 필터 바에 체크 아이콘을 추가하여 TODO(Pending/Completed) 항목만 모아보기 기능 제공.

## 3. 해결 방안 (Proposed Solution)

### 3.1. 카드 내 토글 인터페이스
- 위치: 카드 우측 상단 즐겨찾기(별) 아이콘 왼쪽.
- 동작: 클릭 시 `None -> Pending -> Completed -> None` 순서로 상태와 아이콘이 실시간 변경.
- 데이터 저장: `localStorage`의 `sns_todos` 키에 `{ "url": "pending" | "completed" }` 형태로 저장.

### 3.2. 상단 필터 바 확장
- 위치: 즐겨찾기 필터 버튼 오른쪽.
- 아이콘: `assignment_turned_in`.
- 동작: 클릭 시 `currentFilter`를 `todos`로 설정하고, Pending 또는 Completed 상태인 게시물만 렌더링.

### 3.3. 시각적 피드백
- 완료(Completed) 상태인 카드는 본문 텍스트의 투명도를 낮추거나 제목에 취소선을 긋는 등의 시각적 처리 검토 (선택 사항).

## 4. 상세 계획 (Tasks)
1. [x] UX 옵션 결정 (옵션 1: 순환 토글).
2. [ ] `web_viewer/style.css`: TODO 상태별 아이콘 클래스 및 애니메이션 정의.
3. [ ] `web_viewer/index.html`: 상단 필터 바에 TODO 필터 버튼 추가.
4. [ ] `web_viewer/script.js`:
    - [ ] `sns_todos` 로컬 스토리지 연동 로직 구현.
    - [ ] `createCard` 함수 내에 TODO 토글 버튼 생성 및 이벤트 바인딩.
    - [ ] `getFilteredPosts` 함수에 `todos` 필터링 로직 추가.
5. [ ] 검증: 상태 전환 시 로컬 스토리지 반영 확인 및 필터링 기능 테스트.

## 5. 기대 효과
- 최소한의 UI 변경으로 강력한 업무 관리 기능 제공.
- 정보 과부하 상황에서 중요한 게시물을 필터링하고 처리 상태를 추적 가능.
