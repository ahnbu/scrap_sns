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
    "source",
    "local_images",
    "is_detail_collected",
    "is_merged_thread",
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
