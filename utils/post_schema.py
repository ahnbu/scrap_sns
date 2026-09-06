"""Post schema single source of truth."""

from __future__ import annotations


STANDARD_FIELD_ORDER = [
    "sequence_id",
    "platform_id",
    "sns_platform",
    "code",
    "urn",
    "username",
    "display_name",
    "full_text",
    "media",
    "url",
    # created_at·date 는 전 플랫폼 KST 기준이다. 오프셋 표기가 없는 naive 문자열이라
    # 값만 봐서는 기준을 알 수 없으므로 새 수집기를 붙일 때 반드시 KST 로 맞춘다.
    # 플랫폼별 변환 지점: _docs/architecture.md 2절.
    "created_at",
    "date",
    "crawled_at",
    "like_count",
    "comment_count",
    "share_count",
    "quote_count",
    "bookmark_count",
    "view_count",
    "metrics_updated_at",
    "source",
    "local_images",
    "is_detail_collected",
    "is_merged_thread",
    # 내가 쓴 글인지. 저장글(남의 글)과 성격이 달라 뷰어 MY 필터와 갱신 정책이 갈린다.
    # source 로 대신하지 않는다 - source 는 수집 경로 값(opencli_shadow 등 8종)이라
    # 의미가 꼬인다. username 매칭도 LinkedIn 저장글이 불투명 ID(ACoAA...)라 취약하다.
    # 계획: _docs/20260826_03 (3.5)
    "is_own_post",
    # 내 북마크에 있는 글인지. 벤치마킹 계정 수집분(남의 계정을 통째로 긁은 것)과
    # 갈라야 뷰어가 "계정을 꺼도 내가 저장했던 글은 남긴다"를 판정할 수 있다.
    # source 로 대신하지 않는다 - 벤치마킹 글을 나중에 북마크하면 중복 제거에서
    # source 가 benchmark 인 채 남아 "저장글 아님"으로 오판한다.
    # 기본값이 True 인 이유는 defaults 주석 참조. 계획: _docs/20260906_01 (D14)
    "is_saved",
    # 이 글이 어느 벤치마킹 계정에서 왔나. 배열인 이유는 한 글이 두 계정에
    # 걸칠 수 있어서다(리포스트·공동출연). 계획: _docs/20260906_01 (D9-다)
    "benchmark_accounts",
    # 유튜브 채널 식별자(UC...). username 은 채널 표시명이라 계정 주소(@handle)와
    # 이어지지 않는다 - 실측으로 제어문자가 섞인 이름도 있었다(\x08헤이디_...).
    # 벤치마킹 계정과 게시물을 잇는 유일한 안정 키다. 계획: _docs/20260906_01 (D12)
    "channel_id",
]

REQUIRED_FIELDS = ["sns_platform", "username", "url", "created_at"]

LEGACY_FIELD_MAP = {
    "user": "username",
    "timestamp": "created_at",
    "post_url": "url",
    "source_url": "url",
}


def validate_post(post: dict) -> list[str]:
    """Return missing required fields for a post."""
    missing = [field for field in REQUIRED_FIELDS if not post.get(field)]
    if not post.get("full_text") and not post.get("media"):
        missing.append("full_text_or_media")
    return missing


def normalize_post(post: dict) -> dict:
    """Normalize legacy post keys into the current standard schema."""
    out = dict(post)

    for legacy, standard in LEGACY_FIELD_MAP.items():
        if legacy in out:
            if not out.get(standard):
                out[standard] = out[legacy]
            del out[legacy]

    if not out.get("platform_id") and out.get("code"):
        out["platform_id"] = out["code"]
    if not out.get("code") and out.get("platform_id"):
        out["code"] = out["platform_id"]

    if out.get("username") and not out.get("display_name"):
        out["display_name"] = out["username"]

    if out.get("created_at") and not out.get("date"):
        out["date"] = str(out["created_at"]).split(" ")[0]

    if out.get("sns_platform"):
        out["sns_platform"] = str(out["sns_platform"]).lower()

    platform = (out.get("sns_platform") or "").lower()
    if "thread" in platform and not out.get("url"):
        username = out.get("username")
        code = out.get("platform_id") or out.get("code")
        if username and code:
            out["url"] = f"https://www.threads.com/@{username}/post/{code}"

    defaults = {
        "media": [],
        "local_images": [],
        "is_detail_collected": False,
        "is_merged_thread": False,
        "like_count": None,
        "comment_count": None,
        "share_count": None,
        "quote_count": None,
        "bookmark_count": None,
        "view_count": None,
        # 지표를 마지막으로 읽은 시각(ISO 8601). crawled_at 은 본문 수집 시각이라
        # 대체할 수 없다 - 본문은 한 번 받으면 끝이지만 지표는 반복해서 읽는다.
        "metrics_updated_at": None,
        "is_own_post": False,
        # True 가 기본이다. 이 필드가 없던 시절의 레코드는 전부 내 북마크였다.
        # False 로 두면 뷰어의 `보임 = is_saved OR 켜진 벤치마킹 계정` 이 거짓이 되어
        # 기존 2,685 건이 통째로 화면에서 사라진다. 안전한 쪽을 기본값으로 둔다.
        "is_saved": True,
        "benchmark_accounts": [],
        "channel_id": "",
    }
    for field in STANDARD_FIELD_ORDER:
        if field in defaults and field not in out:
            out[field] = defaults[field]
        elif field not in defaults and field not in out:
            out[field] = ""

    ordered = {field: out[field] for field in STANDARD_FIELD_ORDER if field in out}
    for key, value in out.items():
        if key not in ordered:
            ordered[key] = value
    return ordered
