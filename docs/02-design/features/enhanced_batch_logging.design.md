# Design: Real-time Logging for Web Scraper Execution

사용자가 웹 UI(브라우저)에서 'Run Scraper' 버튼을 클릭했을 때, 터미널(서버 창)에 실시간으로 로그가 출력되지 않는 문제를 해결하기 위한 설계입니다.

## 1. 문제 분석
- 현재 `server.py`의 `/api/run-scrap` 엔드포인트는 `subprocess.run(capture_output=True)`를 사용합니다.
- `capture_output=True`는 프로세스가 **종료될 때까지 모든 출력을 버퍼링**한 후 한꺼번에 가져오기 때문에, 실행 중에는 터미널에 아무것도 찍히지 않습니다.
- 사용자는 작업이 끝날 때까지 진행 상황을 알 수 없어 답답함을 느낍니다.

## 2. 해결 전략
- `subprocess.run` 대신 `subprocess.Popen`을 사용하여 프로세스의 출력을 한 줄씩(Line-by-line) 실시간으로 읽어 서버의 표준 출력(stdout)으로 전달합니다.
- Python의 `-u` (Unbuffered) 옵션을 사용하여 서브프로세스의 출력이 즉시 전달되도록 보장합니다.

## 3. 상세 설계

### A. `server.py` 수정
- `/api/run-scrap` 내의 실행 로직 변경:
    ```python
    # AS-IS: subprocess.run (버퍼링됨)
    process = subprocess.run([...], capture_output=True, ...)

    # TO-BE: subprocess.Popen (실시간 스트리밍)
    process = subprocess.Popen(
        [sys.executable, "-u", script_path, "--mode", mode], # -u 추가
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # stderr를 stdout으로 통합
        text=True,
        encoding='utf-8',
        errors='replace',
        env=env
    )
    
    # 루프를 돌며 실시간 출력
    full_output = []
    for line in iter(process.stdout.readline, ""):
        print(line, end="") # 서버 터미널에 즉시 출력
        full_output.append(line)
    
    process.wait() # 프로세스 종료 대기
    ```

### B. `total_scrap.py` 및 하위 스크립트 확인
- 이미 직접 실행 시 로그가 잘 찍히고 있으므로, 서브프로세스로 호출될 때 `-u` 옵션만 잘 전달되면 실시간 로그가 터미널에 표시될 것입니다.

## 4. 기대 효과
- 사용자가 브라우저에서 버튼을 누르면, 배치 파일 실행 창(`run_viewer.bat`에 의해 열린 창)에 즉시 "⏳ [1/19] ..." 등의 진행 로그가 실시간으로 올라옵니다.
- 서버 로그를 통해 현재 어떤 단계(Threads 수집 중, LinkedIn 수집 중 등)인지 즉각 확인 가능합니다.
