import json
import os
import re
import glob
from datetime import datetime, timedelta

def load_json(filepath, default=[]):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception as e:
            print(f'⚠️ [Common] JSON 로드 실패 ({filepath}): {e}')
            return default
    return default

def save_json(filepath, data, indent=2):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except Exception as e:
        print(f'⚠️ [Common] JSON 저장 실패 ({filepath}): {e}')
        return False

def clean_text(text, exclude_list=None):
    if not text: return ''
    if isinstance(text, list): text = '\n'.join(text)
    lines = text.split('\n')
    cleaned_lines = []
    if exclude_list:
        if lines and lines[0].strip() in exclude_list: lines.pop(0)
    meta_patterns = [r'^\d+시간$', r'^\d+분$', r'^\d+일$', r'^\d{4}-\d{2}-\d{2}$', r'^\d+주$', r'^AI Threads$', r'^수정됨$', r'^답글$']
    for line in lines:
        line = line.strip()
        if not line: continue
        if any(re.match(p, line) for p in meta_patterns): continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines)

def reorder_post(post):
    STANDARD_FIELD_ORDER = ['sequence_id', 'platform_id', 'sns_platform', 'username', 'display_name', 'full_text', 'media', 'url', 'created_at', 'date', 'crawled_at', 'source', 'local_images']
    ordered_post = {}
    for field in STANDARD_FIELD_ORDER:
        if field in post: ordered_post[field] = post[field]
    for key, value in post.items():
        if key not in ordered_post: ordered_post[key] = value
    return ordered_post

def format_timestamp(ts):
    if not ts: return None, None
    try:
        dt = datetime.fromtimestamp(int(ts))
        return dt.strftime('%Y-%m-%d %H:%M:%S'), dt.strftime('%Y-%m-%d')
    except: return None, None

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
