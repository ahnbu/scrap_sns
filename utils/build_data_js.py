"""Build web_viewer/data.js from the latest total_full JSON."""

import glob
import json
import os
import re
import sys

from utils.post_schema import validate_post


def build() -> None:
    files = sorted(
        path
        for path in glob.glob("output_total/total_full_*.json")
        if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
    )
    if not files:
        print("[ERROR] no total_full_*.json found", file=sys.stderr)
        raise SystemExit(1)

    latest = files[-1]
    with open(latest, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    posts = data.get("posts", data) if isinstance(data, dict) else data
    invalid = [
        (idx, post.get("platform_id") or post.get("code"), validate_post(post))
        for idx, post in enumerate(posts)
    ]
    invalid = [item for item in invalid if item[2]]
    if invalid:
        print(f"[ERROR] {len(invalid)}/{len(posts)} posts invalid", file=sys.stderr)
        for idx, code, missing in invalid[:5]:
            print(f"  idx={idx} code={code} missing={missing}", file=sys.stderr)
        raise SystemExit(1)

    content = "const snsFeedData = " + json.dumps(data, ensure_ascii=False, indent=2) + ";"
    with open("web_viewer/data.js", "w", encoding="utf-8-sig") as f:
        f.write(content)
    print(f"OK: {len(posts)} posts → web_viewer/data.js (source: {latest})")


if __name__ == "__main__":
    build()
