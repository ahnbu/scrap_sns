# SNS Crawler 프로젝트 개발 및 인수인계 가이드

이 문서는 Threads 및 LinkedIn 저장물 크롤러의 데이터 추출 규칙과 기술적 세부 사항을 정리한 문서입니다. 프로젝트 유지보수 및 인수인계 시 참고하시기 바랍니다.

---

## 1. LinkedIn 크롤링 및 데이터 추출 규칙

LinkedIn은 Voyager GraphQL API를 사용하며, 복잡한 데이터 구조를 가지고 있습니다.

### 🔍 데이터 소스

- **엔드포인트**: `voyager/api/graphql` (Search SRP 응답)
- **추출 대상**: `included` 배열 내 `$type`이 `com.linkedin.voyager.dash.search.EntityResultViewModel`인 객체

### 🛠️ 필드 매핑 및 변환 로직

1.  **작성 일자 (Snowflake ID 디코딩)**
    - LinkedIn은 `taken_at` 필드가 없으므로 `entityUrn`의 숫자 ID를 디코딩하여 절대 시간을 추출합니다.
    - **로직**: `(ID_int >> 22) + LinkedIn_Epoch_MS`
    - **우선순위**: 디코딩된 절대 시간 > `time_text` 감지 및 역산 > 크롤링 시점(`crawled_at`)
2.  **상대적 시간 역산 (`time_text`)**
    - "1주", "3일", "5시간" 등의 텍스트를 정규식으로 분석하여 크롤링 시점으로부터 `timedelta`를 계산해 절대 시간으로 변환 후 저장합니다.
3.  **이미지 수집**
    - `image.attributes` 배열의 `detail` 정보를 활용합니다.
    - `rootUrl` 뒤에 `artifacts` 배열 중 가장 큰 해상도의 `fileIdentifyingUrlPathSegment`를 붙여 완성합니다.
    - **Fallback**: `imageUrl.url` 필드 직접 참조.

---

## 2. Threads 크롤링 및 데이터 추출 규칙

Threads는 비교적 직관적인 JSON 구조를 가지며, 절대 타임스탬프를 제공합니다.

### 🔍 데이터 소스

- **루트 경로**: `data.xdt_text_app_viewer.saved_media.edges`
- **개별 객체**: `node.thread_items[0].post`

### 🛠️ 필드 매핑 및 변환 로직

1.  **작성 일자 (`taken_at`)**
    - **필드**: `post.taken_at` (Unix Timestamp, 초 단위)
    - **변환**: Python의 `datetime.fromtimestamp()`를 사용하여 즉시 절대 시간으로 변환합니다.
2.  **이미지 및 캐러셀**
    - **단일 이미지**: `post.image_versions2.candidates[0].url`
    - **캐러셀 (여러 장)**: `post.carousel_media` 배열을 순회하며 각 아이템의 `image_versions2.candidates[0].url`을 수집합니다.
3.  **원본 링크 생성**
    - **공식**: `https://www.threads.net/t/{post.code}` (여기서 `code`는 게시물 고유 코드)

---

## 3. 공통 데이터 구조 (Output JSON)

모든 크롤러는 최종적으로 다음 규격의 JSON 객체를 생성해야 합니다.

```json
{
  "code": "게시물 고유 ID (activity_id 또는 pk)",
  "username": "작성자 이름",
  "text": "본문 텍스트",
  "created_at": "YYYY-MM-DD HH:MM:SS (절대 시간)",
  "crawled_at": "YYYY-MM-DD HH:MM:SS (수집 시점)",
  "time_text": "YYYY-MM-DD (역산된 절대 시간 문자열)",
  "images": ["url1", "url2"],
  "post_url": "원본 게시물 링크"
}
```

---

## 4. 주의 사항 및 유지보수

- **세션 관리**: LinkedIn은 쿠키 세션이 만료될 경우 크롤링이 중단되므로 수동 로그인이 주기적으로 필요할 수 있습니다.
- **날짜 정확도**: `time_text` 역산은 크롤러 실행 시점에 따라 오차(최대 1일)가 발생할 수 있으므로, 항상 Snowflake ID 디코딩 결과를 최우선으로 신뢰합니다.
- **Selector 변경**: SNS 플랫폼의 UI 업데이트로 인해 CSS Selector나 JSON 경로가 변경될 수 있으므로, 응답이 비어있을 경우 `docs` 폴더의 최신 `response.json`을 재분석하십시오.
