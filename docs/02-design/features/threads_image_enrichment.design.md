---
title: "threads_image_enrichment Design Document"
created: "2026-02-12 00:00"
---

# threads_image_enrichment Design Document

> **Summary**: 쓰레드 게시물의 누락된 이미지를 1회성 전체 재스크래핑을 통해 보강함.
>
> **Project**: scrap_sns
> **Version**: 1.0.0
> **Author**: Gemini CLI Agent
> **Date**: 2026-02-12
> **Status**: Draft
> **Planning Doc**: [threads_image_enrichment.plan.md](../01-plan/features/threads_image_enrichment.plan.md)

---

## 1. Overview

### 1.1 Design Goals

- `thread_scrap.py`에 `--enrich` 파라미터를 추가하여 1회성 전체 수집 모드 지원.
- 수집 과정에서 동일한 `code`(platform_id)를 가진 게시물이 이미 존재하더라도, `media` 필드가 비어있다면 새로운 이미지 URL로 보강.
- 기존 데이터 파일과의 병합 과정에서 데이터 손실 없이 이미지 정보만 정밀하게 업데이트.

### 1.2 Design Principles

- **Idempotency**: 여러 번 실행해도 동일한 데이터 상태를 유지하며, 이미지가 있는 경우 덮어쓰지 않음 (또는 더 나은 데이터로 교체).
- **Non-destructive**: 기존의 텍스트, 날짜, 좋아요 수 등의 메타데이터는 유지.
- **Efficiency**: 이미 이미지가 충분한 게시물은 수집 로직에서 우선순위를 낮출 수 있으나, 이번 1회성 작업에서는 전체 탐색을 원칙으로 함.

---

## 2. Architecture

### 2.1 Data Flow

1. **Execution**: `python thread_scrap.py --enrich` 실행.
2. **Load Existing**: 최신 `output_threads/python/threads_py_full_*.json` 로드 (선택 사항, 또는 수집 후 병합 시 처리).
3. **Scraping**:
    - DOM 및 Network 이벤트를 통해 게시물 정보 수집.
    - `media` 리스트가 비어있지 않은지 확인.
4. **Smart Merge**:
    - `collected_data`에 추가 시:
        ```python
        existing_post = find_by_code(collected_data, new_post['code'])
        if existing_post:
            if not existing_post['media'] and new_post['media']:
                existing_post['media'] = new_post['media']
                existing_post['source'] += "+enriched"
        else:
            collected_data.append(new_post)
        ```
5. **Persistence**: 결과를 새로운 JSON 파일로 저장.

---

## 3. Data Model

### 3.1 Entity Definition (Threads Post)

기존 스키마를 유지하되 `media` 필드 업데이트에 집중함.

```typescript
interface ThreadsPost {
  platform_id: string;   // 'code' 필드와 매핑
  username: string;
  full_text: string;
  media: string[];       // 이번 설계의 핵심 보강 대상
  created_at: string;
  sns_platform: "threads";
  source: string;        // 'initial_dom', 'network', 'enriched' 등
}
```

---

## 4. Implementation Details

### 4.1 CLI Argument

`argparse`를 사용하여 `--enrich` 플래그 추가.
```python
parser.add_argument('--enrich', action='store_true', help='Enrich missing images by re-scanning all posts')
```

### 4.2 Merge Logic Enhancement

`thread_scrap.py` 내의 중복 체크 로직 수정:
- 기존: `if any(p['code'] == code for p in collected_data): continue`
- 변경: 
    - 만약 `enrich` 모드라면, 기존 항목을 찾아 `media`가 비어있는지 확인 후 업데이트.
    - `media`가 이미 있다면 `continue`.

---

## 5. Test Plan

### 5.1 Test Cases

- **Case 1: 이미지 누락 게시물 보강**
    - `media: []`인 게시물이 스캔될 때, 이미지가 발견되면 `media: ["http..."]`로 업데이트되는지 확인.
- **Case 2: 기존 이미지 유지**
    - `media: ["url1"]`인 게시물이 다시 스캔될 때, 기존 이미지가 유지되거나 중복되지 않게 병합되는지 확인.
- **Case 3: 중복 방지**
    - 이미지 정보가 동일한 경우 `collected_data`에 중복 추가되지 않는지 확인.

---

## 6. Next Steps

1. [ ] `thread_scrap.py` 코드 수정 (argparse 및 merge 로직)
2. [ ] 소량 테스트 데이터로 검증 실행
3. [ ] 전체 데이터 대상 실행 및 `total_scrap.py` 연동 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-12 | Initial design for image enrichment | Gemini CLI Agent |
