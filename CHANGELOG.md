# 변경 사항 (2026-02-01)

## 1. 데이터 스키마 통일 (Standardization)

- **LinkedIn (`linkedin_scrap.py`)**:
  - `date` → `created_at` (Format: `YYYY-MM-DD HH:MM:SS`)
  - `collected_at` → `crawled_at`
  - `content_type` 필드 추가 (image, carousel, text 판단)
- **Threads (`threads_scrap.py`)**:
  - `user_link` 필드 추가 (작성자 프로필 URL)
  - `content_type` 필드 추가 (text, image, video, carousel)
  - 이미지 해상도 추출 로직 개선 (가장 높은 해상도 선택)
  - 캐러셀(Carousel) 미디어 수집 로직 추가

## 2. 버그 수정 (Bug Fixes)

- **LinkedIn Update Mode**: `CRAWL_MODE` 변수값 불일치("update" vs "update only")로 인해 전체 스크랩이 발생하던 문제 수정.
- **Optimization**: 기존 데이터 발견 시 즉시 스크롤 및 수집을 중단하는 조기 종료(Early Stop) 로직 추가 (`stopped_early` 플래그 사용).

이제 두 플랫폼의 데이터는 `created_at`, `crawled_at`, `user_link`, `content_type` 등 공통된 필드를 갖게 되어 통합 분석이 용이해졌으며, 업데이트 모드가 정상적으로 작동합니다.
