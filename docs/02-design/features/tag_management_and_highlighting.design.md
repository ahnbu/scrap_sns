---
title: "[Design] 태그 관리 및 강조 표시 기능 구현"
created: "2026-02-12 11:04"
---

# [Design] 태그 관리 및 강조 표시 기능 구현

## 1. 개요
웹 뷰어에서 사용자가 태그의 중요도(Primary/Basic)를 직접 설정하고, 중요 태그는 시각적으로 강조하여 피드 내 가독성을 높입니다. 설정 모달 내에 새로운 '태그 관리' 탭을 추가하여 이를 구현합니다.

## 2. 세부 설계 사항

### 2.1. 시각적 스타일링 (`web_viewer/style.css`)
- **강조 스타일 (`.tag-primary`)**:
    - 배경색: `#7f0df2` (Primary Color)
    - 텍스트 색상: `white`
    - 보더: `1px solid rgba(127, 13, 242, 0.5)`
    - 호버 시: `#6a0bc9` (약간 어두운 보라색)
- **기본 스타일 (`.tag-basic`)**:
    - 기존 `.tag-chip` 스타일을 그대로 유지하거나 명시적으로 정의.
- **태그 관리 UI 스타일**:
    - 태그 관리 리스트 아이템 스타일 (그리드 형태 또는 리스트 형태).
    - 타입 토글 스위치/버튼 디자인.

### 2.2. HTML 구조 확장 (`web_viewer/index.html`)
- **탭 메뉴 추가**:
    - `#managementModal` 내의 `tab-navigation`에 `data-target="tabTags"` 버튼 추가.
- **컨텐츠 영역 추가**:
    - `#managementModal` 내의 `tab-content`에 `id="tabTags"` 섹션 추가.
    - 태그 목록을 렌더링할 `id="tagManagementList"` 컨테이너 포함.
    - 검색 필드(태그 필터용) 및 일괄 설정 버튼(선택 사항) 고려.

### 2.3. 로직 구현 (`web_viewer/script.js`)
- **데이터 구조**:
    - `localStorage` 키: `sns_tag_types`
    - 형식: `{ "태그명": "primary" | "basic" }`
- **핵심 함수**:
    - `loadTagTypes()`: 로컬 스토리지에서 태그 타입 데이터를 불러옴.
    - `saveTagType(tagName, type)`: 특정 태그의 타입을 저장.
    - `renderTagManagementList()`: 설정 모달의 태그 관리 탭 내용을 렌더링.
    - `renderTags(container, url)`: 기존 함수 수정. `sns_tag_types`를 참조하여 `.tag-primary` 또는 `.tag-basic` 클래스 적용.
    - `updateGlobalTags()`: 전역 태그 클라우드에서도 강조 표시 적용.
- **이벤트 핸들러**:
    - 탭 전환 시 `renderTagManagementList()` 호출.
    - 태그 타입 토글 클릭 시 데이터 업데이트 및 피드 재렌더링.

## 3. UI/UX 상세
- **태그 관리 탭**:
    - 현재 시스템에 존재하는 모든 고유 태그 목록을 가나다순/사용 빈도순으로 정렬하여 표시.
    - 각 태그 우측에 "강조(Primary)" 토글 스위치 배치.
    - 태그가 많은 경우를 대비해 스크롤바 지원.

## 4. 검증 시나리오
1. 설정 -> 태그 관리 탭 이동.
2. 특정 태그(예: 'AI')의 토글을 활성화.
3. 피드로 돌아와 해당 태그가 보라색 배경으로 강조되어 표시되는지 확인.
4. 새로고침 후에도 설정이 유지되는지 확인.
