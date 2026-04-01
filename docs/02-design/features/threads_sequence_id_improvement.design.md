---
title: "threads_sequence_id_improvement Design Document"
created: "2026-02-13 00:00"
---

# threads_sequence_id_improvement Design Document

> Version: 1.0.0 | Created: 2026-02-13 | Status: Draft

## 1. Overview
수집된 리스트의 인덱스를 활용하여 Threads의 물리적 저장 순서를 `sequence_id`에 박제하는 로직 설계입니다.

## 2. Architecture: Sequence Assignment Logic

### Step 1: Sequential Collection
- `collected_data` 리스트에 `append` 되는 순서는 Threads 웹사이트 상단 → 하단 순서임.
- 이 순서를 그대로 유지하며 중복을 제거함.

### Step 2: Order-Preserving Merge
```python
# 기존: dictionary에 무작위로 담기
# 개선: 리스트의 순서를 유지하며 중복 제거
seen = set()
ordered_new_list = []
for post in raw_collected_list:
    pid = post['platform_id']
    if pid not in seen:
        ordered_new_list.append(post)
        seen.add(pid)
```

### Step 3: Reverse & Increment
- `ordered_new_list.reverse()` 를 수행하여 [가장 오래전 저장] → [가장 최근 저장] 순으로 변경.
- 순차적으로 `max_sequence_id + 1` 부여.

## 3. Test Plan
1. `total_scrap.py` 실행 시 로그에 찍히는 순서 확인.
2. 생성된 `threads_py_simple_*.json`의 `sequence_id`가 역순(숫자 큰 것이 위)으로 정렬되었을 때 로그 순서와 일치하는지 대조.
