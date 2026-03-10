# LinkedIn 테스트 로케이터 매칭 및 안정화 설계

> Version: 1.0.0 | Created: 2026-03-10 | Status: Draft

## 1. Overview
LinkedIn "Saved Posts" 페이지에서 게시물 목록이 정상적으로 로드되었는지 확인하기 위한 견고한 로케이터를 설계합니다.

## 2. Proposed Locators
LinkedIn의 레이아웃은 동적으로 변할 수 있으므로, 다중 선택자 또는 상위 컨테이너를 활용합니다.

### 2.1. 컨테이너 기반 선택자 (Primary)
- .reusable-search__result-container: 개별 검색 결과/게시물 항목의 공통 클래스
- main .reusable-search__entity-result-list: 목록 전체를 감싸는 UL 요소

### 2.2. 텍스트 기반 선택자 (Secondary)
- utton:has-text("결과 더보기"): 데이터가 로드되어야 나타나는 버튼
- h2:has-text("저장된 게시물"): 페이지 제목 확인용

## 3. Implementation Strategy
	ests/smoke/test_linkedin_smoke.py의 has_posts 판별 로직을 다음과 같이 개선합니다.

`python
# 다중 로케이터를 시도하여 하나라도 발견되면 성공으로 간주
post_selectors = [
    '.reusable-search__entity-result-list',
    '.reusable-search__result-container',
    '.entity-result',
    'article'
]

has_posts = False
for selector in post_selectors:
    if page.locator(selector).count() > 0:
        has_posts = True
        print(f"Found posts with selector: {selector}")
        break
`

## 4. Test Case (Updated)
| Test Case | Method | Expected Result |
|-----------|--------|-----------------|
| 세션 유효성 체크 | page.goto | 로그인 페이지가 아닌 저장된 게시물 페이지 유지 |
| 목록 로딩 체크 | 다중 로케이터 확인 | 게시물 항목(카드)이 1개 이상 존재 |

## 5. Action Items
1. 	ests/smoke/test_linkedin_smoke.py 파일의 로케이터 로직 수정
2. 수동으로 갱신된 uth/auth_linkedin.json을 사용하여 테스트 실행
3. 결과에 따라 가장 안정적인 로케이터를 하나로 고정하거나 다중 선택자 유지
