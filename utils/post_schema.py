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
