import json
from datetime import datetime
from urllib.parse import urlparse
from utils.common import format_timestamp


def _extract_balanced_json_object(text, start_idx):
    """Return a JSON object span while ignoring braces inside strings."""
    brace_count = 0
    in_string = False
    escaped = False

    for idx in range(start_idx, len(text)):
        char = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[start_idx : idx + 1]

    return None


def extract_json_from_html(html_content):
    """Robustly extracts specific JSON data from Threads HTML"""
    if "thread_items" not in html_content: return None
    ti_idx = html_content.find("thread_items")
    
    # Threads has various markers depending on the version
    marker = '"result":{"data"'
    idx = html_content.rfind(marker, 0, ti_idx)
    if idx == -1: return None
    
    # Find the start of the JSON object (the first '{' after the marker)
    start_obj = html_content.find('{', idx + len(marker) - 5) # Look around "data" area
    if start_obj == -1: return None

    json_str = _extract_balanced_json_object(html_content, start_obj)
    if not json_str:
        return None
    
    try: 
        # result is a dictionary that contains "data" or similar
        return json.loads(json_str)
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        return None

RESULT_DATA_MARKER = '"result":{"data"'


def iter_result_data_blocks(html_content):
    """Yield every parsed ``"result":{"data" ...}`` block in the page.

    The old response shape put the whole thread in one block, so
    ``extract_json_from_html`` only ever looked at one. The current shape
    spreads a single post across five blocks - one holds the post body,
    another holds the reply/self-thread tree - so callers need all of them.
    Blocks that fail to parse are skipped rather than aborting the scan.
    """
    if not html_content:
        return

    idx = 0
    while True:
        idx = html_content.find(RESULT_DATA_MARKER, idx)
        if idx == -1:
            return
        start_obj = html_content.find("{", idx + len(RESULT_DATA_MARKER) - 5)
        idx += len(RESULT_DATA_MARKER)
        if start_obj == -1:
            continue
        json_str = _extract_balanced_json_object(html_content, start_obj)
        if not json_str:
            continue
        try:
            yield json.loads(json_str)
        except Exception:
            continue


def _is_detail_media(media):
    """A block holds the requested post only if its media carries the body."""
    if not isinstance(media, dict):
        return False
    if "caption" not in media or not media.get("code"):
        return False
    return bool((media.get("user") or {}).get("username"))


def select_detail_media(blocks, target_code=None, username=None):
    """Pick the block holding the requested post, or None when ambiguous.

    Block order is not stable - across 42 captured pages the body block sat at
    index 0, 1 or 2 - so position must never decide. Every one of those pages
    had exactly one block satisfying ``_is_detail_media``. When more than one
    somehow matches, fall back to the requested code and then the requested
    username; if neither disambiguates, return None so the fetch is recorded as
    a failure. Guessing here is what produced the author/body contamination
    that ``utils/twitter_cli_adapter.select_focal_tweet`` had to be hardened
    against.
    """
    candidates = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        media = block.get("media")
        if _is_detail_media(media):
            candidates.append(media)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    by_code = [m for m in candidates if m.get("code") == target_code]
    if len(by_code) == 1:
        return by_code[0]
    by_user = [m for m in candidates if (m.get("user") or {}).get("username") == username]
    if len(by_user) == 1:
        return by_user[0]
    return None


def collect_self_thread_nodes(blocks, media_id, root_username):
    """Return the author's own follow-up posts for the selected media.

    The chain lives under ``text_post_app_info.self_thread`` on a block whose
    ``media.id`` matches the body block. ``direct_replies`` sits right next to
    it and holds other people's posts, so it is never read.
    """
    if not media_id:
        return []

    nodes = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        media = block.get("media")
        if not isinstance(media, dict) or media.get("id") != media_id:
            continue
        text_post_app_info = media.get("text_post_app_info") or {}
        self_thread = text_post_app_info.get("self_thread") or {}
        edges = (self_thread.get("posts") or {}).get("edges") or []
        for edge in edges:
            node = (edge or {}).get("node")
            if not isinstance(node, dict):
                continue
            if (node.get("user") or {}).get("username") != root_username:
                continue
            nodes.append(node)
    return nodes


def extract_items_from_media_html(html_content, target_code, username):
    """Extract posts from the current ``data.media`` response shape.

    Used when ``extract_json_from_html`` finds no ``thread_items`` anchor. The
    author-consistency filter keys off the selected root's own ``user.pk``
    rather than the requested username, because a repost redirects to the
    original and the requested username is then absent from the payload.
    """
    blocks = list(iter_result_data_blocks(html_content))
    if not blocks:
        return []

    root_media = select_detail_media(blocks, target_code, username)
    if not root_media:
        return []

    root_user = root_media.get("user") or {}
    root_username = root_user.get("username")
    master_pk = root_user.get("pk")

    extracted = extract_posts_from_node(root_media, target_code, master_pk)
    for node in collect_self_thread_nodes(blocks, root_media.get("id"), root_username):
        extracted.extend(extract_posts_from_node(node, target_code, master_pk))

    dedup = {}
    for item in extracted:
        code = item.get("code")
        if code:
            dedup[code] = item
    return list(dedup.values())


def find_master_pk_recursive(data, username):
    """Recursively search the user pk matching URL username."""
    if not username:
        return None
    if isinstance(data, dict):
        if data.get("username") == username:
            return data.get("pk")
        for v in data.values():
            res = find_master_pk_recursive(v, username)
            if res:
                return res
    elif isinstance(data, list):
        for item in data:
            res = find_master_pk_recursive(item, username)
            if res:
                return res
    return None

def extract_posts_from_node(node, target_code, master_pk):
    """Extract posts from a node with author consistency filters."""
    if not isinstance(node, dict):
        return []

    thread_items = node.get("thread_items", [])
    if thread_items:
        posts_to_process = [item.get("post", {}) for item in thread_items]
    else:
        post = node.get("post") or node
        posts_to_process = [post]

    if not posts_to_process:
        return []

    root_post = posts_to_process[0]
    root_user_pk = (root_post.get("user") or {}).get("pk")
    if not root_post.get("code"):
        return []

    extracted = []
    for i, post in enumerate(posts_to_process):
        if not isinstance(post, dict):
            continue
        code = post.get("code")
        if not code:
            continue

        current_user_pk = (post.get("user") or {}).get("pk")
        if master_pk and current_user_pk != master_pk:
            continue
        if root_user_pk and current_user_pk != root_user_pk:
            continue

        if i > 0:
            text_post_app_info = post.get("text_post_app_info") or {}
            reply_to_author = text_post_app_info.get("reply_to_author") or {}
            reply_to_author_id = reply_to_author.get("id")
            if reply_to_author_id and root_user_pk and reply_to_author_id != root_user_pk:
                continue

        user = post.get("user") or {}
        username = user.get("username")
        caption = post.get("caption") or {}
        image_versions = post.get("image_versions2") or {}
        candidates = image_versions.get("candidates") or []
        created_at, created_date = format_timestamp(post.get("taken_at"))
        item = {
            "platform_id": code,
            "code": code,
            "root_code": target_code,
            "username": username,
            "display_name": user.get("full_name") or username,
            "full_text": caption.get("text", ""),
            "media": [c.get("url") for c in candidates[:1] if c.get("url")],
            "url": f"https://www.threads.com/@{username}/post/{code}" if username else "",
            "created_at": created_at,
            "date": created_date,
            "sns_platform": "threads",
            "source": "consumer_detail",
            "pk": post.get("pk"),
            "taken_at": post.get("taken_at"),
        }
        item.update(extract_engagement_metrics(post))
        extracted.append(item)
    return extracted


# Threads 원본 지표명 -> 공통 스키마명 (utils/post_schema.py STANDARD_FIELD_ORDER 기준).
# reply_count / repost_count 는 2026-08-24에 폐기된 옛 이름이므로 쓰지 않는다.
THREADS_METRIC_FIELD_MAP = {
    "like_count": "like_count",
    "direct_reply_count": "comment_count",
    "repost_count": "share_count",
    "quote_count": "quote_count",
}


def extract_engagement_metrics(post):
    """상세 응답(data.media)의 참여지표를 공통 스키마 필드명으로 뽑는다.

    값이 없거나 정수로 해석되지 않으면 그 필드를 생략한다 - 키를 만들지 않아야
    normalize_post 가 None 기본값을 넣고, 병합 단계의 보존 가드가 기존값을 지킨다.
    음수는 과거 DOM 경로가 쓰던 '값 없음' 표식이므로 버린다.
    """
    if not isinstance(post, dict):
        return {}

    metrics = {}
    text_post_app_info = post.get("text_post_app_info") or {}
    for source_key, schema_key in THREADS_METRIC_FIELD_MAP.items():
        value = post.get(source_key)
        if value is None and isinstance(text_post_app_info, dict):
            value = text_post_app_info.get(source_key)
        if value is None or isinstance(value, bool):
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number < 0:
            continue
        metrics[schema_key] = number

    # 값이 하나라도 잡혔을 때만 읽은 시각을 남긴다. 이 필드가 없으면
    # 일자별 파일에서 "안 변한 것"과 "안 읽은 것"을 구분할 수 없다 -
    # 재수집하지 않은 글도 병합 과정에서 같은 값이 그대로 복사돼 실리기 때문이다.
    # 계획: _docs/20260826_02 (P4, W3)
    if metrics:
        metrics["metrics_updated_at"] = datetime.now().isoformat(timespec="milliseconds")
    return metrics

def extract_items_multi_path(data, target_code, username):
    """
    Fallback extraction path for Threads payload:
    1) data.data.data.thread_items (Direct API)
    2) data.result.data.data.thread_items (Embedded in HTML)
    """
    if not isinstance(data, dict):
        return []

    # Try various root paths
    inner_data = None
    if "result" in data:
        inner_data = data.get("result", {}).get("data", {}).get("data")
    elif "data" in data:
        # Could be data.data.data or just data.data
        d = data.get("data", {})
        if "data" in d:
            inner_data = d.get("data")
        else:
            inner_data = d

    if not isinstance(inner_data, dict):
        # Last resort: use data itself if it contains thread_items
        if "thread_items" in data:
            inner_data = data
        else:
            return []

    master_pk = find_master_pk_recursive(data, username)
    extracted = []

    thread_items = inner_data.get("thread_items")
    if isinstance(thread_items, list) and thread_items:
        extracted.extend(extract_posts_from_node(inner_data, target_code, master_pk))

    edges = inner_data.get("edges")
    if isinstance(edges, list):
        for edge in edges:
            extracted.extend(extract_posts_from_node(edge.get("node", {}), target_code, master_pk))

    containing_thread = inner_data.get("containing_thread")
    if isinstance(containing_thread, dict):
        extracted.extend(extract_posts_from_node(containing_thread, target_code, master_pk))

    dedup = {}
    for item in extracted:
        dedup[item.get("code")] = item
    return [v for v in dedup.values() if v.get("code")]
