"""X 게시일시가 KST 로 저장되는지 지키는 테스트.

2026-09-05 이전에는 두 날짜 경로가 UTC 를 그대로 기록했다. 그 회귀를 막는다.
경위: _docs/20260905_01_X-게시일시-UTC저장-결함수정과-95건-백필-계획_실행완료.md
"""

from datetime import datetime, timedelta, timezone

from utils.x_time import (
    KST,
    created_at_from_id,
    format_kst,
    parse_api_date,
    parse_iso_date,
    snowflake_drift_seconds,
    warn_on_snowflake_drift,
)

# 실측 표본. output_total/total_full_20260905.json 의 첫 X 레코드.
# 저장돼 있던 값(UTC)과 실제 KST 를 함께 둔다.
SAMPLE_ID = "2021555296000000000"
SAMPLE_API_DATE = "Wed Feb 11 12:01:56 +0000 2026"
SAMPLE_ISO_DATE = "2026-02-11T12:01:56.000Z"
EXPECTED_KST = "2026-02-11 21:01:56"
EXPECTED_DATE = "2026-02-11"


# --- API(GraphQL) 경로 -------------------------------------------------


def test_parse_api_date_는_KST_로_변환한다():
    parsed = parse_api_date(SAMPLE_API_DATE)
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=9)
    assert format_kst(parsed) == (EXPECTED_KST, EXPECTED_DATE)


def test_parse_api_date_는_UTC_벽시계를_그대로_쓰지_않는다():
    """이번 결함의 회귀 가드. 변환 없이 strftime 하면 12:01:56 이 남는다."""
    parsed = parse_api_date(SAMPLE_API_DATE)
    assert parsed is not None
    assert format_kst(parsed)[0] != "2026-02-11 12:01:56"


def test_parse_api_date_는_실패시_None():
    assert parse_api_date("말이 안 되는 값") is None
    assert parse_api_date(None) is None
    assert parse_api_date("") is None


# --- HTML 폴백 경로 ----------------------------------------------------


def test_parse_iso_date_는_KST_로_변환한다():
    parsed = parse_iso_date(SAMPLE_ISO_DATE)
    assert parsed is not None
    assert format_kst(parsed) == (EXPECTED_KST, EXPECTED_DATE)


def test_두_경로가_같은_결과를_낸다():
    """같은 트윗이면 GraphQL 이든 HTML 이든 같은 값이어야 한다."""
    from_api = parse_api_date(SAMPLE_API_DATE)
    from_iso = parse_iso_date(SAMPLE_ISO_DATE)
    assert from_api is not None and from_iso is not None
    assert format_kst(from_api) == format_kst(from_iso)


def test_parse_iso_date_는_실패시_None():
    assert parse_iso_date("2026-13-99") is None
    assert parse_iso_date(None) is None


# --- 날짜 경계 ---------------------------------------------------------


def test_UTC_15시_이후는_KST_에서_날짜가_하루_밀린다():
    """실측 95건 중 31건이 이 경우다. date 필드를 함께 고쳐야 하는 이유."""
    parsed = parse_api_date("Tue Feb 10 15:26:27 +0000 2026")
    assert parsed is not None
    assert format_kst(parsed) == ("2026-02-11 00:26:27", "2026-02-11")


# --- Snowflake 복원 ----------------------------------------------------


def test_created_at_from_id_는_KST_시각을_복원한다():
    restored = created_at_from_id(SAMPLE_ID)
    assert restored is not None
    assert restored.utcoffset() == timedelta(hours=9)


def test_created_at_from_id_는_API_파싱과_일치한다():
    """백필의 정본이 되는 성질. 두 경로가 어긋나면 백필을 믿을 수 없다."""
    restored = created_at_from_id(SAMPLE_ID)
    parsed = parse_api_date(SAMPLE_API_DATE)
    assert restored is not None and parsed is not None
    assert abs((restored - parsed).total_seconds()) < 1


def test_created_at_from_id_는_멱등하다():
    """저장값이 아니라 ID 에서 재계산하므로 반복 실행이 안전하다."""
    first = created_at_from_id(SAMPLE_ID)
    second = created_at_from_id(SAMPLE_ID)
    assert first is not None and second is not None
    assert first == second
    assert format_kst(first) == format_kst(second)


def test_created_at_from_id_는_복원_불가시_None():
    assert created_at_from_id("abc") is None
    assert created_at_from_id("") is None
    assert created_at_from_id(None) is None
    assert created_at_from_id("0") is None  # epoch 이전


# --- 회귀 가드 ---------------------------------------------------------


def test_회귀가드는_정상값에_경고하지_않는다():
    messages = []
    fired = warn_on_snowflake_drift(
        parse_api_date(SAMPLE_API_DATE), SAMPLE_ID, printer=messages.append
    )
    assert fired is False
    assert messages == []


def test_회귀가드는_9시간_어긋나면_경고한다():
    """UTC 로 되돌아가는 회귀가 나면 잡힌다."""
    utc_naive = datetime.strptime("2026-02-11 12:01:56", "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=KST
    )  # KST 라고 우기지만 값은 UTC 벽시계 — 결함 상태 재현
    messages = []
    fired = warn_on_snowflake_drift(utc_naive, SAMPLE_ID, printer=messages.append)
    assert fired is True
    assert len(messages) == 1
    assert "시각 회귀 의심" in messages[0]


def test_회귀가드는_대조_불가하면_조용히_넘어간다():
    messages = []
    assert warn_on_snowflake_drift(None, SAMPLE_ID, printer=messages.append) is False
    assert warn_on_snowflake_drift(parse_api_date(SAMPLE_API_DATE), "abc", printer=messages.append) is False
    assert messages == []


def test_drift_는_초단위_차이를_돌려준다():
    drift = snowflake_drift_seconds(parse_api_date(SAMPLE_API_DATE), SAMPLE_ID)
    assert drift is not None
    assert drift < 1


# --- 다른 플랫폼과의 기준 일치 -----------------------------------------


def test_KST_상수는_UTC_plus_9다():
    assert KST.utcoffset(None) == timedelta(hours=9)
    reference = datetime(2026, 2, 11, 12, 0, 0, tzinfo=timezone.utc)
    assert reference.astimezone(KST).hour == 21
