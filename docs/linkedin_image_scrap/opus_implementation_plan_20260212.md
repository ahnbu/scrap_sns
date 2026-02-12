# LinkedIn 미디어 크롤링 종합 개선

## 배경

사용자가 10개 게시글을 직접 검증한 결과를 반영합니다.
현재 프로젝트는 SNS 게시글을 localhost 웹 뷰어로 모아 보는 구조이며, `web_viewer/images`에 666개의 이미지가 로컬 저장되어 있습니다.

## 사용자 검증 결과 (Ground Truth)

| #   | 작성자           | API 패턴                           | 실제 콘텐츠       | Phase 1 수집 |
| --- | ---------------- | ---------------------------------- | ----------------- | ------------ |
| 1   | SangRok Jung     | `articleshare-shrink_`             | 링크 미리보기     | ❌ 제외      |
| 2   | 정구봉           | 프로필만                           | 텍스트만          | ❌           |
| 3   | **백세명**       | `feedshare-shrink_`                | **이미지**        | ✅ 이미지    |
| 4   | Joongsoo Park    | 프로필만                           | 텍스트만          | ❌           |
| 5   | 티타임즈         | `feedshare-document-cover-images_` | **슬라이드 10장** | ✅ 커버 1장  |
| 6   | **홍민지**       | `feedshare-shrink_`                | **이미지+링크**   | ✅ 이미지    |
| 7   | 정구봉           | 프로필만                           | 링크만            | ❌           |
| 8   | Kyung Jin Jung   | 프로필만                           | 텍스트만          | ❌           |
| 9   | Jeongmin Lee     | `videocover-high/`                 | **동영상**        | ✅ 썸네일    |
| 10  | **Bumgeun Song** | `image-shrink_`                    | **이미지**        | ✅ 이미지    |

---

## Phase 1 — 즉시 구현 (이미지 필터 + 미디어 유형 분류)

### 핵심 변경: 블랙리스트 → 화이트리스트 + content_type 분류

#### [MODIFY] [linkedin_scrap.py](file:///d:/vibe-coding/scrap_sns/linkedin_scrap.py#L313-L339)

```diff
-        # 중복 제거 및 필터링 (프로필 사진 등 제외 시도)
-        # 보통 본문 이미지는 feedshare-shrink 또는 articleshare-shrink 포함
-        final_images = []
-        for img in set(images):
-            if "profile-displayphoto" not in img: # 프로필 사진 제외
-                final_images.append(img)
+        # 화이트리스트: 게시물 미디어 패턴만 수집
+        MEDIA_PATTERNS = [
+            "feedshare-shrink_",              # 일반 이미지 게시글
+            "image-shrink_",                   # 뉴스레터/기사 이미지
+            "feedshare-document-cover-images_", # 슬라이드/PDF 커버
+            "feedshare-document-images_",       # 슬라이드/PDF 이미지
+            "videocover-",                     # 동영상 썸네일
+        ]
+        final_images = []
+        for img in set(images):
+            if any(pattern in img for pattern in MEDIA_PATTERNS):
+                final_images.append(img)
```

content_type 분류 로직도 개선:

```diff
-            "content_type": "carousel" if len(final_images) > 1 else ("image" if final_images else "text"),
+            "content_type": self._classify_content_type(final_images),
```

새 메서드 추가:

```python
def _classify_content_type(self, images):
    """미디어 URL 패턴으로 콘텐츠 유형 분류"""
    if not images:
        return "text"
    for img in images:
        if "videocover-" in img:
            return "video"
        if "feedshare-document" in img:
            return "document"
    return "carousel" if len(images) > 1 else "image"
```

#### [MODIFY] [download_test_images.py](file:///d:/vibe-coding/scrap_sns/download_test_images.py#L50)

동일 화이트리스트 적용.

---

## Phase 1 예상 결과

| #   | 작성자       | 수집                                        | content_type |
| --- | ------------ | ------------------------------------------- | ------------ |
| 3   | 백세명       | `feedshare-shrink_` 이미지 1장              | `image`      |
| 5   | 티타임즈     | `feedshare-document-cover-images_` 커버 1장 | `document`   |
| 6   | 홍민지       | `feedshare-shrink_` 이미지 1장              | `image`      |
| 9   | Jeongmin Lee | `videocover-high` 썸네일 1장                | `video`      |
| 10  | Bumgeun Song | `image-shrink_` 이미지 1장                  | `image`      |

→ 총 **5개** 미디어 (이미지 3 + 슬라이드커버 1 + 영상썸네일 1)

---

## Phase 2 — 향후 고도화 (별도 작업)

> [!NOTE]
> Phase 2는 별도 이슈로 관리합니다. Phase 1 완료 후 진행 여부를 결정합니다.

| 기능                 | 난이도 | 방법                                                                                        |
| -------------------- | ------ | ------------------------------------------------------------------------------------------- |
| 슬라이드 전체 이미지 | 중     | Playwright로 개별 게시글 방문 →`feedshare-document-images_1280` 패턴의 각 슬라이드 URL 추출 |
| 동영상 다운로드      | 상     | `blob:` URL → 별도 미디어 다운로드 로직 필요 (yt-dlp 등)                                    |

---

## Verification Plan

1. `download_test_images.py`로 response.json에서 이미지 추출 테스트
   - **기대 결과**: 5개 미디어 파일 저장
2. `temp-code/analyze_image_accuracy.py`로 정확도 검증
