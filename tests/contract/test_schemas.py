import pytest
import json
import glob
import os

def test_total_json_schema():
    """통합 JSON 파일의 필수 필드 및 구조를 검증합니다."""
    total_files = glob.glob("output_total/total_full_*.json")
    if not total_files:
        pytest.skip("검증할 통합 JSON 파일이 없습니다.")
    
    latest_file = max(total_files, key=os.path.getmtime)
    with open(latest_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
        
    # 1. 루트 구조 검증
    assert "metadata" in data
    assert "posts" in data
    
    # 2. 메타데이터 필수 필드
    metadata = data["metadata"]
    assert "total_count" in metadata
    assert "max_sequence_id" in metadata
    
    # 3. 포스트 데이터 필수 필드
    posts = data["posts"]
    if posts:
        sample = posts[0]
        required_fields = ["sequence_id", "platform_id", "sns_platform", "full_text", "url"]
        for field in required_fields:
            assert field in sample, f"필수 필드 누락: {field}"
            
        # 4. 데이터 정합성 (sequence_id는 양수)
        assert sample["sequence_id"] > 0
        assert sample["sns_platform"] in ["threads", "linkedin", "x", "twitter"]
