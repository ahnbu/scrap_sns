# Design: Project_Cleanup_and_Legacy_Management

## 1. Overview
- **Feature Name**: 프로젝트 클린업 및 레거시 파일 정리
- **Plan Reference**: `docs/01-plan/features/project_cleanup.plan.md`
- **Status**: Design

## 2. Backup Architecture
정리된 파일들을 안전하게 보관하기 위해 `_backup_20260310/` 디렉토리를 최상위에 생성하고 다음과 같이 분류합니다.

### 2.1 Directory Structure
- `_backup_20260310/scripts/`: 보조 스크래퍼 및 유틸리티
- `_backup_20260310/tests_legacy/`: 구버전/실험용 테스트 코드
- `_backup_20260310/data_archive/`: 과거 JSON 결과물 및 로그
- `_backup_20260310/temp_archive/`: 산재된 임시 폴더 통합
- `_backup_20260310/docs_guides/`: 이전 문서 및 가이드 자료

## 3. Migration Mapping Table

| Source (Original) | Target Category | Reason |
|:---|:---|:---|
| `download_test_images.py` | `tests_legacy/` | 테스트용 유틸리티 |
| `linkedin_scrap_by_user.py` | `scripts/` | 비정기 수집기 |
| `migrate_schema.py` | `scripts/` | 마이그레이션 완료됨 |
| `substack_scrap_by_user.py` | `scripts/` | 사용 빈도 낮음 |
| `temp_migrate_linkedin.py` | `scripts/` | 임시 작업용 |
| `test_linkedin_image.py` | `tests_legacy/` | 실험용 테스트 |
| `test_logic_refinement.py` | `tests_legacy/` | 실험용 테스트 |
| `pending_list.json` | `data_archive/` | 상태 데이터 |
| `scrap_failures_*.json` | `data_archive/` | 과거 에러 로그 |
| `twitter_py_*_20260212.json` | `data_archive/` | 과거 산출물 |
| `SNS허브_바로가기.lnk` | `scripts/` | 불필요한 바로가기 |
| `execute_invisible.vbs` | `scripts/` | 특수 목적 스크립트 |
| `codex_sandbox_probe_inside/` | `temp_archive/` | 실험용 폴더 |
| `guide/` | `docs_guides/` | docs/ 로의 통합 대상 |
| `temp_code/`, `temp-code/`, `tmp/` | `temp_archive/` | 중복된 임시 폴더 |
| `test_runs/` | `temp_archive/` | 실행 이력 |

## 4. Implementation Strategy (Do Phase)

### 4.1 Step-by-Step Execution
1. **의존성 검증**: 핵심 파일(`total_scrap.py`, `server.py`)에서 위 파일들을 참조하는지 `grep` 검색.
2. **백업 폴더 생성**: `mkdir -p` 명령어로 계층 구조 생성.
3. **파일 이동**: `mv` 명령어로 이동 수행.
4. **Git Ignore 업데이트**: `_backup_*/` 패턴을 `.gitignore`에 추가.

### 4.2 Recovery Plan
- 모든 이동 작업은 `move_and_log.py`와 같은 스크립트를 통해 기록을 남기며 수행함.
- 문제 발생 시 로그 파일을 기반으로 `undo` 기능 수행 가능하도록 설계.

## 5. Verification Plan (Check Phase)
- **런타임 검증**: `python total_scrap.py --help` 실행 및 `server.py` 구동 테스트.
- **테스트 검증**: `pytest tests/` 실행 (레거시 테스트 제외 후에도 정상 작동 확인).
- **구조 검증**: 루트 디렉토리의 파일 목록이 설계와 일치하는지 확인.
