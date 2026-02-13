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


def parse_target(url):
    m = re.search(r"/@([^/]+)/post/([^/?#]+)", url)
    if not m:
        return None
    return {"url": url, "username": m.group(1), "code": m.group(2)}


async def scrape_target(context, target):
    page = await context.new_page()
    try:
        url = f"https://www.threads.net/@{target['username']}/post/{target['code']}"
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        await page.wait_for_timeout(3000)

        html = await page.content()
        data = extract_json_from_html(html)
        if not data:
            return {"target": target, "ok": False, "reason": "json_not_found", "items": []}

        items = data.get("data", {}).get("data", {}).get("thread_items", [])
        if not isinstance(items, list):
            return {"target": target, "ok": False, "reason": "thread_items_missing", "items": []}

        out = []
        for item in items:
            post = item.get("post", {}) or {}
            code = post.get("code")
            if not code:
                continue
            user = post.get("user", {}) or {}
            caption = post.get("caption", {}) or {}
            imgs = [c.get("url") for c in post.get("image_versions2", {}).get("candidates", [])[:1] if c.get("url")]

            out.append(
                {
                    "target_code": target["code"],
                    "root_code": target["code"],
                    "code": code,
                    "username": user.get("username"),
                    "full_text": caption.get("text", ""),
                    "images": imgs,
                    "taken_at": post.get("taken_at"),
                    "post_url": f"https://www.threads.com/@{user.get('username')}/post/{code}",
                }
            )

        dedup = {}
        for it in out:
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
            print(f"[{idx}/{len(targets)}] current-logic {target['username']}/{target['code']}")
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

    output = {"summary": summary, "results": results}
    out_file = RESULT_DIR / "thread_scrap_single_current_logic_result.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\nSaved:", out_file)
    print("Summary:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
