import glob
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

from utils.post_schema import normalize_post, validate_post
from utils.threads_http_adapter import (
    build_threads_headers,
    fetch_thread_html,
    load_threads_cookies,
)
from utils.threads_parser import extract_items_multi_path, extract_json_from_html
from utils.auth_paths import threads_storage

# ==========================================
# ⚙️ Configuration
# ==========================================
OUTPUT_DIR = "output_threads/python"
SIMPLE_FILE_PATTERN = "threads_py_simple_*.json"
FULL_FILE_PATTERN = "threads_py_full_{date}.json"
FAILURES_FILE = "scrap_failures_threads.json"
AUTH_FILE = str(threads_storage())


# ==========================================
# 🛠️ Utility Functions
# ==========================================
def load_failures(path=FAILURES_FILE):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as file:
            try:
                return json.load(file)
            except Exception:
                return {}
    return {}


def save_failures(failures, path=FAILURES_FILE):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(failures, file, ensure_ascii=False, indent=4)


def get_post_code(post):
    """Legacy-safe code resolver for simple/full datasets."""
    code = post.get("code") or post.get("root_code") or post.get("platform_id")
    if code:
        return code

    url = post.get("url") or ""
    if url:
        try:
            path = urlparse(url).path.rstrip("/")
            if "/post/" in path:
                return path.split("/post/")[-1]
        except Exception:
            pass
    return None


def _assert_threads_schema(posts, context=""):
    """Validate threads records before persisting them."""
    bad = []
    for idx, post in enumerate(posts or []):
        if not isinstance(post, dict):
            continue
        if (post.get("sns_platform") or "").lower() not in ("thread", "threads"):
            continue
        missing = validate_post(post)
        if missing:
            bad.append((idx, post.get("platform_id") or post.get("code"), missing))
    if bad:
        first = bad[0]
        raise RuntimeError(
            f"[{context}] schema violation: {len(bad)} threads posts invalid. "
            f"first: idx={first[0]} code={first[1]} missing={first[2]}"
        )


def merge_thread_items(thread_items):
    """Merges multiple posts from the same thread into one single post data object."""
    if not thread_items:
        return None
    sorted_items = sorted(thread_items, key=lambda x: x.get("taken_at", 0))
    root = sorted_items[0]
    merged_text = "\n\n---\n\n".join(
        [item.get("full_text", "") for item in sorted_items if item.get("full_text")]
    )
    all_media = []
    seen_media = set()
    for item in sorted_items:
        for media in item.get("media", []):
            if media in seen_media:
                continue
            all_media.append(media)
            seen_media.add(media)

    merged_post = root.copy()
    merged_post["full_text"] = merged_text
    merged_post["media"] = all_media
    merged_post["is_merged_thread"] = True
    merged_post["original_item_count"] = len(sorted_items)
    return normalize_post(merged_post)


def promote_to_full_history(grouped_data, output_dir=OUTPUT_DIR):
    """수집된 타래 데이터를 최신 Full DB 파일로 병합 및 승격시킵니다."""
    if not grouped_data:
        return

    today = datetime.now().strftime("%Y%m%d")
    latest_full_path = os.path.join(output_dir, FULL_FILE_PATTERN.format(date=today))

    if not os.path.exists(latest_full_path):
        latest_full_path = import_from_simple_database(output_dir=output_dir)

    if not latest_full_path or not os.path.exists(latest_full_path):
        print("❌ [Promotion] 메인 Full 파일을 찾을 수 없습니다.")
        return

    with open(latest_full_path, "r", encoding="utf-8-sig") as file:
        full_content = json.load(file)

    posts = full_content.get("posts", [])
    merge_map = {}
    for root_code, items in grouped_data.items():
        merged = merge_thread_items(items)
        if merged:
            merge_map[root_code] = merged

    updated_count = 0
    new_posts = []
    max_sequence_id = full_content.get("metadata", {}).get("max_sequence_id", 0)

    for post in posts:
        code = post.get("code")
        if code in merge_map:
            merged_data = merge_map[code]
            merged_data["sequence_id"] = post.get("sequence_id")
            merged_data["crawled_at"] = post.get("crawled_at")
            new_posts.append(merged_data)
            updated_count += 1

            sequence_id = merged_data.get("sequence_id", 0)
            if sequence_id > max_sequence_id:
                max_sequence_id = sequence_id
        else:
            new_posts.append(post)

    if updated_count > 0:
        full_content["posts"] = new_posts
        full_content["metadata"].update(
            {
                "updated_at": datetime.now().isoformat(),
                "total_count": len(new_posts),
                "max_sequence_id": max_sequence_id,
            }
        )
        _assert_threads_schema(full_content["posts"], "promote")
        with open(latest_full_path, "w", encoding="utf-8-sig") as file:
            json.dump(full_content, file, ensure_ascii=False, indent=4)
        print(
            f"✅ [Promotion] {updated_count}개 타래 승격 완료: "
            f"{os.path.basename(latest_full_path)} (max_sequence_id: {max_sequence_id})"
        )


def import_from_simple_database(output_dir=OUTPUT_DIR):
    """Simple DB(목록)의 신규 데이터를 Full DB(상세)로 가져옵니다."""
    simple_files = glob.glob(os.path.join(output_dir, SIMPLE_FILE_PATTERN))
    if not simple_files:
        return None
    simple_files.sort(reverse=True)
    with open(simple_files[0], "r", encoding="utf-8-sig") as file:
        simple_data = json.load(file)

    today = datetime.now().strftime("%Y%m%d")
    today_full_path = os.path.join(output_dir, FULL_FILE_PATTERN.format(date=today))

    full_files = glob.glob(os.path.join(output_dir, "threads_py_full_*.json"))
    full_files.sort(reverse=True)

    full_content = {"metadata": {"version": "1.0", "total_count": 0, "max_sequence_id": 0}, "posts": []}
    if os.path.exists(today_full_path):
        with open(today_full_path, "r", encoding="utf-8-sig") as file:
            full_content = json.load(file)
    elif full_files:
        with open(full_files[0], "r", encoding="utf-8-sig") as file:
            full_content = json.load(file)

    full_posts = full_content.get("posts", [])
    existing_codes = {code for post in full_posts if (code := get_post_code(post))}

    simple_posts = simple_data.get("posts", [])
    max_sequence_id = simple_data.get("metadata", {}).get("max_sequence_id", 0)
    if not max_sequence_id and simple_posts:
        max_sequence_id = max(
            (post.get("sequence_id", 0) for post in simple_posts), default=0
        )

    new_items = []
    for post in simple_posts:
        code = get_post_code(post)
        if not code or code in existing_codes:
            continue
        new_item = post.copy()
        new_item["code"] = code
        new_item["is_merged_thread"] = False
        new_items.append(new_item)

    if new_items:
        for item in new_items:
            full_posts.insert(0, item)
            sequence_id = item.get("sequence_id", 0)
            if sequence_id > max_sequence_id:
                max_sequence_id = sequence_id

        full_content["posts"] = full_posts
        full_content["metadata"]["total_count"] = len(full_posts)
        full_content["metadata"]["max_sequence_id"] = max_sequence_id

        _assert_threads_schema(full_content["posts"], "import_simple")
        with open(today_full_path, "w", encoding="utf-8-sig") as file:
            json.dump(full_content, file, ensure_ascii=False, indent=4)
        print(
            f"✅ [Import] {len(new_items)}개 목록 가져옴: "
            f"{os.path.basename(today_full_path)} (max_sequence_id: {max_sequence_id})"
        )

    return today_full_path


def sync_detail_collected_flags(simple_path, full_path):
    """Synchronize is_detail_collected flags from simple DB to full DB."""
    if not simple_path or not full_path:
        return 0
    if not os.path.exists(simple_path) or not os.path.exists(full_path):
        return 0

    with open(simple_path, "r", encoding="utf-8-sig") as file:
        simple_data = json.load(file)
    with open(full_path, "r", encoding="utf-8-sig") as file:
        full_data = json.load(file)

    simple_posts = simple_data.get("posts", [])
    full_posts = full_data.get("posts", [])

    simple_done_codes = set()
    simple_changed = 0
    for post in simple_posts:
        code = get_post_code(post)
        if not code:
            continue
        if not post.get("code"):
            post["code"] = code
            simple_changed += 1
        if post.get("is_detail_collected") is True:
            simple_done_codes.add(code)

    full_changed = 0
    for post in full_posts:
        code = get_post_code(post)
        if not code:
            continue
        if code in simple_done_codes and post.get("is_detail_collected") is not True:
            post["is_detail_collected"] = True
            full_changed += 1

    if simple_changed > 0:
        _assert_threads_schema(simple_data.get("posts", []), "sync_simple")
        with open(simple_path, "w", encoding="utf-8-sig") as file:
            json.dump(simple_data, file, ensure_ascii=False, indent=4)

    if full_changed > 0:
        full_data["posts"] = full_posts
        full_data.setdefault("metadata", {})
        full_data["metadata"]["updated_at"] = datetime.now().isoformat()
        _assert_threads_schema(full_posts, "sync_full")
        with open(full_path, "w", encoding="utf-8-sig") as file:
            json.dump(full_data, file, ensure_ascii=False, indent=4)

    return full_changed


def collect_one(
    code,
    username,
    cookies,
    headers,
    fetch_fn=fetch_thread_html,
    snapshot_saver=None,
):
    url = f"https://www.threads.com/@{username}/post/{code}"
    result = fetch_fn(url, cookies=cookies, headers=headers)
    if not result:
        return []

    if snapshot_saver:
        try:
            snapshot_saver(result.html, "threads")
        except Exception:
            pass

    data = extract_json_from_html(result.html)
    if not data:
        return []
    return extract_items_multi_path(data, code, username)


def main(
    output_dir=OUTPUT_DIR,
    failures_file=FAILURES_FILE,
    auth_file=AUTH_FILE,
    cookie_loader=load_threads_cookies,
    header_builder=build_threads_headers,
    fetch_fn=fetch_thread_html,
    sleep_fn=time.sleep,
    max_workers=5,
    snapshot_saver=None,
):
    start_time = time.time()
    collected_data = []

    if snapshot_saver is None:
        try:
            from utils.common import save_debug_snapshot

            snapshot_saver = save_debug_snapshot
        except Exception:
            snapshot_saver = None

    latest_full_path = import_from_simple_database(output_dir=output_dir)
    failures = load_failures(failures_file)
    simple_files = sorted(
        glob.glob(os.path.join(output_dir, SIMPLE_FILE_PATTERN)), reverse=True
    )
    latest_simple = simple_files[0] if simple_files else None

    synced = sync_detail_collected_flags(latest_simple, latest_full_path)
    if synced > 0:
        print(f"[Sync] 상세 수집 상태 {synced}개를 full DB에 동기화했습니다.")

    target_codes = []
    skipped_done = 0
    skipped_invalid = 0
    skipped_fail_limit = 0
    if latest_full_path and os.path.exists(latest_full_path):
        with open(latest_full_path, "r", encoding="utf-8-sig") as file:
            full_data = json.load(file)
        for post in full_data.get("posts", []):
            code = get_post_code(post)
            if not code:
                skipped_invalid += 1
                continue
            if post.get("is_merged_thread"):
                continue
            if post.get("is_detail_collected") is True:
                skipped_done += 1
                continue
            if failures.get(code, {}).get("fail_count", 0) >= 3:
                skipped_fail_limit += 1
                continue
            target_codes.append(
                {
                    "code": code,
                    "username": post.get("user") or post.get("username"),
                    "url": post.get("url") or "",
                }
            )

    print(
        f"[Target] 수집대상 {len(target_codes)}개 | "
        f"기수집 스킵 {skipped_done}개 | 코드없음 스킵 {skipped_invalid}개 | "
        f"실패한도 스킵 {skipped_fail_limit}개"
    )

    if target_codes:
        cookies = cookie_loader(auth_file=auth_file)
        if not cookies:
            print(f"❌ Threads 인증 쿠키를 찾을 수 없습니다. {threads_storage()} 를 확인하세요.")
        else:
            headers = header_builder()
            total_targets = len(target_codes)
            completed = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(
                        collect_one,
                        target["code"],
                        target["username"],
                        cookies,
                        headers,
                        fetch_fn,
                        snapshot_saver,
                    ): target
                    for target in target_codes
                }
                for future in as_completed(future_map):
                    target = future_map[future]
                    code = target["code"]
                    try:
                        items = future.result()
                    except Exception:
                        items = []

                    if items:
                        collected_data.extend(items)
                        completed += 1
                        percent = int((completed / total_targets) * 100)
                        print(
                            f"   ✅ 수집 완료: [{code}] "
                            f"({completed}/{total_targets}, {percent}%)"
                        )
                    else:
                        print(f"   ⚠️ 수집 실패(추출 0건): [{code}]")
                    sleep_fn(0.3)
    else:
        print("✨ 수집할 새로운 타래가 없습니다.")

    scraped_codes = {item["root_code"] for item in collected_data}
    for code in scraped_codes:
        if code in failures:
            del failures[code]
    for target in target_codes:
        if target["code"] in scraped_codes:
            continue
        fail_info = failures.get(target["code"], {"fail_count": 0})
        fail_info["fail_count"] += 1
        if target.get("url"):
            fail_info["url"] = target["url"]
        failures[target["code"]] = fail_info
    save_failures(failures, failures_file)

    grouped = {}
    for item in collected_data:
        root_code = item["root_code"]
        grouped.setdefault(root_code, []).append(item)

    promote_to_full_history(grouped, output_dir=output_dir)

    if latest_simple and os.path.exists(latest_simple):
        with open(latest_simple, "r", encoding="utf-8-sig") as file:
            simple_data = json.load(file)
        simple_marked = 0
        for post in simple_data.get("posts", []):
            code = get_post_code(post)
            if code in scraped_codes and post.get("is_detail_collected") is not True:
                post["is_detail_collected"] = True
                simple_marked += 1
            if code and not post.get("code"):
                post["code"] = code
        _assert_threads_schema(simple_data.get("posts", []), "mark_collected")
        with open(latest_simple, "w", encoding="utf-8-sig") as file:
            json.dump(simple_data, file, ensure_ascii=False, indent=4)
        if simple_marked > 0:
            print(f"[Update] simple DB 상세수집 완료 {simple_marked}개 반영")
        synced_after = sync_detail_collected_flags(latest_simple, latest_full_path)
        if synced_after > 0:
            print(f"[Sync] 실행 후 full DB 상세수집 상태 {synced_after}개 반영")

    duration = time.time() - start_time
    print(f"\n🏁 Finished in {duration:.2f} seconds")


if __name__ == "__main__":
    main()
