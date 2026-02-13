# PDCA 설계: total_scrap.py 터미널 창 숨김 및 로그 파일 저장

## 1. 개요 (Overview)
- **목표**: `total_scrap.py`에서 실행되는 3개의 자식 프로세스(터미널)를 완전히 숨기고(Invisible), 각 프로세스의 출력을 로그 파일로 저장하여 필요 시 확인할 수 있도록 함.
- **방식**: `CREATE_NO_WINDOW` 플래그 사용 및 `stdout/stderr` 리다이렉션.

## 2. 상세 설계 (Technical Design)

### 2.1. 프로세스 숨김 및 로그 리다이렉션
- **창 숨김**: `creationflags=0x08000000` (CREATE_NO_WINDOW) 사용.
- **로그 저장**: `logs/` 디렉토리를 생성하고, 각 플랫폼별로 `.log` 파일을 생성하여 `stdout`과 `stderr`를 리다이렉션함.
- **실시간 확인**: 사용자는 필요 시 `logs/threads.log` 등을 열어서 진행 상황 확인 가능.

### 2.2. 수정 대상 코드 (`total_scrap.py`)
- `run_scrapers_in_parallel` 함수 내부.
- 로그 폴더 생성 로직 추가 (`os.makedirs("logs", exist_ok=True)`).
- `subprocess.Popen` 호출 시 `stdout`, `stderr` 설정 추가.

```python
# 설계안 코드 예시
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = open(os.path.join(LOG_DIR, f"{platform.lower()}.log"), "w", encoding="utf-8")
p = subprocess.Popen(
    f"python {script_name} --mode {mode}", 
    creationflags=0x08000000, # CREATE_NO_WINDOW
    stdout=log_file,
    stderr=subprocess.STDOUT
)
```

## 3. 검증 계획 (Verification Plan)
- **테스트 케이스**:
    1. `total_scrap.py` 실행 시 어떤 터미널 창도 새로 뜨지 않는지 확인.
    2. `logs/` 폴더 내에 `threads.log`, `twitter.log`, `linkedin.log` 파일이 생성되는지 확인.
    3. 각 로그 파일에 스크래핑 진행 내용이 실시간으로 기록되는지 확인.
    4. 프로세스 완료 후 로그 파일이 정상적으로 닫히고 수집 데이터가 생성되는지 확인.

---
작성일: 2026-02-13
작성자: Gemini CLI Agent
