---
template: design
version: 1.0
description: Substack 아카이브 및 본문 스크래퍼 상세 설계
---

# substack_scraper 설계서

> **요약**: Substack의 아카이브 리스트와 개별 게시글 본문을 체계적으로 수집하기 위한 데이터 구조 및 크롤링 로직을 설계합니다.
>
> **프로젝트**: scrap_sns
> **버전**: 1.0.0
> **작성자**: Gemini CLI
> **날짜**: 2026-02-08
> **상태**: 진행 중

---

## 1. 시스템 아키텍처

### 1.1 저장 구조 (Storage Structure)

```
output_substack/
└── {user_name}/
    ├── substack_{user_name}_full_{YYYYMMDD}.json
    └── update/
        └── substack_{user_name}_update_{YYYYMMDD_HHMMSS}.json
```

### 1.2 데이터 스키마 (Data Schema)

#### Full JSON Object
- `metadata`:
    - `user_id`: Substack 사용자 명 (slug)
    - `total_count`: 전체 게시글 수
    - `crawled_at`: 최종 수집 일시
- `posts`: Array of Post Objects

#### Post Object
- `code`: 게시글 고유 ID (URL 슬러그 활용)
- `title`: 제목
- `subtitle`: 부제목
- `author`: 작성자
- `created_at`: 작성 일시 (ISO 8601)
- `post_url`: 원본 링크
- `body_html`: 본문 HTML (정제됨)
- `images`: Array of Image URLs
- `sequence_id`: 정렬 및 관리용 ID (오름차순 부여)

---

## 2. 상세 설계

### 2.1 아카이브 리스트 수집 (`list.html` 기반)
- **대상**: `div[role="article"]`
- **추출 정보**:
    - 링크: `a[data-testid="post-preview-title"]` 의 `href`
    - 임시 날짜: `time` 태그의 `datetime` 속성

### 2.2 개별 게시글 본문 수집 (`each_article.html` 기반)
- **대상**: `article.post`
- **필드별 Selector**:
    - 제목: `h1.post-title`
    - 부제목: `h3.subtitle`
    - 본문: `.body.markup` (추후 Markdown 변환 고려 가능)
    - 작성일: `.post-header` 영역 내 시간 관련 텍스트 파싱

### 2.3 무한 스크롤 및 네트워크 처리
- **로직**: `window.scrollTo(0, document.body.scrollHeight)` 반복 수행.
- **종료 조건**: 새로운 게시글이 더 이상 발견되지 않거나 사용자가 지정한 제한(limit)에 도달할 때.

---

## 3. 데이터 흐름

1. **초기화**: `USER_ID` 인자 수신 및 마이그레이션 확인 (기존 `python` 폴더 등 확인).
2. **리스트 스캔**: 아카이브 페이지에서 전체 게시글 URL 목록을 먼저 확보.
3. **상세 수집**: 
    - 확보된 URL 중 기존 데이터에 없는 항목만 필터링.
    - 각 URL 순차 방문하여 본문 추출.
4. **정렬 및 ID 부여**:
    - `created_at` 또는 `code` 기준 정렬.
    - `sequence_id` 재할당.
5. **저장**: Full 버전 및 Update 버전 파일 생성.

---

## 4. 예외 처리 및 고려 사항

- **유료 게시글**: "This post is for subscribers" 등 텍스트 감지 시 `is_paid` 플래그 추가 및 수집 가능한 부분까지만 저장.
- **인코딩**: UTF-8 보장.
- **속도 제한**: 각 게시글 방문 사이 1~3초 간격(jitter) 적용하여 차단 방지.

---

## 5. 검증 계획

1. `substack_scrap_by_user.py --user edwardhan99 --limit 3` 실행.
2. `output_substack/edwardhan99/` 폴더 및 파일 생성 확인.
3. 본문 내용이 `body_html` 필드에 정상적으로 담겨 있는지 확인.
