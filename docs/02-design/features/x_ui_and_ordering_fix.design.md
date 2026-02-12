# Design: SNS 통합 아카이브 스키마 표준화 및 데이터 정규화

이 문서는 Threads, LinkedIn, X(Twitter)의 데이터를 동일한 구조로 통일하고, 전역 정렬 순서를 바로잡기 위한 상세 설계 내용을 담고 있습니다.

## 1. 표준 데이터 스키마 (Standard Schema v1.0)
모든 플랫폼 데이터는 수집 단계에서부터 아래의 필드명으로 정규화됩니다.

- `id`: (String) 플랫폼별 고유 식별자
- `user`: (String) 사용자 아이디 (@handle)
- `display_name`: (String) 사용자 이름
- `full_text`: (String) 게시글 전체 본문 내용
- `media`: (Array) 이미지 및 동영상 URL 리스트
- `timestamp`: (String) YYYY-MM-DD HH:MM:SS 형식의 작성 일시
- `date`: (String) YYYY-MM-DD 형식의 작성 날짜
- `url`: (String) 원본 게시물 주소
- `sns_platform`: (String) 'threads', 'linkedin', 'x' 중 하나
- `sequence_id`: (Integer) 전역 날짜순 정렬 순번

## 2. 컴포넌트별 변경 설계

### 2.1 스크래퍼 (Scrapers)
- **공통**: 각 스크래퍼의 데이터 추출 결과물(JSON) 형식을 위 표준 스키마로 즉시 변경.
- **Twitter**: `body` 필드를 `full_text`로 변경.
- **Threads**: `body` -> `full_text`, `images` -> `media` 변경.
- **LinkedIn**: 기존 필드들을 표준에 맞춰 맵핑.

### 2.2 통합 엔진 (total_scrap.py)
- **병합 로직**: `full_text` 필드를 기본 본문으로 인식.
- **ID 정규화**: 
    - 이번 일괄 수정을 위해 `reorder_all_by_date()` 함수 구현.
    - 기존 `sequence_id`를 모두 초기화하고, 전체 데이터를 `timestamp` 오름차순으로 정렬 후 1번부터 재할당.
    - 이를 통해 신규 추가된 X 데이터가 과거 타임라인 사이에 자연스럽게 배치됨.

### 2.3 프론트엔드 (Web Viewer)
- **필터 바**: 파란색 트위터 아이콘을 검은색 배경의 'X' 아이콘(폰트 또는 SVG)으로 교체.
- **카드 렌더링**: `item.body` 참조를 `item.full_text`로 전면 교체.
- **플랫폼 설정**: `platformConfig` 내 `twitter` 키를 `x`로 통합 관리.

## 3. 마이그레이션 전략
1. 각 스크래퍼 수정 및 개별 플랫폼 `full` 파일 재생성.
2. `total_scrap.py`를 통해 전역 정렬 및 ID 재부여 실행.
3. `web_viewer` 코드 수정 및 결과 확인.
