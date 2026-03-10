# [Design] 공통 유틸리티 통합 및 플랫폼 특화 로직 보존 설계

> **상태**: 작성 완료
> **목표**: 중복 코드 제거 및 플랫폼별(Twitter, Threads, LinkedIn) 미세 로직 보존

## 1. 개요
현재 6개 이상의 파일에 흩어진 `clean_text`, `reorder_post`, `load_json`, `save_json` 등을 `utils/common.py`로 통합한다. 이때 각 플랫폼이 가진 고유한 텍스트 처리 방식과 데이터 순서를 훼손하지 않도록 '플랫폼 분기 로직'을 공통 함수 내부에 포함한다.

## 2. 핵심 함수 설계

### 2.1 `clean_text(text, platform=None, **kwargs)`
기존의 파편화된 로직을 `platform` 파라미터로 통합한다.

| 플랫폼 | 특화 로직 (보존 대상) |
| :--- | :--- |
| **Common** | 기본 공백 제거, 연속 줄바꿈 정규화 |
| **Threads** | `username` 첫 줄 제거, `AI Threads`/`수정됨` 등 메타데이터 필터링 |
| **Twitter** | `\n`을 공백(` `)으로 대체 (기존 twitter_scrap.py 로직 준수) |
| **LinkedIn** | `…더보기` UI 텍스트 제거, 탭/공백 정규화 |

### 2.2 `reorder_post(post)`
표준 필드 순서를 정의하되, 특정 플랫폼 전용 필드도 유연하게 수용한다.
- **표준 순서**: `sequence_id`, `platform_id`, `sns_platform`, `username`, `full_text`, `media`, `url`, `created_at`, `date`, `crawled_at`
- **플랫폼 전용**: `code` (Threads), `urn` (LinkedIn), `display_name` (Twitter)

### 2.3 JSON 입출력 (`load_json`, `save_json`)
- 모든 파일에서 `utf-8-sig` 인코딩과 `ensure_ascii=False`를 강제하여 한글 깨짐 방지 및 정합성 유지.

## 3. 트레이드오프 및 리스크 관리
- **과도한 추상화 위험**: `clean_text`가 너무 복잡해지면 성능 저하나 예기치 못한 필터링이 발생할 수 있음.
  - **대응**: 플랫폼별 단위 테스트(`tests/unit/test_common.py`)를 작성하여 리팩터링 전후의 결과값이 동일한지 검증.
- **기능 상실**: 특히 Twitter의 줄바꿈 제거 로직은 뷰어 가독성에 영향을 주므로 절대 누락 금지.

## 4. 작업 단계 (Implementation Steps)
1. `utils/common.py` 고도화 (플랫폼 분기 로직 추가)
2. `tests/unit/test_common.py` 작성 및 기존 로직과의 동일성 검증
3. 각 스크래퍼 파일에서 로컬 정의 삭제 및 `import` 교체
   - `thread_scrap.py`
   - `twitter_scrap.py`
   - `linkedin_scrap.py`
   - `total_scrap.py`
   - `thread_scrap_single.py`
   - `twitter_scrap_single.py`
