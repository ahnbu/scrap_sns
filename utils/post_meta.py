from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit


META_FIELDS = [
    "sequence_id",
    "post_key",
    "platform_id",
    "sns_platform",
    "code",
    "username",
    "display_name",
    "url",
    "canonical_url",
    "created_at",
    "date",
    "source",
    "full_text_preview",
    "full_text_length",
    "media_count",
    "local_images_count",
    "thumbnail",
    "is_detail_collected",
    "is_merged_thread",
]


def _normalize_threads_url(url: str) -> str:
    parsed = urlsplit(str(url))
    if not parsed.netloc:
        return str(url)
    if "threads" not in parsed.netloc:
        return str(url)
    return urlunsplit(
        ("https", "www.threads.com", parsed.path, parsed.query, parsed.fragment)
    )


def canonicalize_url(post: dict) -> str:
    raw_url = str(post.get("url") or post.get("post_url") or post.get("source_url") or "")
    platform = str(post.get("sns_platform") or "").lower()
    username = post.get("username") or post.get("user") or ""
    code = post.get("code") or post.get("platform_id") or ""

    if "thread" in platform:
        if username and code:
            return f"https://www.threads.com/@{username}/post/{code}"
        if raw_url:
            return _normalize_threads_url(raw_url)
    return raw_url


def normalize_post_key_platform(platform: str) -> str:
    value = str(platform or "").strip().lower()
    if value in {"thread", "threads"}:
        return "threads"
    if value == "linkedin":
        return "linkedin"
    if value in {"x", "twitter", "x/twitter", "x_twitter"}:
        return "x"
    return value


def build_post_key(post: dict) -> str:
    platform = normalize_post_key_platform(post.get("sns_platform"))
    identifier = post.get("platform_id") or post.get("code") or post.get("urn")
    if platform and identifier:
        return f"{platform}:{identifier}"

    canonical_url = canonicalize_url(post)
    if platform and canonical_url:
        return f"{platform}:url:{canonical_url}"
    if canonical_url:
        return f"url:{canonical_url}"
    return ""


def build_thumbnail(post: dict) -> str | None:
    local_images = post.get("local_images") or []
    media = post.get("media") or []
    if local_images:
        return local_images[0]
    if not media:
        return None
    first = media[0]
    if "wsrv.nl" in first or "licdn.com" in first:
        return first
    return f"https://wsrv.nl/?url={quote(first, safe='')}&output=webp"


def build_post_meta(post: dict) -> dict:
    full_text = str(post.get("full_text") or "")
    media = post.get("media") or []
    local_images = post.get("local_images") or []

    enriched = {
        **post,
        "post_key": build_post_key(post),
        "canonical_url": canonicalize_url(post),
        "full_text_preview": full_text[:200],
        "full_text_length": len(full_text),
        "media_count": len(media),
        "local_images_count": len(local_images),
        "thumbnail": build_thumbnail(post),
    }
    return {field: enriched.get(field) for field in META_FIELDS}
