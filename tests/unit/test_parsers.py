import pytest
from datetime import datetime, timedelta
import thread_scrap
import linkedin_scrap

def test_threads_clean_text():
    raw_text = "user123\n1시간\n본문 내용입니다.\n여기도 본문.\n1/5"
    username = "user123"
    cleaned = thread_scrap.clean_text(raw_text, username)
    assert "1시간" not in cleaned
    assert "user123" not in cleaned
    assert "본문 내용입니다." in cleaned
    assert "1/5" not in cleaned

def test_threads_parse_relative_time():
    base_time = datetime(2026, 3, 10, 12, 0, 0)
    
    # "1시간" 테스트
    abs_time, date_only = thread_scrap.parse_relative_time("1시간", base_time)
    assert abs_time == "2026-03-10 11:00:00"
    
    # "1일" 테스트
    abs_time, date_only = thread_scrap.parse_relative_time("1일", base_time)
    assert abs_time == "2026-03-09 12:00:00"
    
    # "1주" 테스트
    abs_time, date_only = thread_scrap.parse_relative_time("1주", base_time)
    assert abs_time == "2026-03-03 12:00:00"

def test_linkedin_extract_urn_id():
    urn = "urn:li:activity:7422622332021604353"
    assert linkedin_scrap.extract_urn_id(urn) == "7422622332021604353"
    
    # 이미 ID인 경우
    assert linkedin_scrap.extract_urn_id("12345") == "12345"

def test_linkedin_clean_text():
    raw = "안녕하세요!…더보기"
    assert linkedin_scrap.clean_text(raw) == "안녕하세요!"
