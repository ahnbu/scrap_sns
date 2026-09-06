"""벤치마킹 계정의 Threads 글을 계정 단위로 수집한다.

왜 이 파일이 필요한가
---------------------
SPEC(_docs/specs/20260906_01) §64 가 *"계정 단위 수집기 부재 — YouTube·Threads·X 는
없다"* 고 적었고, 그것이 Threads 를 1차에서 뺀 근거였다. **그 제약은 사실이 아니다.**

실측(2026-09-06): 비로그인 계정 페이지가 200 을 주고, 그 HTML 안에 Meta 의
embedded JSON(`thread_items`·`taken_at`·`like_count`·`caption`)이 그대로 들어 있다.
이 레포의 `utils/threads_parser.py` 가 이미 그 구조를 파싱한다 - 저장글 수집에
쓰는 바로 그 함수들이다. 그래서 새로 만들 것은 수집기가 아니라 연결부뿐이다.

가져오기는 `scrap-my` 스킬의 scrapling 경로(stealthy-fetch)를 그대로 쓴다.
그쪽이 Threads 를 화이트리스트로 갖고 있고 fetcher 선택이 이미 검증돼 있다.

계획: _docs/20260906_03 (W4)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime

from utils.common import load_json, save_json
from utils.post_schema import normalize_post
from utils.threads_parser import iter_result_data_blocks, extract_posts_from_node

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(PROJECT_ROOT, "web_viewer", "benchmark_accounts.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output_threads_user", "python")
SCRAPLING_RUNNER = os.path.join(
    os.path.expanduser("~"), ".claude", "skills", "scrap-my",
    "scripts", "run-scrapling-extract.mjs",
)
DEFAULT_LIMIT = 5


def load_active_threads_accounts():
    """켜져 있고 Threads 주소가 있는 계정만."""
    override = os.environ.get("SNS_BENCHMARK_ACCOUNTS_PATH", "").strip()
    path = os.path.abspath(override) if override else ACCOUNTS_PATH
    data = load_json(path, {}) or {}
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        return []
    return [
        account for account in accounts
        if account.get("status") == "active"
        and (account.get("channels") or {}).get("threads")
    ]


def fetch_account_html(handle: str) -> str | None:
    """계정 페이지 HTML. 로그인 없이 받는다."""
    username = handle.lstrip("@")
    url = f"https://www.threads.com/@{username}"
    out_path = os.path.join(tempfile.gettempdir(), f"threads_bm_{username}.html")
    command = [
        "node", SCRAPLING_RUNNER,
        "--fetcher", "stealthy-fetch",
        "--url", url,
        "--output", out_path,
    ]
    print(f"   ▶ {url}")
    result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   ⚠️ 가져오기 실패({result.returncode}): {(result.stderr or '').strip()[:200]}")
        return None
    if not os.path.exists(out_path):
        print("   ⚠️ 산출 파일이 없다")
        return None
    with open(out_path, "r", encoding="utf-8", errors="replace") as handle_file:
        return handle_file.read()


def _walk_thread_nodes(node, found=None):
    """`thread_items` 를 가진 노드를 전부 모은다.

    계정 페이지는 글 하나가 아니라 목록이라, 저장글 경로처럼 target_code 로
    좁힐 수 없다. 트리를 훑어 글 묶음을 전부 집는다.
    """
    if found is None:
        found = []
    if isinstance(node, dict):
        if "thread_items" in node:
            found.append(node)
        for value in node.values():
            _walk_thread_nodes(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_thread_nodes(value, found)
    return found


def parse_posts(html: str, username: str) -> list[dict]:
    """HTML 안의 embedded JSON 에서 글을 뽑는다. 파싱은 기존 파서에 맡긴다."""
    nodes = []
    for block in iter_result_data_blocks(html):
        _walk_thread_nodes(block, nodes)

    posts: list[dict] = []
    seen: set[str] = set()
    for node in nodes:
        for post in extract_posts_from_node(node, None, None):
            code = str(post.get("code") or "")
            # 남의 답글이 섞여 들어온다. 그 계정 글만 남긴다.
            if not code or code in seen:
                continue
            if str(post.get("username") or "").lstrip("@") != username:
                continue
            seen.add(code)
            posts.append(post)
    # 최신순. taken_at 이 없으면 created_at 문자열로 떨어진다.
    posts.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    return posts


def to_standard(raw: dict, account: dict) -> dict:
    """표준 스키마로 옮기고 벤치마킹 표식을 붙인다."""
    post = dict(raw)
    post["sns_platform"] = "threads"
    post["is_saved"] = False
    post["is_own_post"] = False
    post["benchmark_accounts"] = [account.get("id")]
    post["source"] = f"benchmark:{account.get('id')}"
    normalized = normalize_post(post)
    if not normalized.get("display_name"):
        normalized["display_name"] = account.get("name") or normalized.get("username")
    return normalized


def collect(limit_override: int | None, dry_run: bool, only: str | None):
    accounts = load_active_threads_accounts()
    if only:
        accounts = [a for a in accounts if a.get("id") == only]
    if not accounts:
        print("ℹ️ 켜진 Threads 벤치마킹 계정이 없습니다.")
        return 0

    print(f"🎯 대상 계정 {len(accounts)}개")
    merged: list[dict] = []
    seen_codes: set[str] = set()
    collected_accounts = 0

    for account in accounts:
        handle = str((account.get("channels") or {}).get("threads") or "").strip()
        if not handle:
            continue
        username = handle.lstrip("@")
        limit = limit_override or int(account.get("limit") or DEFAULT_LIMIT)
        print(f"\n📌 {account.get('name') or account.get('id')} (@{username}) · 최대 {limit}편")

        if dry_run:
            print("     (dry-run — 가져오지 않음)")
            continue

        html = fetch_account_html(username)
        if not html:
            continue

        posts = parse_posts(html, username)
        if not posts:
            print("   ⚠️ 글을 찾지 못했다 — 페이지 구조가 바뀌었을 수 있다")
            continue

        added = 0
        for raw in posts[:limit]:
            code = str(raw.get("code") or "")
            if code in seen_codes:
                continue
            seen_codes.add(code)
            merged.append(to_standard(raw, account))
            added += 1
        collected_accounts += 1
        print(f"   ✅ {added}편 (페이지에서 {len(posts)}편 확인)")

    if not merged:
        print("\nℹ️ 통합본에 넣을 새 글이 없습니다.")
        return 0

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(OUTPUT_DIR, f"threads_user_full_{stamp}.json")
    payload = {
        "metadata": {
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "crawl_mode": "benchmark",
            "platform": "threads",
            "account_count": collected_accounts,
            "post_count": len(merged),
        },
        "posts": merged,
    }
    save_json(out_path, payload)
    print(f"\n💾 저장: {out_path} ({len(merged)}편 · 계정 {collected_accounts}개)")
    return len(merged)


def main():
    parser = argparse.ArgumentParser(
        description="벤치마킹 계정의 Threads 글 수집 (계정 단위·비로그인)"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="계정별 상한을 강제한다. 생략하면 계정 설정값(기본 5)")
    parser.add_argument("--only", type=str, default=None, help="계정 id 하나만 돌린다")
    parser.add_argument("--dry-run", action="store_true", help="대상만 출력한다")
    args = parser.parse_args()

    collect(args.limit, args.dry_run, args.only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
