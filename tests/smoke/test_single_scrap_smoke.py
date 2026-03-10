import pytest
import subprocess
import sys
import os
import json

@pytest.mark.single
def test_threads_single_scrap_smoke():
    # 실제 수집 테스트 (단일 타래글)
    # 세션이 유효해야 함
    test_url = "https://www.threads.net/@zuck/post/C3A_u23L6hS" # 마크 저커버그의 글 예시
    script_path = "thread_scrap_single.py"
    
    # 1개만 테스트로 수집 시도 (실행 여부만 확인)
    result = subprocess.run(
        [sys.executable, script_path, test_url, "--limit", "1"],
        capture_output=True, text=True, encoding='utf-8'
    )
    
    print(result.stdout)
    assert result.returncode == 0, f"Single scrap failed: {result.stderr}"

@pytest.mark.single
def test_twitter_single_scrap_smoke():
    test_url = "https://x.com/elonmusk/status/1755813303666135040" # 일론 머스크의 글 예시
    script_path = "twitter_scrap_single.py"
    
    result = subprocess.run(
        [sys.executable, script_path, test_url, "--limit", "1"],
        capture_output=True, text=True, encoding='utf-8'
    )
    
    print(result.stdout)
    # 트위터는 세션이 없으면 실패할 수 있으므로, 실행 시도 로그 확인
    assert result.returncode == 0 or "login" in result.stdout.lower()
