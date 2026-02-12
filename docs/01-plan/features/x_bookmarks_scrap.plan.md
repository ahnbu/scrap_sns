# Plan: X(Twitter) 저장 게시글(Bookmarks) 크롤링 및 타래글 통합

X의 북마크 API 및 HTML 구조를 분석하여, 저장된 게시글과 그에 딸린 타래글들을 체계적으로 수집하고 `total_scrap.py`에 통합하는 계획을 수립합니다.

## 1. 분석 결과 요약
- **데이터 소스**: X Bookmarks GraphQL API (`Bookmarks?variables=...`)
- **주요 데이터 경로**:
    - 텍스트: `result.note_tweet.note_tweet_results.result.text` (긴 글) 또는 `result.legacy.full_text`
    - 미디어: `result.legacy.entities.media` (이미지 URL 등)
    - 고유 ID: `rest_id` 및 `conversation_id_str`
- **타래글 처리 이슈**: 북마크 API는 저장된 특정 트윗만 반환함. Threads와 유사하게 `conversation_id_str`을 활용하여 대화 전체를 추출하는 로직이 필요함.

## 2. 단계별 접근 전략

### 단계 1: X 북마크 기본 크롤러 구현 (`twitter_scrap.py`)
- `docs/twitter_saved/fetch.js`의 헤더 정보를 활용하여 API 요청 구현.
- 북마크 목록을 순회하며 기본 정보(작성자, 본문, 이미지, 작성일, URL) 추출.
- 중복 수집 방지를 위한 `rest_id` 기반 필터링.

### 단계 2: 타래글(Thread) 수집 로직 강화
- 수집된 각 트윗의 `conversation_id_str` 확인.
- 동일한 `conversation_id_str`을 가진 트윗들을 그룹화하거나, 필요한 경우 추가 API(`TweetDetail`)를 호출하여 타래 전체 수집.
- Threads 수집 로직과 유사하게 본문들을 순서대로 결합하여 하나의 컨텐츠로 구성.

### 단계 3: `total_scrap.py` 통합 및 데이터 정규화
- `total_scrap.py`의 `PLATFORMS` 설정에 `twitter` 추가.
- 수집된 데이터를 프로젝트 표준 JSON 형식으로 변환.
- `web_viewer`에서 X 아이콘 및 스타일이 적용되도록 `sns_platform` 값 지정.

## 3. 상세 Task 리스트
- [ ] `twitter_scrap.py` 신규 생성 (북마크 API 연동)
- [ ] 타래글 감지 및 병합 로직 구현
- [ ] 이미지/동영상 미디어 URL 추출 및 처리 (CORS 대응 wsrv.nl 적용)
- [ ] `total_scrap.py` 연동 및 통합 테스트
- [ ] `web_viewer` UI 반영 확인 (아이콘 및 플랫폼별 스타일)

## 4. 검토 및 고려사항
- **인증 만료**: `fetch.js`의 쿠키 및 토큰은 만료될 수 있으므로, 세션 갱신 방법 고려 필요.
- **API 제한**: X API의 Rate Limit에 대응하기 위한 지연 시간(sleep) 설정.
- **데이터 구조 변화**: GraphQL 특성상 필드명이 자주 변경될 수 있으므로 예외 처리 강화.
