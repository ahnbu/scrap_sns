import argparse
import glob
import json
import os
import time
from datetime import datetime

from utils.twitter_cli_adapter import (
    build_twitter_cli_env,
    fetch_tweet_detail,
    load_twitter_tokens,
)

OUTPUT_DIR = "output_twitter/python"
SIMPLE_FILE_PATTERN = "twitter_py_simple_*.json"
FULL_FILE_PATTERN = "twitter_py_full_{date}.json"
FAILURE_FILE = "scrap_failures_twitter.json"


def clean_text(text):
    if not text:
        return ""
    return text.strip()


def load_failures(path=FAILURE_FILE):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as file:
            try:
                return json.load(file)
            except Exception:
                return {}
    return {}


def save_failures(failures, path=FAILURE_FILE):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(failures, file, ensure_ascii=False, indent=4)


def normalize_target_url(url, pid):
    normalized_url = str(url)
    if normalized_url.endswith(f"/status/{pid}") and "/None/" in normalized_url:
        return f"https://x.com/i/status/{pid}"
    return url


def main(
    limit=0,
    output_dir=OUTPUT_DIR,
    failure_file=FAILURE_FILE,
    auth_dir="auth",
    token_loader=load_twitter_tokens,
    fetch_detail=fetch_tweet_detail,
    sleep_fn=time.sleep,
):
    failures = load_failures(failure_file)
    simple_files = glob.glob(os.path.join(output_dir, SIMPLE_FILE_PATTERN))
    if not simple_files:
        print("❌ Simple 파일을 찾을 수 없습니다.")
        return

    latest_simple = sorted(simple_files, reverse=True)[0]
    print(f"📂 목록 로드: {os.path.basename(latest_simple)}")
    with open(latest_simple, "r", encoding="utf-8-sig") as file:
        simple_data = json.load(file)

    posts = simple_data.get("posts", [])
    targets = []
    skipped_count = 0
    for post in posts:
        pid = str(post.get("platform_id") or post.get("id"))
        if post.get("is_detail_collected"):
            continue

        fail_info = failures.get(pid, {})
        if fail_info.get("count", 0) >= 3:
            skipped_count += 1
            continue
        targets.append(post)

    if skipped_count > 0:
        print(f"⏩ [Skip] {skipped_count}개 항목 제외 (3회 이상 실패)")
    if not targets:
        print("✨ 상세 수집할 새로운 항목이 없습니다. (메타데이터 동기화만 진행)")

    updated_count = 0
    if targets:
        if limit > 0:
            print(f"🎯 테스트 모드: {limit}개만 수집합니다.")
            targets = targets[:limit]

        tokens = token_loader(auth_dir=auth_dir)
        if not tokens:
            print("❌ twitter-cli 토큰을 찾을 수 없습니다. auth/x_cookies_*.json을 확인하세요.")
        else:
            env = build_twitter_cli_env(os.environ, tokens)
            total_targets = len(targets)
            print(f"🚀 총 {total_targets}개의 신규 항목 상세 수집 시작...")
            for index, post in enumerate(targets, start=1):
                pid = str(post.get("platform_id") or post.get("id"))
                url = normalize_target_url(post["url"], pid)
                user = post.get("username") or post.get("user")
                progress_percent = int((index / total_targets) * 100)
                progress_msg = f"({index}/{total_targets}, {progress_percent}%)"

                try:
                    detail = fetch_detail(url, user, env=env)
                except Exception:
                    detail = None
                if detail:
                    post["username"] = detail.real_user
                    post["url"] = f"https://x.com/{detail.real_user}/status/{pid}"
                    post["full_text"] = clean_text(detail.full_text)
                    post["media"] = list(
                        dict.fromkeys((post.get("media", []) or []) + detail.media)
                    )
                    post["is_detail_collected"] = True
                    post["source"] = "full_tweet_cli"
                    post["sns_platform"] = "x"
                    if not post.get("created_at"):
                        now = datetime.now()
                        post["created_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                        post["date"] = now.strftime("%Y-%m-%d")
                    if pid in failures:
                        del failures[pid]
                    updated_count += 1
                    print(f"   ✅ 수집 완료: @{detail.real_user} {progress_msg}")
                else:
                    fail_info = failures.get(pid, {"count": 0, "last_fail": ""})
                    fail_info["count"] += 1
                    fail_info["last_fail"] = datetime.now().isoformat()
                    fail_info["url"] = url
                    failures[pid] = fail_info
                    print(f"   ❌ 수집 실패 ({fail_info['count']}/3): {url} {progress_msg}")

                save_failures(failures, failure_file)
                sleep_fn(3)

    today = datetime.now().strftime("%Y%m%d")
    full_file = os.path.join(output_dir, FULL_FILE_PATTERN.format(date=today))

    all_full_posts = []
    max_sequence_id = 0
    if os.path.exists(full_file):
        with open(full_file, "r", encoding="utf-8-sig") as file:
            try:
                full_data_existing = json.load(file)
                all_full_posts = full_data_existing.get("posts", [])
                max_sequence_id = full_data_existing.get("metadata", {}).get(
                    "max_sequence_id", 0
                )
            except Exception:
                pass

    full_map = {
        str(post.get("platform_id") or post.get("id")): post for post in all_full_posts
    }
    for post in posts:
        if post.get("is_detail_collected"):
            pid = str(post.get("platform_id") or post.get("id"))
            if pid in full_map:
                full_map[pid].update(post)
            else:
                full_map[pid] = post

            sequence_id = post.get("sequence_id", 0)
            if sequence_id > max_sequence_id:
                max_sequence_id = sequence_id

    final_posts = sorted(
        full_map.values(), key=lambda item: item.get("sequence_id", 0), reverse=True
    )
    if final_posts:
        with open(full_file, "w", encoding="utf-8-sig") as file:
            json.dump(
                {
                    "metadata": {
                        "updated_at": datetime.now().isoformat(),
                        "total_count": len(final_posts),
                        "max_sequence_id": max_sequence_id,
                        "platform": "x",
                    },
                    "posts": final_posts,
                },
                file,
                ensure_ascii=False,
                indent=4,
            )
        print(
            f"📦 최종 상세 데이터 동기화 완료: {full_file} "
            f"(max_sequence_id: {max_sequence_id}, total: {len(final_posts)})"
        )

    if updated_count > 0:
        newly_updated_posts = [post for post in targets if post.get("is_detail_collected")]
        update_dir = os.path.join(output_dir, "update")
        os.makedirs(update_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(update_dir, f"twitter_py_full_update_{timestamp}.json")

        with open(update_file, "w", encoding="utf-8-sig") as file:
            json.dump(newly_updated_posts, file, ensure_ascii=False, indent=4)
        print(f"📂 상세 수집 업데이트 저장: {update_file} ({updated_count}개)")

    with open(latest_simple, "w", encoding="utf-8-sig") as file:
        json.dump(simple_data, file, ensure_ascii=False, indent=4)

    print(f"\n✨ 상세 수집 마감! 총 {updated_count}개 신규 갱신됨.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="X(Twitter) 상세 수집기")
    parser.add_argument("--limit", type=int, default=0, help="수집할 최대 개수 (0: 무제한)")
    args = parser.parse_args()
    main(limit=args.limit)
