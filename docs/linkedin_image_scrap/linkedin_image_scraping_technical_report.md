---
title: "링크드인 이미지 스크래핑 기술 분석 및 개선 보고서"
created: "2026-02-12 17:43"
---

# 링크드인 이미지 스크래핑 기술 분석 및 개선 보고서

**작성일**: 2026년 2월 12일
**주제**: 링크드인 Voyager API 기반 이미지 추출 로직의 문제점 진단 및 재귀적 탐색 알고리즘을 통한 해결

## 1. 배경 및 문제점 (Problem Statement)

기존 링크드인 스크래퍼(`linkedin_scrap.py`)는 게시글 수집 시 텍스트 데이터는 정상적으로 가져왔으나, **이미지(media) 데이터가 지속적으로 누락**되는 현상이 발생함.

### 1.1 초기 진단
- 링크드인은 단순한 이미지 URL을 제공하는 대신, 여러 해상도와 포맷을 포함하는 복잡한 **VectorImage** 구조를 사용함.
- 기존 코드는 `entityEmbeddedObject.image`라는 고정된 경로만 탐색했으나, 실제 이미지는 게시글 종류(일반 포스트, 공유 링크, 뉴스레터 등)에 따라 매우 다양한 JSON 경로에 위치함.

## 2. 기술적 분석 (Technical Analysis)

### 2.1 링크드인 이미지 데이터 구조
링크드인 Voyager API(GraphQL) 응답에서 이미지는 주로 `com.linkedin.common.VectorImage` 타입을 가짐.

```json
"vectorImage": {
    "rootUrl": "https://media.licdn.com/dms/image/v2/.../feedshare-shrink_",
    "artifacts": [
        {
            "width": 800,
            "height": 400,
            "fileIdentifyingUrlPathSegment": "800/B56Z.../"
        },
        {
            "width": 2048,
            "height": 1536,
            "fileIdentifyingUrlPathSegment": "2048_1536/B56Z.../"
        }
    ]
}
```

### 2.2 이미지 URL 조립 공식
이미지는 하나의 완성된 URL로 오지 않으며, 에이전트가 다음 공식을 통해 직접 조립해야 함:
- **최종 URL** = `rootUrl` + `fileIdentifyingUrlPathSegment`
- **해상도 선택**: `artifacts` 배열 내에서 `width` 값이 가장 큰 요소를 선택하여 고화질을 확보함.

## 3. 해결 방안: 재귀적 탐색 알고리즘 (Solution)

경로의 가변성을 극복하기 위해 특정 경로를 하드코딩하는 대신, 객체 전체를 훑는 **재귀적 이미지 탐색(Recursive Image Discovery)** 로직을 도입함.

### 3.1 `find_images_recursively` 함수 설계
- **입력**: 게시글 객체(JSON)
- **로직**:
    1. 객체가 딕셔너리인 경우, `$type`이 `VectorImage`이거나 `artifacts` 키가 있는지 확인.
    2. 발견 시, 위 조립 공식에 따라 URL을 생성하고 저장.
    3. 객체가 리스트인 경우, 모든 요소를 재귀적으로 호출.
    4. 딕셔너리의 모든 밸류에 대해 다시 재귀 호출을 수행하여 깊숙이 숨겨진 이미지 경로까지 추적.
    5. **필터링**: 프로필 사진(`profile-displayphoto`) 등 본문과 무관한 이미지는 제외.

### 3.2 수집 정책 변경
- **데이터 업데이트 허용**: 기존에 수집된 데이터가 있더라도 `media` 필드가 비어있다면(`[]`), 이미지가 누락된 것으로 간주하고 새로운 로직을 통해 데이터를 다시 채워 넣도록 업데이트 로직을 보강함.

## 4. 검증 결과 (Verification)

### 4.1 추출 테스트
- **대상**: `docs/linkedin_saved/response.json` (약 8,000줄의 실제 API 응답)
- **결과**: 기존 로직에서 누락되었던 6건 이상의 고화질 이미지 URL을 완벽하게 추출함.
- **다양성**: 일반 이미지뿐만 아니라 아티클 커버, 영상 썸네일 등 모든 형태의 미디어를 수집 가능함을 확인.

### 4.2 로컬 저장 검증
- 추출된 URL을 통해 `docs/linkedin_saved/test_images/` 폴더에 실제 파일을 다운로드하여 이미지가 깨지지 않고 고화질로 저장됨을 최종 확인함.

## 5. 결론 및 향후 계획

이번 개선을 통해 링크드인 데이터 수집의 가장 큰 난제였던 이미지 누락 문제를 해결함. 이 재귀적 탐색 방식은 링크드인뿐만 아니라 유사한 복잡한 구조를 가진 타 플랫폼(예: 트위터의 복잡한 Entities 구조)에도 확장 적용이 가능함.

**향후 계획**:
- 로컬 이미지 저장(`local_images`) 기능을 활성화하여 외부 링크 만료에 대비.
- 수집된 이미지를 기반으로 웹 뷰어의 UI/UX 개선.
