# Plan: Project_Cleanup_and_Legacy_Management

## 1. Overview
- **Feature Name**: 프로젝트 클린업 및 레거시 파일 정리
- **Description**: 루트 디렉토리에 산재된 미사용 스크립트, 임시 데이터, 실험용 폴더를 식별하여 `_backup/` 폴더로 이동시키고 작업 환경을 슬림화함.
- **Priority**: High
- **Status**: Planning

## 2. Goals
- [ ] **루트 디렉토리 슬림화**: 핵심 실행 파일(`total_scrap.py`, `server.py` 등)만 남기고 정리.
- [ ] **구조적 백업**: `_backup/` 하위에 카테고리별(scripts, data, temp) 보관.
- [ ] **의존성 보호**: 정리 과정에서 시스템 작동에 필요한 숨은 의존성 파일 유실 방지.

## 3. Classification Criteria (정리 기준)
### 필수 유지 (Keep)
- `README.md`, `CHANGELOG.md`, `.gitignore`, `package.json`, `pytest.ini`
- `thread_scrap.py`, `linkedin_scrap.py`, `twitter_scrap.py`, `total_scrap.py`, `server.py`
- `utils/`, `tests/`, `web_viewer/`, `output_*/`, `auth/`, `docs/`, `logs/`

### 정리 대상 (Move to _backup/)
- **Test Scripts**: `test_*.py`, `test_runs/`, `codex_sandbox_probe_inside/`
- **Temp Data**: 루트의 `*.json`, `temp_code/`, `temp-code/`, `tmp/`
- **Legacy Utils**: `migrate_schema.py`, `substack_scrap_by_user.py`, `*.vbs`, `*.lnk`
- **Guides**: `guide/` (필요 시 `docs/`로 이동 고려)

## 4. Tasks (Checklist)
- [ ] **Task 1: 의존성 정밀 분석**
  - 핵심 파일의 `import` 문과 `subprocess` 호출 경로 전수 조사.
- [ ] **Task 2: 백업 구조 생성**
  - `_backup/scripts`, `_backup/data`, `_backup/temp` 생성.
- [ ] **Task 3: 파일 이동 및 .gitignore 업데이트**
  - 대상 파일 이동 및 `_backup/` 폴더 ignore 등록.
- [ ] **Task 4: 최종 동작 테스트**
  - `pytest` 및 `total_scrap.py` 실행 확인.

## 5. Success Criteria
- [ ] 루트 디렉토리가 핵심 자산 위주로 정돈됨.
- [ ] 파일 이동 후에도 전체 스크래핑 파이프라인이 정상 작동함.
- [ ] 사용자가 정리된 환경에서 더 빠르게 파일을 식별할 수 있음.
