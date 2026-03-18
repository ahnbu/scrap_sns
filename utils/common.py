import json
import os
import re
import glob
from datetime import datetime, timedelta

def load_json(filepath, default=None):
    if default is None:
        default = []
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception as e:
            print(f'⚠️ [Common] JSON 로드 실패 ({filepath}): {e}')
            return default
    return default

def save_json(filepath, data, indent=4):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except Exception as e:
        print(f'⚠️ [Common] JSON 저장 실패 ({filepath}): {e}')
        return False

def clean_text(text, platform=None, **kwargs):
    if not text: return ''
    if isinstance(text, list): text = '\n'.join(text)
    
    # 1. 플랫폼별 사전 처리 (Pre-processing)
    if platform == 'twitter' or platform == 'x':
        # Twitter 특화: 줄바꿈 제거 및 연속 공백 축소 (기존 로직 준수)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip().replace('\n', ' ')
        return re.sub(r'\s+', ' ', text).strip()
    
    if platform == 'linkedin':
        # LinkedIn 특화: "…더보기" UI 텍스트 제거 및 공백 정규화
        text = text.replace("…더보기", "")
        lines = text.split('\n')
        cleaned_lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
        return "\n".join(cleaned_lines).strip()

    # 2. 공통 및 Threads 특화 처리
    lines = text.split('\n')
    cleaned_lines = []
    
    # Threads: 첫 줄에 username이 있으면 제거
    username = kwargs.get('username')
    if platform == 'threads' and lines and username and lines[0].strip() == username:
        lines.pop(0)

    # 필터링할 메타데이터 패턴
    meta_patterns = [
        r'^\d+시간$', r'^\d+분$', r'^\d+일$', r'^\d+주$', 
        r'^\d{4}-\d{2}-\d{2}$', r'^AI Threads$', r'^수정됨$', 
        r'^답글$', r'^\d+$', r'^\d+/\d+$'
    ]
    
    is_body_started = False
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # 메타데이터 패턴 검사
        is_metadata = any(re.match(p, line) for p in meta_patterns)
        
        if is_metadata:
            # 메타데이터는 무조건 건너뜀
            continue
            
        if platform == 'threads':
            # Threads: 본문 시작 플래그 설정
            is_body_started = True
            
        cleaned_lines.append(line)
        
    return '\n'.join(cleaned_lines).strip()

def reorder_post(post):
    # 표준 필드 순서 (최신 요구사항 반영)
    STANDARD_FIELD_ORDER = [
        'sequence_id', 'platform_id', 'sns_platform', 'code', 'urn',
        'username', 'display_name', 'full_text', 'media', 'url', 
        'created_at', 'date', 'crawled_at', 'source', 'local_images', 
        'is_detail_collected', 'is_merged_thread'
    ]
    ordered_post = {}
    for field in STANDARD_FIELD_ORDER:
        if field in post: ordered_post[field] = post[field]
    
    # 누락된 나머지 필드 추가
    for key, value in post.items():
        if key not in ordered_post: ordered_post[key] = value
    return ordered_post

def format_timestamp(ts):
    if not ts: return None, None
    try:
        dt = datetime.fromtimestamp(int(ts))
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except Exception: return None, None

def parse_relative_time(relative_str, base_time=None):
    if not relative_str: return None, None
    if not base_time: base_time = datetime.now()
    if re.match(r'^\d{4}-\d{2}-\d{2}$', relative_str): return f'{relative_str} 00:00:00', relative_str
    match = re.search(r'(\d+)\s*(분|시간|일|주|개월|년)', relative_str)
    if not match: return None, None
    value = int(match.group(1)); unit = match.group(2)
    delta = None
    if unit == '분': delta = timedelta(minutes=value)
    elif unit == '시간': delta = timedelta(hours=value)
    elif unit == '일': delta = timedelta(days=value)
    elif unit == '주': delta = timedelta(weeks=value)
    elif unit == '개월': delta = timedelta(days=value * 30)
    elif unit == '년': delta = timedelta(days=value * 365)
    if delta:
        target_time = base_time - delta
        return target_time.strftime('%Y-%m-%d %H:%M:%S'), target_time.strftime('%Y-%m-%d')
    return None, None

def save_debug_snapshot(content, platform, ext="html"):
    """
    스크래퍼의 성공/실패 시 디버깅 및 TDD 테스트용으로 원본 데이터를 저장합니다.
    """
    import os
    import time
    try:
        snapshot_dir = os.path.join("tests", "fixtures", "snapshots", platform)
        os.makedirs(snapshot_dir, exist_ok=True)
        # 최대 10개만 유지 (오래된 것 삭제)
        existing_files = sorted(os.listdir(snapshot_dir))
        if len(existing_files) > 10:
            for old_file in existing_files[:-9]:
                os.remove(os.path.join(snapshot_dir, old_file))
                
        snapshot_path = os.path.join(snapshot_dir, f"snapshot_{int(time.time())}.{ext}")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            if ext == "json" and isinstance(content, dict):
                import json
                json.dump(content, f, ensure_ascii=False, indent=2)
            else:
                f.write(str(content))
    except Exception as e:
        print(f"Failed to save snapshot: {e}")

