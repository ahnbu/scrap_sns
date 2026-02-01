# Threads 저장물 JSON 데이터 분석 리포트 (2026-02-01)

제공해주신 `docs/thread_saved_html/response.json` 파일을 분석한 결과, Threads의 데이터를 정확하게 추출하기 위한 매핑 정보는 다음과 같습니다.

## 1. 데이터 추출 경로 (Extraction Path)

- **루트 경로**: `data.xdt_text_app_viewer.saved_media.edges` (배열)
- **개별 게시물**: 각 `edge` 내부의 `node.thread_items[0].post`

## 2. 주요 필드 매핑

| 항목            | JSON 필드 경로       | 비고                                    |
| :-------------- | :------------------- | :-------------------------------------- |
| **고유 ID**     | `post.pk`            | 시스템 내부 고유 번호 (문자열)          |
| **작성자**      | `post.user.username` | 예: "guuu.dev"                          |
| **본문**        | `post.caption.text`  | 줄바꿈(`\n`)이 포함된 원문 텍스트       |
| **작성 시간**   | `post.taken_at`      | **절대 시간 (Unix Timestamp, 초 단위)** |
| **게시물 코드** | `post.code`          | URL 생성용 (예: threads.net/t/[code])   |
| **미디어 타입** | `post.media_type`    | 1: 이미지, 8: 캐러셀(여러 장)           |

## 3. 핵심 분석 결과

### ✅ 절대 시간 정보 (`taken_at`)

- LinkedIn과 달리 Threads는 JSON 안에 `taken_at`이라는 이름으로 **Unix 타임스탬프(초 단위)**가 포함되어 있습니다.
- **예시**: `1769770448`
- **변환 결과**: 이 숫자는 Python의 `datetime.fromtimestamp()`를 사용하면 즉시 **YYYY-MM-DD HH:MM:SS** 형태의 절대 시간으로 변환됩니다. 따라서 별도의 역산 로직이 필요 없습니다.

### 🖼️ 이미지 추출 로직

- **단일 이미지**: `post.image_versions2.candidates[0].url`
- **캐러셀 (여러 장)**: `post.carousel_media` 배열을 순회하며 각 객체의 `image_versions2.candidates[0].url`을 수집하면 됩니다.

### 🔗 URL 생성

- `https://www.threads.net/t/{post.code}` 형식을 사용하면 게시물 원문 링크를 정확히 생성할 수 있습니다.

---

## 4. 다음 단계 제안

이 분석 결과를 바탕으로 `threads_scrap.py` 또는 `simple_threads_finder.js`를 수정하여 **정확한 절대 시간**과 **이미지/캐러셀**을 수집하도록 업데이트할 준비가 되었습니다. 진행할까요?
