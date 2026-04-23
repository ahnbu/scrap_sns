import pytest
import json
import glob
import hashlib
import os
import re


def _total_files():
    return [
        path
        for path in glob.glob("output_total/total_full_*.json")
        if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
    ]


def _latest_total_file():
    total_files = _total_files()
    if not total_files:
        pytest.skip("검증할 통합 JSON 파일이 없습니다.")
    return max(total_files, key=os.path.getmtime)

def test_total_json_schema():
    """통합 JSON 파일의 필수 필드 및 구조를 검증합니다."""
    latest_file = _latest_total_file()
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


def _local_image_path(media_url):
    lower_url = str(media_url).lower()
    if ".png" in lower_url:
        ext = ".png"
    elif ".webp" in lower_url:
        ext = ".webp"
    else:
        ext = ".jpg"
    filename = hashlib.md5(str(media_url).encode("utf-8")).hexdigest() + ext
    return os.path.join("web_viewer", "images", filename), f"web_viewer/images/{filename}"


def test_latest_total_links_existing_local_image_files():
    latest_file = _latest_total_file()
    with open(latest_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    missing = []
    for post in data.get("posts", []):
        local_images = set(post.get("local_images") or [])
        for media_url in post.get("media") or []:
            if ".mp4" in str(media_url).lower():
                continue
            fs_path, web_path = _local_image_path(media_url)
            if os.path.exists(fs_path) and web_path not in local_images:
                missing.append((post.get("code") or post.get("platform_id"), web_path))
                if len(missing) >= 5:
                    break
        if len(missing) >= 5:
            break

    assert not missing, f"기존 로컬 이미지 파일이 local_images에 연결되지 않았습니다: {missing}"
