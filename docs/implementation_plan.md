# 태그 분류 기능 구현 계획

태그에 "중요(Primary)" 속성을 부여하여 시각적으로 강조하고, 이를 관리할 수 있는 설정 UI를 추가합니다.

## Proposed Changes

### [web_viewer]

#### [MODIFY] [style.css](file:///d:/vibe-coding/scrap_sns/web_viewer/style.css)

- `.tag-primary` 스타일 추가: 배경색 강조 (예: primary color), 보더 스타일 변경, 텍스트 강조 등.
- `.tag-basic` 스타일 명시 (기존 스타일 유지).

#### [MODIFY] [index.html](file:///d:/vibe-coding/scrap_sns/index.html)

- `managementModal` 내의 `tab-navigation`에 "태그 관리" 탭 추가.
- `tab-pane` 섹션에 태그 목록 및 타입 토글 UI 추가.

#### [MODIFY] [script.js](file:///d:/vibe-coding/scrap_sns/web_viewer/script.js)

- `sns_tag_types` 로컬 스토리지 데이터 로드/저장 로직 추가.
- 설정 모달 내 태그 관리 탭 렌더링 함수 `renderTagManagementList()` 구현.
- `renderTags()` 함수 수정: 태그 렌더링 시 `tagTypes`를 참조하여 적절한 CSS 클래스 적용.
- 탭 전환 로직에 새 탭 추가.

## Verification Plan

### Automated Tests

- 없음 (현재 프로젝트에 자동화 테스트 프레임워크가 명시되지 않음)

### Manual Verification

1. 설정 아이콘 클릭 -> "태그 관리" 탭 선택.
2. 현재 사용 중인 태그 목록이 정상적으로 표시되는지 확인.
3. 특정 태그의 타입을 "Primary"로 변경.
4. 게시물 피드에서 해당 태그가 강조된 스타일로 표시되는지 확인.
5. 페이지 새로고침 후 설정이 유지되는지 확인.
