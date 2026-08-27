"""내 Threads 게시물(insight) 레코드를 scrap_sns 표준 Post 스키마로 변환한다.

계획: _docs/20260827_02_내-쓰레드-글-수집-계획.md (3.3~3.5)

입력은 `D:/vibe-coding/sns_insight_update` 가 만드는 `sns_insight.v1` 레코드다.
그 레포는 수정하지 않는다 - 수집기는 그대로 두고 산출물만 받는다(계획 3.1).

이 어댑터가 책임지는 세 가지:

1. **자기 답글 이어붙이기** (계획 3.3). Threads 본문 상한이 499자라 넘치는 분량이
   자기 답글로 나뉘어 있다. 실측 32건 중 21건(66%), 6,905자. 그대로 두면 본문이
   중간에 끊긴 채 저장된다. 저장글은 이미 같은 방식으로 병합돼 있다(1,187/1,273).
2. **UTC → KST 변환** (계획 3.5). Graph API 는 UTC 를 주고 이 레포는 전 플랫폼이
   KST naive 문자열로 저장한다(`utils/common.py:109`). 여기서 끝내야 하류가
   시간대를 몰라도 된다.
3. **리포스트 제외** (계획 3.4). 남의 글 공유는 내 글이 아니다.

⚠️ `code` 는 Graph API 의 숫자 id 가 아니라 permalink 의 shortcode 다.
   `utils/post_meta.py:62` 의 `canonicalize_url()` 이 `username` + `code` 로
   원문 URL 을 조립하므로, 숫자 id 를 넣으면 열리지 않는 URL 이 만들어진다.
   저장글도 shortcode 를 쓴다(예: `DUn02Eukm2o`).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from utils.post_schema import normalize_post


#: 내 Threads 핸들. 저장글과 같은 표기(@ 없음)를 써야 뷰어 저자 필터가 갈리지 않는다.
MY_THREADS_USERNAME = "byungwook.an"

#: 수집 경로 표기. `source` 는 방법을 적는 자리이고 내 글 여부는 `is_own_post` 가 든다.
OWN_POST_SOURCE = "my_insight_threads_api"

#: 남의 글 공유. 본문이 비어 있고 내 글이 아니다(계획 1.1 #3).
REPOST_MEDIA_TYPE = "REPOST_FACADE"

#: 자기 답글이 이 시간 안에 올라왔으면 본문 이어쓰기로 본다(계획 3.3).
#: 실측 23개 중 22개가 11.6분 이내, 대화형 답글 1개가 551.7분.
SELF_REPLY_WINDOW_MINUTES = 30

KST = timezone(timedelta(hours=9))

_SHORTCODE_RE = re.compile(r"/post/([A-Za-z0-9_-]+)")


def extract_shortcode(url) -> str:
    """permalink 에서 shortcode 를 뽑는다. 없으면 빈 문자열."""
    match = _SHORTCODE_RE.search(str(url or ""))
    return match.group(1) if match else ""


def parse_api_datetime(value):
    """Graph API 시각 문자열을 tz-aware datetime 으로. 실패하면 None.

    `+0000` 과 `+00:00` 을 모두 받는다. 타임존이 없으면 UTC 로 본다 -
    Graph API 가 UTC 를 주기 때문이며, 여기서 로컬로 가정하면 9시간 어긋난다.
    """
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    else:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def to_kst_text(value) -> str | None:
    """Graph API 시각 -> 'YYYY-MM-DD HH:MM:SS' (KST naive). 실패하면 None."""
    parsed = parse_api_datetime(value)
    if parsed is None:
        return None
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def _thread_raw(record: dict) -> dict:
    raw = record.get("raw") or {}
    thread = raw.get("thread") if isinstance(raw, dict) else None
    return thread if isinstance(thread, dict) else {}


def is_repost(record: dict) -> bool:
    """남의 글 공유인가(계획 3.4)."""
    return str(_thread_raw(record).get("media_type") or "").upper() == REPOST_MEDIA_TYPE


def select_continuations(
    root_created_at,
    replies,
    *,
    username: str = MY_THREADS_USERNAME,
    window_minutes: int = SELF_REPLY_WINDOW_MINUTES,
) -> list[dict]:
    """답글 목록에서 본문 이어쓰기만 골라 시간순으로 돌려준다(계획 3.3).

    두 조건을 모두 만족해야 한다.
      - 작성자가 나  (남의 댓글을 본문에 붙이면 안 된다)
      - 원글 이후 `window_minutes` 이내  (9시간 뒤 대화형 답글을 걸러낸다)

    원글보다 앞선 시각은 데이터 이상이므로 제외한다.
    """
    base = parse_api_datetime(root_created_at)
    if base is None:
        return []
    window = timedelta(minutes=window_minutes)

    picked = []
    for reply in replies or []:
        if not isinstance(reply, dict):
            continue
        if str(reply.get("username") or "") != username:
            continue
        text = str(reply.get("text") or "").strip()
        if not text:
            continue
        stamp = parse_api_datetime(reply.get("timestamp"))
        if stamp is None:
            continue
        gap = stamp - base
        if gap < timedelta(0) or gap > window:
            continue
        picked.append((stamp, text))

    picked.sort(key=lambda item: item[0])
    return [{"timestamp": stamp.isoformat(), "text": text} for stamp, text in picked]


def merge_body(root_text, continuations) -> str:
    """원글 본문에 이어쓰기를 붙인다. 빈 조각은 버린다."""
    parts = [str(root_text or "").strip()]
    for item in continuations or []:
        text = str((item or {}).get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(part for part in parts if part)


def to_standard_post(record: dict, continuations=None) -> dict:
    """insight 레코드 1건을 표준 Post dict 로 바꾼다.

    `sequence_id` 는 부여하지 않는다 - 통합 파일 안에서 다시 매겨지는
    로컬 순서값이라 durable identity 가 아니다(AGENTS.md).
    """
    metrics = record.get("metrics") or {}
    thread = _thread_raw(record)
    url = str(record.get("url") or "").strip()
    shortcode = extract_shortcode(url)
    created_at = to_kst_text(record.get("created_at"))
    collected_at = record.get("collected_at") or None
    continuations = list(continuations or [])

    post = {
        "platform_id": shortcode,
        "code": shortcode,
        "sns_platform": "threads",
        "username": str(record.get("author") or MY_THREADS_USERNAME),
        "display_name": str(record.get("author") or MY_THREADS_USERNAME),
        "full_text": merge_body(record.get("text"), continuations),
        "url": url,
        "created_at": created_at,
        "crawled_at": collected_at,
        # Graph API 가 5종 지표를 모두 권위 있게 준다. LinkedIn 과 달리
        # 다른 경로가 채우는 칸이 없어 필드를 나눠 지킬 필요가 없다.
        "view_count": metrics.get("impressions"),
        "like_count": metrics.get("likes"),
        # Threads 가 세는 replies 에는 내 이어쓰기도 포함된다. 화면에 뜨는 값과
        # 맞추기 위해 빼지 않고 그대로 싣는다.
        "comment_count": metrics.get("replies"),
        "share_count": metrics.get("reposts"),
        "quote_count": metrics.get("quotes"),
        "metrics_updated_at": collected_at,
        "source": OWN_POST_SOURCE,
        "media": [thread["media_url"]] if thread.get("media_url") else [],
        "is_detail_collected": True,
        "is_merged_thread": bool(continuations),
        "is_own_post": True,
    }
    return normalize_post(post)


def to_standard_posts(records, continuations_by_id=None) -> list[dict]:
    """insight 레코드 목록을 표준 Post 목록으로 바꾼다.

    리포스트와 식별자 없는 건은 버린다. `continuations_by_id` 는
    Graph API 숫자 id 를 키로 하는 이어쓰기 목록이다 - 답글을 부를 때
    쓰는 것이 숫자 id 라 shortcode 로 바꾸기 전 값을 키로 둔다.
    """
    lookup = continuations_by_id or {}
    out = []
    for record in records or []:
        if str(record.get("platform") or "").lower() != "threads":
            continue
        if is_repost(record):
            continue
        api_id = str(record.get("platform_post_id") or "")
        post = to_standard_post(record, lookup.get(api_id))
        if not post.get("platform_id") or not post.get("url"):
            continue
        out.append(post)
    return out


def merge_own_post(existing: dict | None, incoming: dict) -> dict:
    """기존 레코드 위에 새 수집 결과를 얹는다.

    지표는 매 실행마다 Graph API 가 전부 새로 주므로 원칙적으로 incoming 이 이긴다.
    다만 부분 실패로 일부 지표가 None 으로 오는 경우가 있어, **None 이 기존 값을
    덮지는 않게** 한다. 있던 성과 수치가 조용히 사라지는 쪽이 더 나쁘다.
    """
    if not existing:
        return dict(incoming)

    merged = dict(existing)
    for key, value in incoming.items():
        if key == "sequence_id":
            continue
        if value is None and merged.get(key) is not None:
            continue
        merged[key] = value
    return merged
