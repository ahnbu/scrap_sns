"""Threads display_name 백필 스크립트.

수집기(DOM 경로)가 display_name을 채우지 못해 username으로 fallback된 게시글을
저자 프로필에서 실제 표시 이름(full_name)을 가져와 채운다.

배경:
    thread_scrap.py 의 DOM 수집 경로는 카드의 inner_text 만 읽는데, Threads 카드에는
    계정 아이디만 렌더링되고 full_name 이 없다. 따라서 수집 단계에서는 채울 방법이 없고,
    저자 단위로 프로필을 조회해 사후 백필하는 것이 유일한 경로다.

    display_name 은 게시글 속성이 아니라 저자 속성이므로, 게시글 N건이 아니라
    고유 저자 M명만 조회하면 된다.

사용법:
    python scripts/backfill_threads_display_name.py            # 백필 실행
    python scripts/backfill_threads_display_name.py --dry-run  # 대상만 집계
    python scripts/backfill_threads_display_name.py --verify   # 백필 결과 검증
    python scripts/backfill_threads_display_name.py --limit 20 # 상위 20명만

주의:
    playwright 가 설치된 인터프리터로 실행해야 한다.
    기본 python 에 없으면 Python311 을 사용한다.
"""

import argparse
import glob
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THREADS_FULL_GLOB = os.path.join(REPO_ROOT, "output_threads", "python", "threads_py_full_*.json")
TOTAL_FULL_GLOB = os.path.join(REPO_ROOT, "output_total", "total_full_*.json")
LOG_DIR = os.path.join(REPO_ROOT, "logs")

KST = timezone(timedelta(hours=9))
FULL_NAME_RE = re.compile(r'"full_name":"((?:[^"\\]|\\.)*)"')
TITLE_RE = re.compile(r"^(.*?)\s*\(@([^)]+)\)\s*[•·]")


def now_kst():
    return datetime.now(KST)


def latest_file(pattern):
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"대상 파일을 찾을 수 없습니다: {pattern}")
    return files[-1]


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def get_posts(data):
    """threads_py_full / total_full 양쪽 구조를 모두 받는다."""
    if isinstance(data, list):
        return data
    return data.get("posts", [])


def collect_targets(posts):
    """display_name == username 인 게시글의 고유 username 목록."""
    targets = {}
    for post in posts:
        username = str(post.get("username") or "").strip()
        display_name = str(post.get("display_name") or "").strip()
        if not username or display_name != username:
            continue
        targets[username] = targets.get(username, 0) + 1
    return targets


def extract_full_name(html, page_title, username):
    """프로필 페이지에서 full_name 을 뽑는다.

    1순위: JSON 페이로드의 "full_name" 필드
    2순위: 페이지 title (`홍길동 (@handle) • Threads, Say more`)
    """
    for raw in FULL_NAME_RE.findall(html)[:40]:
        try:
            value = json.loads('"' + raw + '"')
        except Exception:
            continue
        value = value.strip()
        if value and value != username:
            return value, "payload"

    match = TITLE_RE.match(page_title or "")
    if match:
        value = match.group(1).strip()
        handle = match.group(2).strip()
        if value and handle.lower() == username.lower() and value != username:
            return value, "title"

    return None, None


def fetch_display_names(usernames, delay, log_lines, limit=None, headless=True):
    from playwright.sync_api import sync_playwright
    from utils.auth_paths import threads_storage

    auth_file = str(threads_storage())
    if not os.path.exists(auth_file):
        raise FileNotFoundError(f"Threads 인증 파일이 없습니다: {auth_file}")

    ordered = sorted(usernames)
    if limit:
        ordered = ordered[:limit]

    resolved = {}
    failed = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=auth_file)
        page = context.new_page()

        try:
            for index, username in enumerate(ordered, start=1):
                try:
                    page.goto(
                        f"https://www.threads.com/@{username}",
                        wait_until="domcontentloaded",
                        timeout=25000,
                    )
                    page.wait_for_timeout(1500)
                    name, source = extract_full_name(page.content(), page.title(), username)

                    if name:
                        resolved[username] = name
                        line = f"OK    {username} -> {name} ({source})"
                    else:
                        failed.append(username)
                        line = f"EMPTY {username} (프로필에 표시 이름 없음)"
                except Exception as exc:
                    failed.append(username)
                    line = f"FAIL  {username} : {str(exc)[:120]}"

                print(f"[{index}/{len(ordered)}] {line}", flush=True)
                log_lines.append(line)

                if index < len(ordered):
                    time.sleep(delay)
        finally:
            browser.close()

    return resolved, failed


def apply_backfill(path, resolved):
    """display_name == username 인 게시글만 갱신한다. 기존 이름은 건드리지 않는다."""
    data = load_json(path)
    posts = get_posts(data)
    changed = 0

    for post in posts:
        username = str(post.get("username") or "").strip()
        display_name = str(post.get("display_name") or "").strip()
        if not username or display_name != username:
            continue
        new_name = resolved.get(username)
        if new_name and new_name != username:
            post["display_name"] = new_name
            changed += 1

    if changed:
        save_json(path, data)
    return changed


def backup_file(path):
    stamp = now_kst().strftime("%Y%m%d_%H%M%S")
    dest = f"{path}.bak_{stamp}"
    shutil.copy2(path, dest)
    return dest


def write_log(lines, summary):
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(
        LOG_DIR, f"backfill_threads_display_name_{now_kst().strftime('%Y%m%d_%H%M%S')}.log"
    )
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n\n=== 요약 ===\n")
        for key, value in summary.items():
            f.write(f"{key}: {value}\n")
    return log_path


def run_verify():
    """백필 결과를 검증한다. 종료코드로 판정한다."""
    threads_path = latest_file(THREADS_FULL_GLOB)
    threads_posts = get_posts(load_json(threads_path))
    remaining = collect_targets(threads_posts)
    remaining_posts = sum(remaining.values())

    print(f"upstream: {threads_path}")
    print(f"  전체 게시글        : {len(threads_posts)}")
    print(f"  display_name 결측  : {remaining_posts}건 / 저자 {len(remaining)}명")

    try:
        total_path = latest_file(TOTAL_FULL_GLOB)
        total_posts = [
            p for p in get_posts(load_json(total_path))
            if str(p.get("sns_platform") or "").lower() == "threads"
        ]
        total_remaining = collect_targets(total_posts)
        print(f"total: {total_path}")
        print(f"  Threads 게시글     : {len(total_posts)}")
        print(f"  display_name 결측  : {sum(total_remaining.values())}건 / 저자 {len(total_remaining)}명")
    except FileNotFoundError:
        print("total_full 파일 없음 - upstream 만 검증")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Threads display_name 백필")
    parser.add_argument("--dry-run", action="store_true", help="대상만 집계하고 종료")
    parser.add_argument("--verify", action="store_true", help="백필 결과 검증")
    parser.add_argument("--limit", type=int, default=0, help="상위 N명만 처리 (0=전체)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="저자당 요청 간격(초). WAF 차단 방지용. 기본 2.0")
    parser.add_argument("--headful", action="store_true", help="브라우저 창을 띄운다 (기본: headless)")
    args = parser.parse_args()

    if args.verify:
        return run_verify()

    threads_path = latest_file(THREADS_FULL_GLOB)
    posts = get_posts(load_json(threads_path))
    targets = collect_targets(posts)

    print(f"대상 파일 : {threads_path}")
    print(f"전체 게시글: {len(posts)}")
    print(f"백필 대상  : {sum(targets.values())}건 / 고유 저자 {len(targets)}명")

    if args.dry_run:
        for username, count in sorted(targets.items(), key=lambda kv: -kv[1])[:20]:
            print(f"  {username:30} {count}건")
        return 0

    if not targets:
        print("백필 대상이 없습니다.")
        return 0

    log_lines = [
        f"백필 시작 {now_kst().isoformat()}",
        f"대상 파일 {threads_path}",
        f"대상 {sum(targets.values())}건 / 저자 {len(targets)}명",
        f"요청 간격 {args.delay}초",
        "",
    ]

    resolved, failed = fetch_display_names(
        targets.keys(), args.delay, log_lines,
        limit=args.limit or None, headless=not args.headful,
    )

    print(f"\n조회 완료: 성공 {len(resolved)}명 / 실패·없음 {len(failed)}명")

    if not resolved:
        summary = {"조회 성공": 0, "조회 실패": len(failed), "백필 건수": 0}
        log_path = write_log(log_lines, summary)
        print(f"채울 이름을 얻지 못했습니다. 로그: {log_path}")
        return 1

    backup = backup_file(threads_path)
    print(f"백업 생성: {backup}")
    changed = apply_backfill(threads_path, resolved)
    print(f"백필 완료: {changed}건 갱신")

    attempted = args.limit or len(targets)
    summary = {
        "조회 성공": len(resolved),
        "조회 실패·이름없음": len(failed),
        "백필 건수": changed,
        "백업 파일": backup,
        "실패 목록": ", ".join(failed) if failed else "없음",
    }
    log_path = write_log(log_lines, summary)
    print(f"로그: {log_path}")
    print("\n다음 단계: python total_scrap.py --mode merge-only 또는 python scripts/merge_total_only.py")

    # 실패가 절반을 넘으면 비정상 종료로 알린다
    return 1 if len(failed) > attempted / 2 else 0


if __name__ == "__main__":
    sys.exit(main())
