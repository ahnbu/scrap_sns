---
title: "[Design] TODO 관리 기능 구현 (순환 토글 방식)"
created: "2026-02-12 11:17"
---

# [Design] TODO 관리 기능 구현 (순환 토글 방식)

## 1. 개요
순환 토글 방식의 TODO 관리 시스템을 위한 상세 설계를 정의합니다.

## 2. 상세 설계 사항

### 2.1. 시각적 스타일링 (`web_viewer/style.css`)
- **TODO 버튼 (`.todo-btn`)**:
    - 기본: `opacity-40`, 호버 시 `opacity-100`.
    - Pending 상태: 색상 `#f97316` (주황색), `opacity-100`.
    - Completed 상태: 색상 `#22c55e` (초록색), `opacity-100`.
- **필터 아이콘**: 기존 `filter-chip` 스타일을 따르되, 활성화 시 주황색/초록색 조합 고려.

### 2.2. HTML 구조 확장 (`index.html`)
- **필터 바**:
    ```html
    <button data-filter="todos" class="filter-chip flex items-center justify-center size-10 rounded-full bg-surface-glass hover:bg-surface-glass-hover text-gray-300 hover:text-white border border-border-glass transition-all whitespace-nowrap group" title="TODO 리스트">
      <span class="material-symbols-outlined text-[18px] text-orange-400">assignment_turned_in</span>
    </button>
    ```

### 2.3. 로직 구현 (`web_viewer/script.js`)

#### 2.3.1. 데이터 초기화
- `const todos = JSON.parse(localStorage.getItem('sns_todos') || '{}');`

#### 2.3.2. 상태 순환 로직
```javascript
function toggleTodo(url) {
    const currentState = todos[url]; // undefined (normal), 'pending', 'completed'
    if (!currentState) {
        todos[url] = 'pending';
    } else if (currentState === 'pending') {
        todos[url] = 'completed';
    } else {
        delete todos[url];
    }
    localStorage.setItem('sns_todos', JSON.stringify(todos));
}
```

#### 2.3.3. 카드 렌더링 (`createCard`)
- 즐겨찾기 버튼 왼쪽에 `todo-btn` 삽입.
- `todos[url]` 값에 따라 아이콘 종류와 클래스 결정.
  - `undefined`: `add_task`
  - `pending`: `pending`
  - `completed`: `task_alt`

#### 2.3.4. 필터링 로직 (`getFilteredPosts`)
- `currentFilter === 'todos'` 일 경우: `todos[url]` 값이 존재하는 항목만 필터링.

## 3. 검증 시나리오
1. 카드 우측 상단 체크 아이콘 클릭 -> 주황색(`Pending`)으로 변경 확인.
2. 한 번 더 클릭 -> 초록색(`Completed`)으로 변경 확인.
3. 한 번 더 클릭 -> 기본 상태로 복구 확인.
4. 상단 TODO 필터 버튼 클릭 -> TODO로 지정된 항목만 리스트에 남는지 확인.
5. 페이지 새로고침 시 TODO 상태가 유지되는지 확인.
