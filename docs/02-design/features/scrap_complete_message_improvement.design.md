---
title: "[Design] 스크랩 완료 메시지 고도화 및 데이터 통계 제공 설계"
created: "2026-02-11 14:43"
---

# [Design] 스크랩 완료 메시지 고도화 및 데이터 통계 제공 설계

## 1. 데이터 구조 변경

### 1.1. `total_full_*.json` 메타데이터 확장
`total_scrap.py`의 `save_total` 함수에서 생성하는 `total_data["metadata"]` 객체에 다음 필드를 추가합니다.
```json
{
    "metadata": {
        ...
        "new_items_count": 10,
        "new_threads_count": 6,
        "new_linkedin_count": 4,
        ...
    }
}
```

## 2. 컴포넌트별 설계

### 2.1. `total_scrap.py` (Python)
- `save_total` 함수 내에서 `new_items` 리스트를 순회하며 `sns_platform` 필드에 따라 카운트 수행.
```python
new_threads = sum(1 for p in new_items if p.get('sns_platform') == 'threads')
new_linkedin = sum(1 for p in new_items if p.get('sns_platform') == 'linkedin')
```

### 2.2. `server.py` (Flask)
- `run_scrap()` 함수에서 `subprocess.run` 성공 시, `get_latest_data()` 로직을 활용해 방금 생성된 파일의 메타데이터를 로드.
- 응답 JSON에 `stats` 필드 추가:
```json
{
    "status": "success",
    "stats": {
        "total": 10,
        "threads": 6,
        "linkedin": 4
    }
}
```

### 2.3. `web_viewer/script.js` (JavaScript)
- `fetch('http://localhost:5000/api/run-scrap', ...)`의 결과를 처리하는 부분 수정.
```javascript
if (result.status === 'success') {
    const stats = result.stats;
    const msg = `총 ${stats.total}건이 추가되었습니다. 데이터를 새로고침합니다.

쓰레드 - ${stats.threads}건 추가
링크드인 - ${stats.linkedin}건 추가`;
    alert(msg);
    fetchData();
}
```

## 3. 예외 처리
- `new_items`가 0건인 경우에도 "0건 추가되었습니다"라고 명시적으로 표시.
- 메타데이터 로드 실패 시 기존의 기본 메시지로 폴백(Fallback).
