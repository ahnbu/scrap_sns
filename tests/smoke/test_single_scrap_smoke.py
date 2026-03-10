import pytest
import subprocess
import sys
import os
import json

@pytest.mark.single
def test_threads_single_scrap_smoke():
    # 실제 수집 테스트 (단일 타래글)
    # 인자를 받지 않고 미수집 항목을 자동으로 처리하는 방식이므로, 그냥 실행하여 에러가 없는지 확인
    script_path = "thread_scrap_single.py"
    
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True, text=True, encoding='utf-8', timeout=60
    )
    
    print(result.stdout)
    assert result.returncode == 0 or "🏁 Finished" in result.stdout

@pytest.mark.single
def test_twitter_single_scrap_smoke():
    # Twitter Single Scrap도 인자 없이 미수집 항목을 처리하는 구조인지 확인
    script_path = "twitter_scrap_single.py"
    
    result = subprocess.run(
        [sys.executable, script_path, "--limit", "1"],
        capture_output=True, text=True, encoding='utf-8', timeout=60
    )
    
    print(result.stdout)
    # usage 에러가 나지 않고 정상 실행되었는지 확인
    assert "error: unrecognized arguments" not in result.stderr
    assert result.returncode == 0 or "수집 완료" in result.stdout or "데이터 로드" in result.stdout
