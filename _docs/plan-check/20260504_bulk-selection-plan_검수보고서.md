# bulk-selection-plan 검수보고서

검수일: 2026-05-04 KST

## 총평

계획은 목적을 달성할 가능성이 높다. 다만 현재 계획 그대로 구현하면 선택 상태의 범위, 일괄 복사 순서, TODO legacy 처리, 테스트 단위가 애매해서 UI 오작동과 회귀가 생길 수 있다.

## 크리티컬 피드백

1. 선택 상태를 필터·검색 변경 후에도 유지한다는 방침은 위험하다.
   - 얻는 것: 검색과 필터를 오가며 여러 글을 누적 선택할 수 있다.
   - 잃는 것: 화면에 보이지 않는 글까지 숨기기·별표·복사가 적용될 수 있다.
   - 개선안: 선택은 메모리 상태로 유지하되, 검색어 변경·필터 변경·정렬 변경·새 데이터 로드 시 초기화한다. 같은 렌더링 안에서 lazy-load로 카드가 다시 그려지는 정도만 유지한다.

2. 일괄 복사 순서가 정의되지 않았다.
   - 선택 Set의 삽입 순서, 현재 화면 순서, 전체 데이터 순서가 서로 다를 수 있다.
   - 개선안: 복사 순서는 현재 `sortPosts(getFilteredPosts())` 결과의 화면 순서를 따른다. 선택된 URL 중 현재 화면 결과에 없는 항목은 작업 대상에서 제외한다.

3. 일괄 액션이 URL만 들고 있으면 post 객체 조회 규칙이 누락된다.
   - `ensurePostDetail(post)`와 `buildCopyText(post)`는 post 객체가 필요하다.
   - 개선안: `getVisibleSelectedPosts()` 헬퍼를 만들고, 내부에서 현재 필터·정렬 결과 중 `selectedPosts.has(resolvePostUrl(post))`인 post만 반환한다.

4. TODO 제거 범위가 과하면 legacy URL 마이그레이션 회귀가 생긴다.
   - 현재 `sns_todos`는 localStorage에서 로드되고, legacy URL 마이그레이션 대상에도 포함된다.
   - 개선안: 카드의 TODO UI와 클릭 로직은 제거하되, `todos` 로드와 `migrateLegacyTagKeys()` 내부의 `sns_todos` 마이그레이션은 보존한다. TODO 필터 버튼은 제거한다.

5. 테스트 계획이 DOM 이벤트와 순수 로직을 구분하지 않는다.
   - 현재 unit test들은 `script.js`에서 함수를 추출해 Node로 검증하는 패턴을 쓴다.
   - 개선안: DOM 의존이 낮은 순수 헬퍼를 먼저 추가한다. 예: `getVisibleSelectedPosts(posts, selectedUrls)`, `buildBulkCopyText(posts)`, `addSelectedUrlsToFavorites(favorites, selectedUrls)`, `addSelectedUrlsToHidden(invisiblePosts, selectedUrls)`.

6. UI 배치 계획은 맞지만 sticky header와의 관계를 명확히 해야 한다.
   - 현재 header는 sticky이며, global tags는 header 밖에 있다.
   - 개선안: bulk action bar는 `globalTagsContainer` 바로 위에 두되 `hidden` 상태가 기본이다. 선택 시 `max-w-[1800px]` 폭을 맞춰 나타나게 하고, sticky까지는 적용하지 않는다. sticky 적용은 시야 유지 장점은 있지만 header와 겹칠 가능성이 있어 1차 범위에서는 제외한다.

## 코드베이스 검증 결과

- `web_viewer/script.js:128-133`: `sns_favorites`, `sns_invisible_posts`, `sns_folded_posts`, `sns_todos`가 localStorage 상태로 로드된다. 따라서 새 선택 상태는 저장하지 않는 메모리 Set으로 두는 계획이 적절하다.
- `web_viewer/script.js:1628-1640`: `getFilteredPosts()`가 현재 필터·태그·숨김 상태를 적용한다. 일괄 액션 대상은 이 결과를 기준으로 잡아야 화면 밖 선택 오작동을 줄일 수 있다.
- `web_viewer/script.js:1644-1667`: `resolvePostUrl(post)`가 URL canonical 기준이다. 선택 key도 이 함수 결과를 사용해야 한다.
- `web_viewer/script.js:1669-1675`: `buildCopyText(post)`가 단일 게시글 복사 포맷을 이미 제공한다. 일괄 복사는 이 함수를 재사용해 구분자만 추가하면 된다.
- `web_viewer/script.js:1770-1797`: `renderPosts()`가 masonry 전체를 다시 만든다. 선택 UI는 렌더링마다 `selectedPosts.has(postUrl)`로 재동기화해야 한다.
- `web_viewer/script.js:1876-1914`: 기존 TODO 버튼 렌더링과 상태 순환 로직이 있다. 이 구간이 선택 버튼으로 대체될 핵심 지점이다.
- `web_viewer/script.js:1950-1973`: 개별 복사는 `ensurePostDetail(post)` 후 `buildCopyText()`를 호출한다. 일괄 복사도 상세 본문 누락 방지를 위해 같은 흐름을 반복해야 한다.
- `web_viewer/script.js:1975-1990`: 개별 숨기기는 confirm 후 `sns_invisible_posts`에 저장한다. 일괄 숨기기는 confirm을 게시글마다 띄우지 말고 1회만 띄워야 한다.
- `index.html:96-105`: TODO 필터 버튼이 실제 UI에 존재한다. 선택 기능 전환 시 이 버튼은 제거 대상이다.
- `index.html:301-307`: global tags 영역이 header 아래에 있다. bulk action bar 삽입 위치로 적합하다.
- `web_viewer/style.css:195-215`: `.todo-btn` 스타일이 TODO 전용이다. `.select-btn` 스타일과 `.glass-card.selected` 스타일로 대체해야 한다.
- `tests/unit/test_web_viewer_copy_string.py:20-110`: 기존 테스트가 `resolvePostUrl`, `buildCopyText`를 함수 추출 방식으로 검증한다. 일괄 복사 헬퍼 테스트도 같은 패턴을 따르는 것이 좋다.
- `tests/unit/test_web_viewer_auto_tagging.py:197-233`: `sns_todos` 마이그레이션 검증이 있다. TODO 데이터를 무조건 제거하면 이 테스트와 legacy 보존 요구가 깨진다.

## 개선된 구현계획

1. `index.html`에서 TODO 필터 버튼을 제거하고, `globalTagsContainer` 위에 숨김 상태의 `bulkActionBar`를 추가한다.
2. `web_viewer/script.js` 상단 상태에 `const selectedPosts = new Set();`을 추가한다.
3. 순수 헬퍼를 추가한다.
   - `getVisibleSelectedPosts(posts, selectedUrls)`
   - `buildBulkCopyText(posts)`
   - `addSelectedUrlsToSet(targetSet, selectedUrls)`
   - `clearSelection()`
4. 검색어 변경, 필터 변경, 정렬 변경, 데이터 재로드 완료 시 `clearSelection()`을 호출한다.
5. 카드 렌더링에서 `todo-btn`을 `select-btn`으로 바꾸고, 선택 상태에 따라 `check_circle`/`radio_button_unchecked`와 `glass-card selected` 상태를 반영한다.
6. 기존 TODO 클릭 로직은 제거한다. 단, `todos` 로드와 `sns_todos` legacy migration은 유지한다.
7. bulk action bar 이벤트를 추가한다.
   - 별표 추가: 현재 화면 선택 post URL을 `favorites`에 추가하고 localStorage 저장
   - 숨기기: 확인창 1회 후 `invisiblePosts`에 추가하고 localStorage 저장
   - 복사: 현재 화면 선택 post를 상세 로드한 뒤 `buildBulkCopyText()` 결과를 클립보드에 기록
   - 선택 해제: `clearSelection()`
8. 단위 테스트를 추가한다.
   - 선택 post 필터링이 현재 화면 순서를 보존하는지
   - 일괄 복사가 `---` 구분자로 단일 복사 포맷을 합치는지
   - 일괄 별표가 기존 별표를 제거하지 않는지
   - 일괄 숨기기가 선택 URL을 누락 없이 추가하는지
9. 기존 회귀 테스트를 실행한다.
   - `pytest tests/unit/test_web_viewer_copy_string.py`
   - `pytest tests/unit/test_web_viewer_resolve_post_url.py`
   - `pytest tests/unit/test_web_viewer_auto_tagging.py`
   - `pytest tests/unit/test_web_viewer_bulk_selection.py`
   - `node utils/query-sns.mjs --help`

## 결론

기존 계획은 구현 방향은 맞지만, 선택 상태를 넓게 유지하려는 부분이 가장 큰 리스크다. 1차 구현은 “현재 화면에서 선택한 글만 일괄 처리”로 제한하는 편이 안전하다. 이후 실제 사용에서 필터 간 누적 선택이 필요하다는 근거가 생기면 별도 기능으로 확장하는 것이 낫다.
