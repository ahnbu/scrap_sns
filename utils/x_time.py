"""X(Twitter) 게시일시 처리 — 전 플랫폼 공통 기준인 KST로 통일한다.

이 레포의 `created_at` 은 **모든 플랫폼이 KST 기준**이다.
- Threads : `utils/common.py` `format_timestamp()` → `datetime.fromtimestamp()` (로컬=KST)
- LinkedIn: `utils/linkedin_parser.py` `get_date_from_snowflake_id()` (로컬=KST)
- YouTube : `youtube_scrap.py` `_to_kst()` (명시 +9)
- X       : 이 모듈

X 만 2026-09-05 까지 UTC 로 저장돼 있었다. API 가 주는 `Sat Sep 05 01:23:45 +0000 2026`
형식을 `%z` 가 아니라 `+0000` 리터럴로 파싱해 tz 정보가 사라졌고, 변환 없이 그대로
기록했기 때문이다. 경위와 백필 절차는
`_docs/20260905_01_X-게시일시-UTC저장-결함수정과-95건-백필-계획_실행완료.md` 에 있다.

의도적으로 표준 라이브러리만 쓴다 — 수집기·백필 스크립트·테스트가 모두 이 모듈을
불러야 하는데, bs4/playwright 같은 무거운 의존을 끌고 들어오면 백필이 수집 환경에
묶인다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 트윗 Snowflake ID 의 기준 시각. 2010-11-04T01:42:54.657Z
X_SNOWFLAKE_EPOCH_MS = 1288834974657

# 파싱 결과와 Snowflake 복원값이 이보다 더 벌어지면 회귀로 본다.
# 같은 트윗을 가리키는 두 경로이므로 정상이면 초 단위로 일치한다.
SNOWFLAKE_DRIFT_TOLERANCE_SEC = 60

TWITTER_API_DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def format_kst(dt: datetime) -> tuple[str, str]:
    """KST 기준 (전체시각, 날짜) 문자열 쌍을 만든다."""
    kst = dt.astimezone(KST)
    return kst.strftime("%Y-%m-%d %H:%M:%S"), kst.strftime("%Y-%m-%d")


def parse_api_date(date_str) -> datetime | None:
    """X API 의 created_at 문자열을 KST datetime 으로 바꾼다.

    `%z` 로 오프셋을 실제 파싱한다. `+0000` 을 포맷 리터럴로 두면 naive UTC 가 되어
    변환 기회 자체가 사라진다 — 그것이 이번 결함의 원인이었다.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str), TWITTER_API_DATE_FORMAT).astimezone(KST)
    except (ValueError, TypeError):
        return None


def parse_iso_date(date_str) -> datetime | None:
    """`<time datetime="...Z">` 속성값을 KST datetime 으로 바꾼다."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).astimezone(KST)
    except (ValueError, TypeError):
        return None


def created_at_from_id(platform_id) -> datetime | None:
    """트윗 Snowflake ID 에서 발행 시각(KST)을 복원한다.

    상위 41비트가 epoch 이후 밀리초다(하위 22비트는 워커·시퀀스).
    복원할 수 없으면 None 을 돌려주고, 호출부는 원래 값을 유지한다.

    이 함수가 백필의 정본이다 — 저장값에 +9시간을 더하는 방식과 달리 몇 번
    실행해도 결과가 같아서, 이중 보정을 막을 실행 마커가 필요 없다.
    """
    text = str(platform_id or "").strip()
    if not text.isdigit():
        return None
    ms = (int(text) >> 22) + X_SNOWFLAKE_EPOCH_MS
    # 하위 22비트뿐인 값(id < 2**22)은 epoch 자기 자신으로 복원된다.
    # 실제 트윗 ID 는 그보다 훨씬 크므로, 그럴듯한 2010-11-04 을 써 넣는 대신 거른다.
    if ms <= X_SNOWFLAKE_EPOCH_MS:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(KST)
    except (OverflowError, OSError, ValueError):
        return None


def snowflake_drift_seconds(parsed: datetime | None, platform_id) -> float | None:
    """파싱 결과와 Snowflake 복원값의 차이(초). 대조 불가면 None."""
    restored = created_at_from_id(platform_id)
    if parsed is None or restored is None:
        return None
    return abs((parsed - restored).total_seconds())


def warn_on_snowflake_drift(parsed: datetime | None, platform_id, *, printer=print) -> bool:
    """타임존 회귀 가드. 어긋나면 경고를 남기고 True 를 돌려준다.

    이번 결함이 5개월 넘게 조용히 살아 있었던 이유는 틀렸는지 알 방법이
    없었기 때문이다. 같은 구멍을 막는다.
    """
    drift = snowflake_drift_seconds(parsed, platform_id)
    if drift is None or drift <= SNOWFLAKE_DRIFT_TOLERANCE_SEC:
        return False
    printer(
        f"   ⚠️ [시각 회귀 의심] id={platform_id} 파싱={parsed} "
        f"Snowflake복원={created_at_from_id(platform_id)} 차이={drift:.0f}초"
    )
    return True
