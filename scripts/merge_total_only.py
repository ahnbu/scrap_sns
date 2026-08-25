"""Rebuild output_total from the existing platform files, without collecting.

``total_scrap.py --mode update`` runs the full pipeline: it launches every
platform producer and consumer first, and only then merges. When you have
already edited the platform files by hand and just want the merged view
refreshed, that is the wrong tool -- the collectors run against the live sites,
and a consumer run bumps ``fail_count`` in the failure ledgers, which can push
records past the 3-strike limit and drop them from all future collection.

This runs only the tail of that pipeline: merge -> image download -> save.
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from total_scrap import (  # noqa: E402
    collect_existing_post_state,
    download_images,
    merge_results,
    preserve_existing_local_images,
    save_total,
    select_image_download_posts,
)


def main():
    parser = argparse.ArgumentParser(
        description="Merge existing platform files into output_total (no collection)."
    )
    parser.add_argument(
        "--mode",
        choices=["all", "update"],
        default="update",
        help="Matches total_scrap semantics for image selection and link validation.",
    )
    args = parser.parse_args()

    existing_post_keys, existing_local_images = (
        collect_existing_post_state() if args.mode == "update" else (set(), {})
    )

    merged = merge_results()
    posts = merged[0]
    if not posts:
        print("❌ 병합할 게시글이 없습니다.")
        return 1

    posts, threads_count, linkedin_count, twitter_count, youtube_count = merged
    preserve_existing_local_images(posts, existing_local_images)

    image_posts = select_image_download_posts(posts, args.mode, existing_post_keys)
    download_images(image_posts)

    save_total(
        posts,
        threads_count,
        linkedin_count,
        twitter_count,
        youtube_count,
        local_image_link_posts=image_posts if args.mode == "update" else posts,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
