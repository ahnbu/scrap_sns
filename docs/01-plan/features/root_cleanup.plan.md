# Plan: Root Directory Cleanup & Dependency Verification

루트 디렉토리의 불필요한 파일들을 `tmp` 폴더로 이동하기 전, 메인 기능과의 의존성을 철저히 검증하고 안전하게 정리합니다.

## 1. 목적
- 루트 디렉토리의 가독성 향상
- 의도치 않은 기능 중단(Breaking Changes) 방지
- 유지보수 효율성 증대

## 2. 의존성 검토 결과 (Verification Results)
사전 조사(`grep`, `read_file`) 결과:
- **`total_scrap.py`**: `threads_scrap.py`, `scrap_single_post.py`, `linkedin_scrap.py`를 직접 호출함. 정리 대상 파일들에 대한 직접적인 호출은 발견되지 않음.
- **`server.py`**: `total_scrap.py`를 호출하며, `web_viewer/sns_tags.json` 등을 관리함. 정리 대상 파일들과의 연관성 없음.
- **기타 스크립트**: 정리 대상 파일들(`cleanup_*.py`, `test_*.py` 등)은 과거 데이터 가공이나 실험용으로 작성된 독립적인 유틸리티로 판단됨.

## 3. 정리 대상 파일 및 이동 경로 (Target Files)
다음 파일들을 `tmp/` 디렉토리로 이동합니다:
- **Substack 정리 유틸**: `cleanup_substack_data.py`, `cleanup_substack_final.py`, `cleanup_substack_to_text.py`
- **Threads/LinkedIn 보정**: `cleanup_threads_history.py`, `fix_linkedin_full.py`, `update_threads_urls.py`
- **실험 및 임시 스크립트**: `merge_and_update.py`, `simple_threads_finder.js`, `temp_cleaned_sample.html`, `temp_merge_script.py`
- **테스트 파일**: `test_cleanup.py`, `test_conversion.json`, `test_conversion.md`

## 4. 유지 파일 (Keep Files) - 프로젝트 핵심
- **메인 실행**: `total_scrap.py`, `server.py`, `run_viewer.bat`, `stop_viewer.bat`
- **SNS별 크롤러**: `linkedin_scrap.py`, `linkedin_scrap_by_user.py`, `scrap_single_post.py`, `substack_scrap_by_user.py`, `threads_scrap.py`
- **설정 및 문서**: `.env.*`, `.gitignore`, `package*.json`, `README.md`, `task.md`, `tailwind.config.cjs`, `favicon.png`, `index.html`, `execute_invisible.vbs`

## 5. 실행 단계 (Action Plan)
1. **백업**: `tmp` 디렉토리가 존재하는지 확인 (없으면 생성).
2. **이동**: `run_shell_command`를 사용하여 대상 파일들을 `tmp/`로 이동. (Windows `move` 명령 사용)
3. **검증**: `total_scrap.py`를 실행하여 정리 후에도 메인 크롤링 프로세스가 정상 작동하는지 확인.
4. **보고**: 정리된 결과 목록 출력.
