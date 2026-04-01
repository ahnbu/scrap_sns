---
title: "LinkedIn 미디어 크롤링 필터 개선 Walkthrough"
created: "2026-02-12 18:14"
---

# LinkedIn 미디어 크롤링 필터 개선 Walkthrough

## 변경 사항

### [linkedin_scrap.py](file:///d:/vibe-coding/scrap_sns/linkedin_scrap.py)

1. **화이트리스트 `MEDIA_PATTERNS`** 추가 (클래스 변수)
   - `feedshare-shrink_` — 일반 이미지
   - `image-shrink_` — 뉴스레터 이미지
   - `feedshare-document-cover-images_` / `feedshare-document-images_` — 슬라이드 커버
   - `videocover-` — 동영상 썸네일

2. **`_classify_content_type()` 메서드** 추가 — URL 패턴으로 `video`, `document`, `image`, `carousel`, `text` 분류
3. **필터링 로직**: `profile-displayphoto` 블랙리스트 → `MEDIA_PATTERNS` 화이트리스트

render_diffs(file:///d:/vibe-coding/scrap_sns/linkedin_scrap.py)

### [download_test_images.py](file:///d:/vibe-coding/scrap_sns/download_test_images.py)

동일 `MEDIA_PATTERNS` 적용 + 절대경로 → 상대경로 변경

render_diffs(file:///d:/vibe-coding/scrap_sns/download_test_images.py)

## 검증 결과

기존 7개 → **정확히 5개**로 개선:

| #   | 작성자       | content_type | 수집 패턴                          |
| --- | ------------ | ------------ | ---------------------------------- |
| 3   | 백세명       | `image`      | `feedshare-shrink_`                |
| 5   | 티타임즈     | `document`   | `feedshare-document-cover-images_` |
| 6   | 홍민지       | `image`      | `feedshare-shrink_`                |
| 9   | Jeongmin Lee | `video`      | `videocover-`                      |
| 10  | Bumgeun Song | `image`      | `image-shrink_`                    |

**제외된 항목** (정확히 제외됨):

- `articleshare-shrink_` (링크 미리보기) ❌
- `company-logo_` (회사 로고) ❌
- `profile-displayphoto` (프로필 사진) ❌
