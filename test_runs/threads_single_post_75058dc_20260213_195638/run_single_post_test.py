import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
WORK_DIR = Path(__file__).resolve().parent
RESULT_DIR = WORK_DIR / "results"
TARGETS_FILE = WORK_DIR / "targets.json"
AUTH_FILE = ROOT / "auth" / "auth_threads.json"

HEADLESS = True
TIMEOUT_MS = 45000


def extract_json_from_html(html_content):
    if "thread_items" not in html_content:
        return None

    ti_idx = html_content.find("thread_items")
    marker = '"result":{"data"'
    idx = html_content.rfind(marker, 0, ti_idx)
    if idx == -1:
        return None

    start_obj = idx + 9
    brace_count = 0
    json_str = ""

    for i in range(start_obj, len(html_content)):
        ch = html_content[i]
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
        json_str += ch
        if brace_count == 0 and ch == "}":
            break

    try:
        return json.loads(json_str)
    except Exception:
        return None


def find_master_pk_recursive(data, username):
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


def parse_target(url):
    m = re.search(r"/@([^/]+)/post/([^/?#]+)", url)
    if not m:
        return None
    return {"url": url, "username": m.group(1), "code": m.group(2)}


def process_node(node, master_pk, target_code):
    if not node:
        return []

    posts_to_process = []
    thread_items = node.get("thread_items", [])
    if thread_items:
        posts_to_process = [item.get("post", {}) for item in thread_items]
    else:
        post = node.get("post") or node
        posts_to_process = [post]

    if not posts_to_process:
        return []

    root_post = posts_to_process[0]
    root_code = root_post.get("code")
    root_user_pk = root_post.get("user", {}).get("pk")
    if not root_code:
        return []

    out = []
    for i, post in enumerate(posts_to_process):
        p_code = post.get("code")
        if not p_code:
            continue

        current_user_pk = post.get("user", {}).get("pk")
        if master_pk and current_user_pk != master_pk:
            continue
        if current_user_pk != root_user_pk:
            continue

        if i > 0:
            text_post_app_info = post.get("text_post_app_info", {})
            reply_to_author_id = text_post_app_info.get("reply_to_author", {}).get("id")
            if reply_to_author_id and reply_to_author_id != root_user_pk:
                continue

        images = []
        candidates = post.get("image_versions2", {}).get("candidates", [])
        if candidates:
            images.append(candidates[0].get("url"))

        caption = post.get("caption", {}) or {}
        user = post.get("user", {}) or {}

        out.append(
            {
                "target_code": target_code,
                "root_code": root_code,
                "code": p_code,
                "username": user.get("username"),
                "full_text": caption.get("text", ""),
                "images": [u for u in images if u],
                "taken_at": post.get("taken_at"),
                "post_url": f"https://www.threads.com/@{user.get('username')}/post/{p_code}",
            }
        )

    return out


async def scrape_target(context, target):
    page = await context.new_page()
    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        await page.wait_for_timeout(3500)
        await page.evaluate("window.scrollBy(0, 900)")
        await page.wait_for_timeout(1500)

        html = await page.content()
        data = extract_json_from_html(html)
        if not data:
            return {"target": target, "ok": False, "reason": "json_not_found", "items": []}

        inner_data = data.get("data", {}).get("data")
        if not inner_data:
            return {"target": target, "ok": False, "reason": "invalid_json_structure", "items": []}

        master_pk = find_master_pk_recursive(data, target["username"])

        items = []
        if isinstance(inner_data, dict) and "edges" in inner_data:
            for edge in inner_data.get("edges", []):
                items.extend(process_node(edge.get("node", {}), master_pk, target["code"]))
        elif isinstance(inner_data, dict) and "containing_thread" in inner_data:
            items.extend(process_node(inner_data.get("containing_thread", {}), master_pk, target["code"]))
        elif isinstance(inner_data, dict) and "thread_items" in inner_data:
            items.extend(process_node(inner_data, master_pk, target["code"]))

        dedup = {}
        for it in items:
            dedup[it["code"]] = it
        final_items = list(dedup.values())

        return {
            "target": target,
            "ok": len(final_items) > 0,
            "reason": "ok" if final_items else "no_items_extracted",
            "items": final_items,
        }
    except Exception as e:
        return {"target": target, "ok": False, "reason": str(e), "items": []}
    finally:
        await page.close()


async def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    with TARGETS_FILE.open("r", encoding="utf-8") as f:
        urls = json.load(f)

    targets = [parse_target(u) for u in urls]
    targets = [t for t in targets if t]

    storage_state = str(AUTH_FILE) if AUTH_FILE.exists() else None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(storage_state=storage_state)

        results = []
        for idx, target in enumerate(targets, 1):
            print(f"[{idx}/{len(targets)}] testing {target['username']}/{target['code']}")
            result = await scrape_target(context, target)
            results.append(result)
            print(f"  -> {result['reason']} | items={len(result['items'])}")

        await browser.close()

    all_items = []
    for r in results:
        all_items.extend(r["items"])

    summary = {
        "checked_at": datetime.now().isoformat(),
        "targets": len(results),
        "success_targets": sum(1 for r in results if r["ok"]),
        "failed_targets": sum(1 for r in results if not r["ok"]),
        "total_items": len(all_items),
    }

    output = {
        "summary": summary,
        "results": results,
    }

    out_file = RESULT_DIR / "scrap_single_post_test_result.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\nSaved:", out_file)
    print("Summary:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
