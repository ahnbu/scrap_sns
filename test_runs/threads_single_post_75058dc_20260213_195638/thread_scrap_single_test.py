import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

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
            found = find_master_pk_recursive(v, username)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_master_pk_recursive(item, username)
            if found:
                return found
    return None


def parse_target(url):
    m = re.search(r"/@([^/]+)/post/([^/?#]+)", url)
    if not m:
        return None
    return {"url": url, "username": m.group(1), "code": m.group(2)}


def extract_items_from_node(node, target_code, master_pk=None):
    if not node:
        return []

    thread_items = node.get("thread_items", [])
    if thread_items:
        posts = [item.get("post", {}) for item in thread_items]
    else:
        post = node.get("post") or node
        posts = [post]

    if not posts:
        return []

    root_post = posts[0]
    root_code = root_post.get("code")
    root_user_pk = root_post.get("user", {}).get("pk")
    if not root_code:
        return []

    out = []
    for idx, post in enumerate(posts):
        code = post.get("code")
        if not code:
            continue

        # 최소 수정 패치:
        # 1) URL 주인(master_pk) 불일치 글 제외
        # 2) 루트 작성자와 다른 작성자 제외
        current_user_pk = post.get("user", {}).get("pk")
        if master_pk and current_user_pk != master_pk:
            continue
        if root_user_pk and current_user_pk != root_user_pk:
            continue

        # 3) 타래 답글이 루트 작성자에게 달린 글인지 확인
        if idx > 0:
            info = post.get("text_post_app_info", {})
            reply_to_author_id = info.get("reply_to_author", {}).get("id")
            if reply_to_author_id and root_user_pk and reply_to_author_id != root_user_pk:
                continue

        user = post.get("user", {}) or {}
        caption = post.get("caption", {}) or {}
        imgs = [c.get("url") for c in post.get("image_versions2", {}).get("candidates", [])[:1] if c.get("url")]

        out.append(
            {
                "code": code,
                "root_code": target_code,
                "user": user.get("username"),
                "full_text": caption.get("text", ""),
                "media": imgs,
                "taken_at": post.get("taken_at"),
                "timestamp": post.get("taken_at"),
                "sns_platform": "threads",
                "post_url": f"https://www.threads.com/@{user.get('username')}/post/{code}",
            }
        )

    return out


def extract_items_multi_path(data, target_code, target_username):
    # 기존 코드의 실패 지점: data.data.thread_items 단일 경로 의존
    # 최소 수정: edges / containing_thread / thread_items 3경로 폴백
    inner = data.get("data", {}).get("data")
    if not isinstance(inner, dict):
        return []

    master_pk = find_master_pk_recursive(data, target_username)
    extracted = []

    direct_items = inner.get("thread_items")
    if isinstance(direct_items, list) and direct_items:
        extracted.extend(extract_items_from_node(inner, target_code, master_pk))

    edges = inner.get("edges")
    if isinstance(edges, list) and edges:
        for edge in edges:
            extracted.extend(extract_items_from_node(edge.get("node", {}), target_code, master_pk))

    containing_thread = inner.get("containing_thread")
    if isinstance(containing_thread, dict) and containing_thread:
        extracted.extend(extract_items_from_node(containing_thread, target_code, master_pk))

    dedup = {}
    for item in extracted:
        dedup[item["code"]] = item
    return list(dedup.values())


async def scrape_target(context, target):
    page = await context.new_page()
    try:
        # 현재 파일 동작과 맞춰 threads.net 도메인으로 접근
        url = f"https://www.threads.net/@{target['username']}/post/{target['code']}"
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollBy(0, 1000)")
        await page.wait_for_timeout(1500)

        html = await page.content()
        data = extract_json_from_html(html)
        if not data:
            return {"target": target, "ok": False, "reason": "json_not_found", "items": []}

        items = extract_items_multi_path(data, target["code"], target["username"])
        return {
            "target": target,
            "ok": len(items) > 0,
            "reason": "ok" if items else "no_items_extracted",
            "items": items,
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
            print(f"[{idx}/{len(targets)}] patched-test {target['username']}/{target['code']}")
            r = await scrape_target(context, target)
            results.append(r)
            print(f"  -> {r['reason']} | items={len(r['items'])}")

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

    output = {"summary": summary, "results": results}
    out_file = RESULT_DIR / "thread_scrap_single_test_result.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\nSaved:", out_file)
    print("Summary:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
