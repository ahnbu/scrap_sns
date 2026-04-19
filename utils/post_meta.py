from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit


META_FIELDS = [
    "sequence_id",
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
        "canonical_url": canonicalize_url(post),
        "full_text_preview": full_text[:200],
        "full_text_length": len(full_text),
        "media_count": len(media),
        "local_images_count": len(local_images),
        "thumbnail": build_thumbnail(post),
    }
    return {field: enriched.get(field) for field in META_FIELDS}
