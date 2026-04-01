---
title: "Plan: Enhanced Logging for Batch Execution (run_viewer.bat)"
created: "2026-02-11 15:41"
---

# Plan: Enhanced Logging for Batch Execution (run_viewer.bat)

`run_viewer.bat`을 통해 스크래퍼를 실행할 때, 터미널에 상세 로그가 표시되지 않아 진행 상황을 파악하기 어려운 문제를 해결합니다.

## 1. 목적
- `run_viewer.bat` 실행 시 `total_scrap.py` 직접 실행과 동일한 수준의 상세 로그 출력
- 실시간 수집 현황(진행률, 성공/실패 여부) 파악 가능하도록 개선
- 백그라운드 실행 시의 답답함 해소

## 2. 원인 분석 (Hypothesis)
- `run_viewer.bat`에서 Python 실행 시 표준 출력(stdout)이 버퍼링되어 실시간으로 보이지 않거나, 특정 리다이렉션 설정이 되어 있을 가능성.
- 혹은 `execute_invisible.vbs` 등을 통해 백그라운드로 실행되면서 출력이 숨겨진 경우.

## 3. 핵심 설계 (Core Design)
- **배치 파일 수정 (`run_viewer.bat`)**: 
    - Python 실행 시 `-u` 옵션(Unbuffered)을 추가하여 실시간 로그 출력을 보장.
    - `python -u total_scrap.py` 형태로 변경.
- **VBScript 확인 (`execute_invisible.vbs`)**: 
    - 만약 로그를 보길 원한다면, "Invisible" 모드가 아닌 일반 터미널 모드로 실행되도록 조정하거나 로그 파일을 `tail -f`로 볼 수 있게 가이드 제공. (사용자는 터미널에 로그가 뜨길 원하므로 터미널 가시성 확보가 우선)
- **로깅 코드 보완 (`total_scrap.py`)**: 
    - 필요한 경우 `sys.stdout.flush()`를 명시적으로 호출하거나 로깅 라이브러리 설정 확인.

## 4. 실행 단계
1. `run_viewer.bat`과 `execute_invisible.vbs` 파일 내용 확인.
2. `total_scrap.py`의 출력 방식(print vs logging) 확인.
3. `-u` 플래그 적용 및 터미널 출력 설정 수정.
4. 실제 배치 실행을 통한 로그 표시 여부 검증.

## 5. 기대 결과
- 사용자가 `run_viewer.bat`만 실행해도 터미널 창에 실시간으로 수집 로그가 출력되어 안심하고 기다릴 수 있음.
