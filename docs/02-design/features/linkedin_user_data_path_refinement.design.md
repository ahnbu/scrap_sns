---
title: "linkedin_user_data_path_refinement 설계서"
created: "2026-02-08 00:00"
template: design
version: 1.0
description: 링크드인 사용자 데이터 저장 경로 및 파일명 규칙 개선 설계
---

# linkedin_user_data_path_refinement 설계서

> **요약**: `linkedin_scrap_by_user.py`의 파일 저장 로직을 수정하여 경로와 파일명 규칙을 최적화합니다.
>
> **프로젝트**: scrap_sns
> **버전**: 1.0.0
> **작성자**: Gemini CLI
> **날짜**: 2026-02-08
> **상태**: 진행 중

---

## 1. 시스템 아키텍처

### 1.1 저장 구조 변경 (Storage Structure)

**이전 (As-Is):**

```
output_linkedin_user/
└── {user_id}/
    └── python/
        ├── linkedin_py_full_20260207.json
        └── update/
            └── linkedin_python_update_20260207_123456.json
```

**변경 (To-Be):**

```
output_linkedin_user/
└── {user_id}/
    ├── linkedin_{user_id}_full_20260208.json
    └── update/
        └── linkedin_{user_id}_update_20260208_123456.json
```

---

## 2. 상세 설계

### 2.1 변수 및 경로 정의 (Paths)

- `USER_DATA_DIR`: `os.path.join(BASE_DATA_DIR, USER_ID)` (기존의 `"python"` 제거)
- `UPDATE_DIR`: `os.path.join(USER_DATA_DIR, "update")` (경로 유지, 상위 경로 변경에 따라 자동 적용)

### 2.2 파일명 규칙 (File Naming Convention)

- **Full Data File**: `f"linkedin_{USER_ID}_full_{date}.json"`
- **Update File**: `f"linkedin_{USER_ID}_update_{timestamp}.json"`

### 2.3 로직 변경점 (Logic Changes)

#### `get_latest_full_file` 메서드

- 검색 패턴 변경: `f.startswith(f"linkedin_{USER_ID}_full_")`

### 2.4 마이그레이션 로직 (Migration Logic)

스크립트 초기화 시(`__init__`) 다음을 수행합니다:

1. **대상 확인**: `output_linkedin_user/{user_id}/python/` 폴더 존재 여부 확인.
2. **파일명 변경 및 이동**:
   - `linkedin_py_full_{date}.json` -> `linkedin_{user_id}_full_{date}.json`
   - `update/linkedin_python_update_{ts}.json` -> `update/linkedin_{user_id}_update_{ts}.json`
3. **폴더 정리**:
   - 파일 이동 완료 후 `python/update` 및 `python` 폴더가 비어있으면 삭제.

#### `save_results` 메서드

- `update_file` 생성 시 `f"linkedin_{USER_ID}_update_{timestamp}.json"` 규칙 적용.

#### `update_full_version` 메서드

- `full_file` 생성 시 `f"linkedin_{USER_ID}_full_{CRAWL_START_TIME.strftime('%Y%m%d')}.json"` 규칙 적용.

---

## 3. 데이터 흐름

1. 사용자가 `--user gb-jeong` 인자로 스크립트 실행.
2. **마이그레이션 수행**: `python/` 폴더 내의 파일들을 상위로 이동 및 이름 변경.
3. `USER_DATA_DIR`이 `output_linkedin_user/gb-jeong/`로 설정됨.
4. `get_latest_full_file`이 새 규칙에 따라 파일을 찾음.
5. 스크래핑 완료 후 새 규칙에 따라 데이터 저장.

---

## 4. 보안 및 예외 처리

- **디렉토리 생성**: `os.makedirs(UPDATE_DIR, exist_ok=True)`를 통해 상위 디렉토리(USER_ID 폴더)까지 안전하게 생성됨을 확인.
- **파일명 안전성**: `USER_ID`에 파일명으로 사용할 수 없는 특수문자가 포함될 가능성을 고려해야 하나, 현재 링크드인 슬러그 구조상 안전함.
- **마이그레이션 안전성**: 파일 이동 시 기존에 동일한 이름의 파일이 이미 존재할 경우 덮어쓰지 않도록 주의하거나(일반적으로 날짜 기반이라 겹치지 않음) 예외 처리를 수행합니다.

---

## 5. 검증 계획

1. `linkedin_scrap_by_user.py` 실행 (예: `python linkedin_scrap_by_user.py --user gb-jeong --limit 1`)
2. 생성된 파일의 경로가 `output_linkedin_user/gb-jeong/` 하위인지 확인.
3. 파일명이 `linkedin_gb-jeong_full_*.json` 인지 확인.
4. 기존에 있던 `python/` 폴더가 삭제되고 파일들이 상위로 이동되었는지 확인.
