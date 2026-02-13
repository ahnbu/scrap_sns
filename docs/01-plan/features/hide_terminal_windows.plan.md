# PDCA 계획: total_scrap.py 실행 시 생성되는 터미널 창 숨김 처리

## 1. 개요 (Overview)
- **대상**: `total_scrap.py`
- **문제**: `total_scrap.py` 실행 시 3개(Threads, X/Twitter, LinkedIn)의 스크래퍼가 각각 새로운 터미널 창(Console)을 생성하여 화면을 점유함.
- **목표**: 터미널 창을 화면 밖(예: Y=5000)으로 배치하거나 숨김 처리하여 사용자 작업에 방해가 되지 않도록 함.

## 2. 현재 상황 및 가설 (Current Status & Hypotheses)
### 2.1. 현상 분석
- `subprocess.Popen`을 사용하며 `creationflags=0x00000010` (CREATE_NEW_CONSOLE)을 사용하여 새 창을 띄움.
- 사용자 요청에 따라 창을 완전히 없애기보다는 "보이지 않는 위치"로 옮기는 방식을 선호함.

### 2.2. 해결 방안 가설
- **방안 1: Win32 API (pywin32) 사용**
    - 프로세스 실행 후 해당 창의 Title을 찾아 `SetWindowPos`를 통해 위치를 이동시킴.
    - 장점: 사용자 요청(y 5000)을 정확히 구현 가능.
    - 단점: 창이 뜬 직후에 타이틀을 찾아야 하므로 타이밍 이슈가 있을 수 있음.
- **방안 2: CREATE_NO_WINDOW 플래그 사용**
    - `creationflags=0x08000000`을 사용하여 창을 아예 생성하지 않음.
    - 장점: 가장 깔끔함.
    - 단점: 실행 중인 로그를 직접 확인할 수 없음.
- **방안 3: STARTUPINFO 사용**
    - `wShowWindow = SW_HIDE`를 설정하여 창을 숨김 모드로 실행.

## 3. 해결 방향 (Proposed Actions)
- `pywin32`가 이미 설치되어 있으므로, 창을 생성한 후 `win32gui` 등을 이용해 창 위치를 화면 밖으로 이동시키는 로직을 추가함.
- 또는 `subprocess`의 `STARTUPINFO`를 활용하여 창을 숨긴 채로 실행하는 옵션을 검토함. (사용자가 원할 때 다시 볼 수 있도록 위치 이동 방식이 더 유연할 수 있음)

## 4. 수행 단계 (Milestones)
1. **[Plan]**: 터미널 창 제어 계획 수립 (현재)
2. **[Design]**: 
    - `pywin32`를 이용한 창 핸들 획득 및 위치 이동 로직 설계.
    - 혹은 `STARTUPINFO`를 이용한 숨김 처리 설계.
3. **[Do]**: 
    - `total_scrap.py`의 `run_scrapers_in_parallel` 함수 수정.
4. **[Check]**: 
    - `total_scrap.py` 실행 시 창이 화면에 나타나지 않는지 확인.
    - 백그라운드에서 프로세스가 정상적으로 종료되는지 확인.
5. **[Act]**: 최종 리포트 작성.

---
작성일: 2026-02-13
작성자: Gemini CLI Agent
