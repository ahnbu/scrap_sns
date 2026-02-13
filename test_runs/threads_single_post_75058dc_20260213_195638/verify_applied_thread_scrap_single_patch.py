import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import thread_scrap_single as tss

WORK_DIR = Path(__file__).resolve().parent
RESULT_DIR = WORK_DIR / "results"
TARGETS_FILE = WORK_DIR / "targets.json"
AUTH_FILE = ROOT / "auth" / "auth_threads.json"

HEADLESS = True
TIMEOUT_MS = 45000


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
        await page.evaluate("window.scrollBy(0, 1000)")
        await page.wait_for_timeout(1500)

        html = await page.content()
        data = tss.extract_json_from_html(html)
        if not data:
            return {"target": target, "ok": False, "reason": "json_not_found", "items": []}

        items = tss.extract_items_multi_path(data, target["code"], target["username"])
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
            print(f"[{idx}/{len(targets)}] verify-applied {target['username']}/{target['code']}")
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
    out_file = RESULT_DIR / "verify_applied_thread_scrap_single_patch_result.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\nSaved:", out_file)
    print("Summary:", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
