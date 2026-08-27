"""내 게시물(insight) 레코드를 scrap_sns 표준 Post 스키마로 변환한다.

계획: _docs/20260826_03_내-게시물-성과지표-통합-수집-계획.md (3.5)

입력은 `D:/vibe-coding/sns_insight_update` 가 만드는 `sns_insight.v1` 레코드다.
그 레포는 수정하지 않는다 - 수집기는 그대로 두고 산출물만 받는다(계획 3.1).

⚠️ 이 어댑터는 노출수(`view_count`)만 신뢰한다. 로그인 recent-activity 카드는
   노출수를 전량 주지만 반응수는 상위 몇 건만 렌더링한다(계획 1.1 #7·#8 실측:
   impressions 36/36, reactions 5/36). 반응·댓글은 비로그인 경로
   (`linkedin_metric_single.py`)가 채우므로 여기서 온 None 으로 덮어쓰면 안 된다.
   병합 규칙은 `merge_own_post()` 가 강제한다(계획 3.6).
"""

from __future__ import annotations

from datetime import datetime

from utils.post_schema import normalize_post


#: 내 LinkedIn member ID. 저장글과 같은 식별자 체계를 써야 뷰어 저자 필터가 갈리지 않는다.
#: 값 출처: output_total 에 이미 들어 있던 내 글 1건의 username(계획 1.1 #1).
MY_LINKEDIN_MEMBER_ID = "ACoAAEeG7JUBmAYkdijja-FrtAJT6XmXgy22WII"

#: 수집 경로 표기. `source` 는 방법을 적는 자리이고 내 글 여부는 `is_own_post` 가 든다.
OWN_POST_SOURCE = "my_insight_recent_activity"

#: 로그인 경로가 신뢰할 수 있게 채우는 유일한 지표 필드.
LOGIN_PATH_METRIC_FIELDS = ("view_count",)

#: 비로그인 경로가 담당하므로 로그인 경로가 건드리면 안 되는 필드(계획 3.6).
#
# 🔴 `metrics_updated_at` 이 여기 있는 이유(계획 _docs/20260827_04 3.5 T5-d):
#    이 필드는 "지표를 언제 읽었는가"이지 "레코드를 언제 수집했는가"가 아니다.
#    어댑터가 `collected_at` 으로 덮으면 갱신 시각이 매 실행마다 「지금」으로
#    리셋되고, 신선도 정책(`utils/metric_refresh.py` `refresh_after_days`)이
#    "방금 읽었다"고 오판해 **지표를 영원히 다시 읽지 않는다.**
#    `linkedin_scrap.py:PRESERVED_METRIC_FIELDS` 와
#    `thread_scrap_single.py:METRIC_FIELDS` 가 같은 이유로 이 필드를 넣어뒀다 -
#    이 세 번째 복사본만 빠져 있었다.
NON_LOGIN_PATH_METRIC_FIELDS = (
    "like_count",
    "comment_count",
    "share_count",
    "metrics_updated_at",
)


def _to_standard_datetime(value):
    """ISO 8601(타임존 포함 가능) -> 'YYYY-MM-DD HH:MM:SS'.

    scrap_sns 표준은 타임존 없는 로컬 문자열이다(예: '2024-10-19 09:59:18').
    """
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # 이미 표준 형식이면 그대로 쓴다.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def to_standard_post(record: dict) -> dict:
    """insight 레코드 1건을 표준 Post dict 로 바꾼다.

    `sequence_id` 는 부여하지 않는다 - 통합 파일 안에서 다시 매겨지는
    로컬 순서값이라 durable identity 가 아니다(AGENTS.md).
    """
    metrics = record.get("metrics") or {}
    post_id = str(record.get("platform_post_id") or "").strip()
    created_at = _to_standard_datetime(record.get("created_at"))
    collected_at = record.get("collected_at") or None

    post = {
        "platform_id": post_id,
        "code": post_id,
        "sns_platform": "linkedin",
        "username": MY_LINKEDIN_MEMBER_ID,
        "display_name": record.get("author") or "안병욱",
        "full_text": record.get("text") or "",
        "url": record.get("url") or "",
        "created_at": created_at,
        "crawled_at": collected_at,
        # 노출수만 로그인 경로가 채운다. 나머지 지표는 아래에서 명시적으로 비운다.
        "view_count": metrics.get("impressions"),
        "metrics_updated_at": collected_at,
        "source": OWN_POST_SOURCE,
        "is_detail_collected": True,
        "is_own_post": True,
    }
    return normalize_post(post)


def to_standard_posts(records) -> list[dict]:
    """insight 레코드 목록을 표준 Post 목록으로 바꾼다. 식별자 없는 건은 버린다."""
    out = []
    for record in records or []:
        if str(record.get("platform") or "").lower() != "linkedin":
            continue
        post = to_standard_post(record)
        if not post.get("platform_id") or not post.get("url"):
            continue
        out.append(post)
    return out


def merge_own_post(existing: dict | None, incoming: dict) -> dict:
    """기존 레코드 위에 새 수집 결과를 필드 단위로 얹는다(계획 3.6).

    로그인 경로는 `view_count` 와 본문·URL·작성일만 갱신하고,
    비로그인 경로가 채운 `like_count`·`comment_count`·`share_count` 는 보존한다.
    통째로 덮어쓰면 최신 반응수가 None 으로 날아간다.
    """
    if not existing:
        return dict(incoming)

    merged = dict(existing)
    for key, value in incoming.items():
        if key in NON_LOGIN_PATH_METRIC_FIELDS:
            continue
        if key == "sequence_id":
            continue
        merged[key] = value

    # 비로그인 경로가 아직 한 번도 못 채웠으면 빈 값이라도 스키마 형태는 유지한다.
    for key in NON_LOGIN_PATH_METRIC_FIELDS:
        if key not in merged:
            merged[key] = existing.get(key)
    return merged
