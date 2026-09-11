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
    "like_count",
    "comment_count",
    "share_count",
    "quote_count",
    "bookmark_count",
    "view_count",
    # 지표를 "언제 읽은 값"인지 카드에 표시하려면 목록 응답에 실려야 한다.
    # 이 목록에 없으면 /api/posts 가 값을 떨어뜨려 뷰어가 볼 수 없다.
    # 계획: _docs/20260826_02 (W3)
    "metrics_updated_at",
    # 뷰어 MY 필터가 이 값으로 내 글을 가려낸다. 이 목록에 없으면 /api/posts 가
    # 필드를 떨어뜨려 프런트에서 항상 undefined 가 되고 필터가 조용히 무동작한다.
    # 계획: _docs/20260826_03 (3.9 T9)
    "is_own_post",
    # 벤치마킹 표시·필터가 이 셋을 쓴다. 위 is_own_post 와 같은 함정이다 -
    # 이 목록에 없으면 /api/posts 가 값을 떨어뜨려 프런트가 항상 undefined 를 보고
    # `보임 = is_saved OR 켜진 계정` 이 전건 거짓이 된다(화면 백지).
    # 계획: _docs/20260906_01 (D16)
    "is_saved",
    "benchmark_accounts",
    "channel_id",
    # 유튜브 카드가 "요약이 왜 없는지"를 한 줄로 그리려면 이 둘이 목록 응답에
    # 실려야 한다. 위 is_own_post·is_saved 와 똑같은 함정이다 - 이 목록에 없으면
    # /api/posts 가 값을 떨어뜨려 프런트가 항상 undefined 를 보고 사유 줄이
    # 통째로 안 뜬다. 표시 문자열을 수집 데이터에 넣지 않고 뷰어에서 그리므로
    # 이 두 상태값이 유일한 근거다. 계획: _docs/20260909_01 (W2 T2-a)
    "transcript_status",
    "summary_status",
    # 볼트 자료 카드(〈웹〉·〈파일〉)가 쓰는 값. 위 is_own_post 와 같은 함정이다 -
    # 이 목록에 없으면 /api/posts 가 값을 떨어뜨려 카드 제목·주제·옵시디언 링크가
    # 조용히 사라진다. 값의 출처는 utils/library_index.note_to_post().
    # sort_seq 는 「로컬수집순」 자리(자료를 SNS 수집 시각 사이에 끼운다),
    # library_notes 는 원문 SNS 카드에 붙는 겹침 요약본 목록(「요약」 배지).
    # 계획: _docs/20260911_01 (W2 T2-d, W3)
    "library_title",
    "library_path",
    "library_topic",
    "library_tags",
    "library_source_type",
    "library_creator",
    "library_obsidian_url",
    "library_has_source_file",
    "library_source_file_url",
    "sort_seq",
    "library_notes",
    # 이름 옆 아이콘이 모든 카드에서 사람 카드를 열려면 이 둘이 실려야 한다.
    # creator_id 는 제작자 레지스트리 판정 결과(utils/creator_registry), profile_slogan 은
    # 링크드인 저자 한 줄 소개(731/769건 보유) - 연결 없는 저자 카드가 비지 않게 한다.
    # 계획: _docs/20260911_01 (W4 T4-c·T4-e)
    "creator_id",
    "profile_slogan",
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


PREVIEW_CHARS = 200
# 자료 카드(web·file)는 미리보기에서 첫 제목·구분선·마크다운 기호를 걷고 줄바꿈을 살려
# 6줄을 보인다. 200자로는 걷어낸 뒤 3줄도 안 남는다. 계획: _docs/20260911_02 (W4 T4-c)
LIBRARY_PREVIEW_CHARS = 600


def build_post_meta(post: dict) -> dict:
    full_text = str(post.get("full_text") or "")
    media = post.get("media") or []
    local_images = post.get("local_images") or []
    is_library = str(post.get("sns_platform") or "").lower() in ("web", "file")

    enriched = {
        **post,
        "post_key": build_post_key(post),
        "canonical_url": canonicalize_url(post),
        "full_text_preview": full_text[:LIBRARY_PREVIEW_CHARS if is_library else PREVIEW_CHARS],
        "full_text_length": len(full_text),
        "media_count": len(media),
        "local_images_count": len(local_images),
        "thumbnail": build_thumbnail(post),
        # 필드가 없는 레코드에도 안전한 값을 준다. normalize_post() 의 defaults 에만
        # 기대면 안 된다 - 뷰어는 이미 만들어진 통합본을 그대로 읽고, 그 파일에는
        # is_saved 가 없다. None 이 나가면 프런트의 `보임 = is_saved OR 켜진 계정` 이
        # 전건 거짓이 되어 화면이 통째로 빈다. 계획: _docs/20260906_01 (D14)
        "is_saved": post.get("is_saved", True),
        "benchmark_accounts": post.get("benchmark_accounts") or [],
        "channel_id": post.get("channel_id") or "",
    }
    return {field: enriched.get(field) for field in META_FIELDS}
