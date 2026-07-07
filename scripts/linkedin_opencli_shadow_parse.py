import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.common import reorder_post
from utils.linkedin_parser import extract_urn_id, parse_linkedin_post


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as file:
        return json.load(file)


def save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def extract_entity_items(detail):
    body = detail.get("body") or {}
    included = body.get("included") or []
    return [
        item
        for item in included
        if item.get("$type") == "com.linkedin.voyager.dash.search.EntityResultViewModel"
    ]


def walk_values(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield value
            yield from walk_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield value
            yield from walk_values(value)


def extract_cluster_entity_result_urns(detail):
    cluster = (
        (detail.get("body") or {})
        .get("data", {})
        .get("data", {})
        .get("searchDashClustersByAll", {})
    )
    refs = set()
    for value in walk_values(cluster.get("elements") or []):
        if isinstance(value, dict):
            ref = value.get("*entityResult")
            if ref:
                refs.add(ref)
    return refs


def extract_save_state_activity_ids(detail):
    included = (detail.get("body") or {}).get("included") or []
    ids = set()
    for item in included:
        if item.get("$type") != "com.linkedin.voyager.dash.feed.SaveState":
            continue
        if item.get("saved") is False:
            continue
        text = f"{item.get('entityUrn', '')} {item.get('preDashEntityUrn', '')}"
        match = re.search(r"SAVE,urn:li:activity:(\d+)", text)
        if match:
            ids.add(match.group(1))
    return ids


def parse_shadow_detail(detail, raw_path, crawl_start_time, require_save_state=False):
    cluster_refs = extract_cluster_entity_result_urns(detail)
    save_state_ids = extract_save_state_activity_ids(detail)
    entity_items = extract_entity_items(detail)
    posts = []
    parser_failed = []
    entity_without_cluster_reference_count = 0
    entity_without_save_state_count = 0

    for item in entity_items:
        entity_urn = item.get("entityUrn", "")
        activity_id = extract_urn_id(entity_urn)
        has_cluster_ref = not cluster_refs or entity_urn in cluster_refs
        has_save_state = not save_state_ids or activity_id in save_state_ids

        if not has_cluster_ref:
            entity_without_cluster_reference_count += 1
        if not has_save_state:
            entity_without_save_state_count += 1
        if require_save_state and (not has_cluster_ref or not has_save_state):
            continue

        post = parse_linkedin_post(item, include_images=True, crawl_start_time=crawl_start_time)
        if not post:
            parser_failed.append(
                {
                    "raw_path": raw_path,
                    "entityUrn": entity_urn,
                }
            )
            continue

        post["diagnostics"] = {
            "saved_activity_id": activity_id if has_save_state else None,
            "entity_activity_id": activity_id,
            "embedded_activity_ids": [],
            "canonical_activity_id": activity_id,
            "save_state_verified": has_save_state,
            "cluster_reference_verified": has_cluster_ref,
        }
        posts.append(reorder_post(post))

    return {
        "metadata": {
            "cluster_entity_result_count": len(cluster_refs),
            "save_state_activity_count": len(save_state_ids),
            "entity_result_count": len(entity_items),
            "cluster_save_state_matched_post_count": len(posts),
            "entity_without_cluster_reference_count": entity_without_cluster_reference_count,
            "entity_without_save_state_count": entity_without_save_state_count,
            "parser_failed_count": len(parser_failed),
            "parser_failed": parser_failed,
        },
        "posts": posts,
    }


def parse_shadow_raw(raw_dir, crawl_start_time, require_save_state=False):
    raw_paths = sorted(glob.glob(os.path.join(raw_dir, "*.json")))
    posts_by_id = {}
    raw_entity_result_count = 0
    parser_failed = []
    cluster_entity_result_count = 0
    save_state_activity_count = 0
    cluster_save_state_matched_post_count = 0
    entity_without_cluster_reference_count = 0
    entity_without_save_state_count = 0

    for raw_path in raw_paths:
        detail = load_json(raw_path)
        result = parse_shadow_detail(
            detail,
            raw_path=raw_path,
            crawl_start_time=crawl_start_time,
            require_save_state=require_save_state,
        )
        metadata = result["metadata"]
        raw_entity_result_count += metadata["entity_result_count"]
        cluster_entity_result_count += metadata["cluster_entity_result_count"]
        save_state_activity_count += metadata["save_state_activity_count"]
        cluster_save_state_matched_post_count += metadata["cluster_save_state_matched_post_count"]
        entity_without_cluster_reference_count += metadata["entity_without_cluster_reference_count"]
        entity_without_save_state_count += metadata["entity_without_save_state_count"]
        parser_failed.extend(metadata["parser_failed"])

        for post in result["posts"]:
            platform_id = post.get("platform_id")
            if not platform_id or platform_id in posts_by_id:
                continue
            post["source"] = "opencli_shadow"
            posts_by_id[platform_id] = reorder_post(post)

    posts = list(posts_by_id.values())
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "raw_dir": raw_dir,
            "raw_file_count": len(raw_paths),
            "raw_entity_result_count": raw_entity_result_count,
            "cluster_entity_result_count": cluster_entity_result_count,
            "save_state_activity_count": save_state_activity_count,
            "cluster_save_state_matched_post_count": cluster_save_state_matched_post_count,
            "entity_without_cluster_reference_count": entity_without_cluster_reference_count,
            "entity_without_save_state_count": entity_without_save_state_count,
            "parsed_post_count": len(posts),
            "duplicate_platform_id_count": max(raw_entity_result_count - len(posts) - len(parser_failed), 0),
            "parser_failed_count": len(parser_failed),
            "parser_failed": parser_failed,
        },
        "posts": posts,
    }


def main():
    parser = argparse.ArgumentParser(description="Parse OpenCLI LinkedIn shadow GraphQL raw files.")
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--require-save-state", action="store_true")
    args = parser.parse_args()

    crawl_start_time = datetime.now()
    payload = parse_shadow_raw(args.raw_dir, crawl_start_time, require_save_state=args.require_save_state)
    stamp = crawl_start_time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.out, f"linkedin_opencli_shadow_{stamp}.json")
    save_json(out_path, payload)

    result = {
        "output_path": out_path,
        **payload["metadata"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
