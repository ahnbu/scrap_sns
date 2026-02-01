# LinkedIn 데이터 무결성 분석 보고서

**날짜**: 2026년 2월 1일
**대상 파일**: `response.json`, `linkedin_saved.html`

## 1. 개요

LinkedIn 저장된 게시물 데이터(`response.json`)와 페이지 소스(`linkedin_saved.html`)를 분석하여 누락된 이미지 URL과 게시물 생성 날짜(Creation Date)의 위치를 파악했습니다.

## 2. 분석 결과

### A. 이미지 URL (`response.json`)

이미지 데이터는 `response.json`의 `included` 배열 내 `EntityResultViewModel` 객체에 깊게 중첩되어 있습니다.

- **위치**: `included` 배열의 항목 중 `entityEmbeddedObject` 필드가 있는 객체.
- **JSON 경로**:
  ```json
  element.entityEmbeddedObject.image.attributes[0].detailData.imageUrl.url
  ```
- **특이사항**:
  - 모든 게시물에 이미지가 있는 것은 아니며, `image` 필드가 `null`인 경우도 존재합니다.
  - `originalImageUrl`이 아닌 `imageUrl.url` 필드에 실제 접근 가능한 URL이 포함된 경우가 많습니다.

### B. 생성 날짜 (Creation Date)

`response.json` 내에서 명시적인 Unix Timestamp(예: `created_at`, `postedAt`) 필드는 발견되지 않았습니다. 날짜 정보는 두 가지 형태로 추정됩니다.

1.  **상대적 시간 문자열 (표시용)**:
    - **위치**: `EntityResultViewModel` -> `secondarySubtitle` -> `text`
    - **예시**: `"1주 • "` (1주 전 게시됨 의미)
    - **한계**: 정확한 날짜가 아닌 "1주 전", "3일 전" 등의 상대적 시간만 제공됩니다.

2.  **URN ID 기반 추정 (절대적 시간)**:
    - **위치**: `urn:li:activity:[ID]` (예: `urn:li:activity:7411204617524391938`)
    - **가능성**: LinkedIn의 Activity ID는 시간 기반(Flake ID 등)으로 구성되는 경우가 많아, ID를 디코딩하면 정확한 생성 시간을 추출할 수 있을 가능성이 높습니다. (추가 검증 필요)

### C. HTML 소스 (`linkedin_saved.html`)

`linkedin_saved.html` 파일은 애플리케이션의 초기 실행 껍데기(Shell) 역할만 수행하며, 실제 저장된 게시물 데이터 목록은 포함하고 있지 않습니다. 데이터는 `response.json`과 같은 API 응답을 통해 동적으로 로드됩니다.

## 3. 결론 및 제안

- **데이터 소스**: 누락된 데이터 추출을 위해서는 `linkedin_saved.html`이 아닌 **`response.json`**을 파싱해야 합니다.
- **이미지 추출**: 위에서 파악된 JSON 경로를 통해 이미지 URL을 추출할 수 있습니다.
- **날짜 확보**:
  1.  간단한 방법: `secondarySubtitle`의 텍스트("1주")를 파싱하여 대략적인 날짜를 계산.
  2.  정확한 방법: Activity URN의 ID 부분을 추출하여 타임스탬프로 변환하는 로직 구현 연구 필요.
