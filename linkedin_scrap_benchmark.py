"""벤치마킹 계정의 LinkedIn 글을 계정 단위로 수집한다.

왜 이 파일이 필요한가
---------------------
`linkedin_scrap_by_user.py` 는 계정 하나를 손으로 지정해 긁는 독립 도구다.
벤치마킹 계정 목록(`web_viewer/benchmark_accounts.json`)을 **한 번도 읽지 않는다.**
그래서 화면에서 계정을 켜고 「수집 가능」 배지가 붙어도 아무도 안 긁었다 —
SPEC 은 LinkedIn 을 수집 가능으로 분류했는데 연결부가 없었다(수행계획 R-2).

이 파일이 그 연결부다. 수집 자체는 기존 도구에 맡기고, 여기서는
「켠 계정 고르기 → 호출 → 표식 붙여 통합본용 파일로 모으기」만 한다.
`youtube_scrap.py --channel` 이 같은 일을 하며, 그쪽 구조를 그대로 따랐다.

계획: _docs/20260906_03 (W3)
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from datetime import datetime

from playwright.sync_api import sync_playwright

from linkedin_scrap_by_user import (
    LinkedinUserScraper,
    launch_linkedin_browser,
    new_linkedin_context,
)
from utils.auth_status import AUTH_REQUIRED_EXIT_CODE, AuthRequiredError
from utils.benchmark_store import (
    KEEP_LIMIT,
    atomic_save_json,
    load_existing_posts,
    merge_and_cap,
    report_removed,
)
from utils.common import load_json
from utils.post_schema import normalize_post

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_PATH = os.path.join(PROJECT_ROOT, "web_viewer", "benchmark_accounts.json")
USER_DATA_ROOT = os.path.join(PROJECT_ROOT, "output_linkedin_user")
OUTPUT_DIR = os.path.join(USER_DATA_ROOT, "python")
DEFAULT_LIMIT = 5


def load_active_linkedin_accounts():
    """켜져 있고 LinkedIn 주소가 있는 계정만.

    `youtube_scrap.py:load_active_benchmark_accounts()` 와 같은 규칙이다 -
    status 가 active 가 아닌 계정은 수집 대상이 아니다.
    """
    override = os.environ.get("SNS_BENCHMARK_ACCOUNTS_PATH", "").strip()
    path = os.path.abspath(override) if override else ACCOUNTS_PATH
    data = load_json(path, {}) or {}
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        return []
    return [
        account for account in accounts
        if account.get("status") == "active"
        and (account.get("channels") or {}).get("linkedin")
    ]


def latest_full_file(slug: str):
    """그 계정 폴더의 최신 full 파일. 수집기가 계정별 폴더에 쌓는다."""
    directory = os.path.join(USER_DATA_ROOT, slug)
    if not os.path.isdir(directory):
        return None
    prefix = f"linkedin_{slug}_full_"
    files = [
        f for f in os.listdir(directory)
        if f.startswith(prefix) and f.endswith(".json") and "_total" not in f
    ]
    if not files:
        return None
    return os.path.join(directory, sorted(files)[-1])


def run_collector(context, slug: str, limit: int, dry_run: bool) -> int:
    """기존 수집기를 **같은 프로세스 안에서** 부른다. 수집 로직은 그대로 쓴다.

    종전에는 계정마다 자식 프로세스를 띄웠다(계정 5개 = 프로그램 5개 = 브라우저 5회).
    그럴 수밖에 없었던 이유는 `linkedin_scrap_by_user.py` 가 모듈 최상단에서
    `parse_args()` 를 불러 import 자체가 불가능했기 때문이다. 그 제약이 사라져
    브라우저 하나를 공유한다. 계획: _docs/20260909_01 (W6 T6-e)

    🔴 **종료코드 규약은 그대로다.** 인증 필요는 86, 그 밖의 실패는 1, 성공은 0.
       이 값이 collect() → main() → total_scrap 으로 올라가야 「업데이트」 결과창이
       재로그인을 안내한다. 계획: _docs/20260908_02 (W2-5)

    🔴 **계정 하나의 오류를 여기서 가둔다.** 프로세스가 갈라져 있을 때는 OS 가
       공짜로 해주던 격리다. 한 프로세스로 합쳤으니 코드가 대신한다.
    """
    print(f"   ▶ {slug} (limit {limit}) — 공용 브라우저로 수집")
    if dry_run:
        print("     (dry-run — 실행하지 않음)")
        return 0

    page = context.new_page()
    try:
        scraper = LinkedinUserScraper(slug, limit=limit)
        scraper.run_with_page(page)
        return 0
    except AuthRequiredError:
        print("   🔑 LinkedIn 인증이 필요하다 — 남은 계정도 같은 세션이라 여기서 멈춘다")
        return AUTH_REQUIRED_EXIT_CODE
    except Exception as error:  # noqa: BLE001 - 계정 하나의 실패로 나머지를 멈추지 않는다
        print(f"   ⚠️ 수집 중 오류 ({type(error).__name__}: {error}) — 이 계정은 건너뛴다")
        return 1
    finally:
        # 닫지 않으면 계정 수만큼 페이지가 한 프로세스에 쌓인다.
        try:
            page.close()
        except Exception:
            pass


def canonical_author_key(account: dict, slug: str, fallback: str = "") -> str:
    """이 계정의 LinkedIn 저자 키. 피드 수집분과 같은 값이어야 한다.

    왜 필요한가: 피드 수집(`linkedin_scrap.py`)은 `username` 에 불투명 ID
    (`ACoAA...`)를 넣는데, 여기 수집기는 `actor.name.text` 즉 **표시명**을 넣었다
    (`linkedin_scrap_by_user.py:428`). 그래서 한 사람이 두 저자로 갈렸다 - 실측
    2026-09-10 기준 LinkedIn 769건 중 47건이 표시명 쪽이었고, 뷰어의
    「이 저자만 보기」가 `(platform, username)` 동일성으로 판정하므로 이승필이
    24건과 5건으로 쪼개졌다.

    우선순위: 계정의 불투명 ID → vanity slug → 넘어온 값.
    `post_key` 는 `platform:platform_id` 라 이 값을 바꿔도 별표·메모는 영향받지
    않는다(`utils/post_meta.build_post_key`).
    계획: _docs/20260910_01 (W2 T2-a)
    """
    for key in (account.get("match_keys") or {}).get("linkedin") or []:
        if str(key).startswith("ACoAA"):
            return str(key)
    if slug:
        return str(slug)
    return str(fallback or "")


def to_standard(raw: dict, account: dict, slug: str) -> dict:
    """수집기 레코드를 표준 스키마로 옮기고 벤치마킹 표식을 붙인다.

    `is_saved=False` 와 `benchmark_accounts` 가 없으면 뷰어의
    `보임 = is_saved OR 켜진 계정` 판정에서 내 저장글과 구분되지 않는다.
    """
    post = dict(raw)
    # 표시명은 display_name 에 남기고 username 은 계정 정본 키로 맞춘다.
    display_from_scraper = str(post.get("username") or "").strip()
    canonical = canonical_author_key(account, slug, fallback=display_from_scraper)
    if canonical:
        post["username"] = canonical
        if display_from_scraper and not post.get("display_name"):
            post["display_name"] = display_from_scraper
    # 수집기는 images 로 담는다. 표준은 media 다 — LEGACY_FIELD_MAP 에 없어
    # 여기서 옮기지 않으면 이미지가 통째로 사라진다.
    if post.get("images") and not post.get("media"):
        post["media"] = post.pop("images")
    post.pop("images", None)
    post["sns_platform"] = "linkedin"
    post["is_saved"] = False
    post["benchmark_accounts"] = [account.get("id")]
    post["source"] = f"benchmark:{account.get('id')}"
    post["is_own_post"] = False
    normalized = normalize_post(post)
    if not normalized.get("url") and normalized.get("code"):
        normalized["url"] = f"https://www.linkedin.com/feed/update/urn:li:activity:{normalized['code']}/"
    if not normalized.get("display_name"):
        normalized["display_name"] = account.get("name") or slug
    return normalized


@contextmanager
def _open_shared_browser(dry_run: bool):
    """계정 전체가 함께 쓸 브라우저·컨텍스트를 연다.

    dry-run 은 수집기를 부르지 않으므로 브라우저도 열지 않는다 - 대상만 출력하는
    실행에서 창(또는 headless 프로세스)이 뜨면 목적이 어긋난다.
    """
    if dry_run:
        yield None, None
        return

    with sync_playwright() as playwright:
        browser = launch_linkedin_browser(playwright)
        try:
            context = new_linkedin_context(browser)
            try:
                yield browser, context
            finally:
                context.close()
        finally:
            browser.close()


def collect(limit_override: int | None, dry_run: bool, only: str | None) -> tuple[int, bool]:
    """(통합본에 넣은 글 수, 인증 필요 여부)를 돌려준다.

    인증 필요 여부를 따로 들고 나오는 이유: 이 값이 종료코드가 되어 `total_scrap` 까지
    올라가야 「업데이트」 결과창이 재로그인을 안내할 수 있다. 계획: _docs/20260908_02 (W2-5)
    """
    accounts = load_active_linkedin_accounts()
    if only:
        accounts = [a for a in accounts if a.get("id") == only]
    if not accounts:
        print("ℹ️ 켜진 LinkedIn 벤치마킹 계정이 없습니다.")
        return 0, False

    print(f"🎯 대상 계정 {len(accounts)}개")
    merged: list[dict] = []
    seen_codes: set[str] = set()
    collected_accounts = 0
    auth_required = False

    # 브라우저 하나·컨텍스트 하나를 계정 전체가 공유한다. 종전에는 계정마다
    # 프로세스가 떠서 브라우저도 그만큼 기동됐다(계정 5개 = 5회).
    # 계정마다 page 만 새로 연다 - 응답 핸들러가 인스턴스에 묶여 있어서다.
    # 계획: _docs/20260909_01 (W6 T6-e)
    with _open_shared_browser(dry_run) as (_browser, context):
        for account in accounts:
            slug = str((account.get("channels") or {}).get("linkedin") or "").strip()
            if not slug:
                continue
            limit = limit_override or int(account.get("limit") or DEFAULT_LIMIT)
            print(f"\n📌 {account.get('name') or account.get('id')} ({slug}) · 최대 {limit}편")

            returncode = run_collector(context, slug, limit, dry_run)
            if returncode == AUTH_REQUIRED_EXIT_CODE:
                # 계정마다 같은 세션 파일을 쓴다. 하나가 만료면 나머지도 반드시 만료다 —
                # 남은 계정을 도는 것은 실패를 반복하는 비용일 뿐이다. 여기까지 모은
                # 것은 아래에서 정상 저장한다(누적 보존).
                auth_required = True
                break
            if returncode != 0:
                continue

            full_file = latest_full_file(slug)
            if not full_file:
                print(f"   ⚠️ 산출물을 찾지 못했다: {os.path.join(USER_DATA_ROOT, slug)}")
                continue

            data = load_json(full_file, [])
            raw_posts = data.get("posts", []) if isinstance(data, dict) else (data or [])
            # 최신 limit 편만 통합본에 넣는다. 계정 폴더에는 과거 수집분이 쌓여 있어
            # 그대로 넣으면 상한이 무의미해진다.
            picked = raw_posts[:limit]
            added = 0
            for raw in picked:
                code = str(raw.get("code") or "")
                if not code or code in seen_codes:
                    continue
                seen_codes.add(code)
                merged.append(to_standard(raw, account, slug))
                added += 1
            collected_accounts += 1
            print(f"   ✅ {added}편 ({os.path.basename(full_file)})")

    # 이번 수집분만 저장하면 직전 수집분이 통합본에서 사라진다 - merge_results()
    # 가 이 폴더의 최신 파일 하나만 읽기 때문이다. 쌓아서 저장한다.
    # 계획: _docs/20260908_01 (W1)
    existing = load_existing_posts(OUTPUT_DIR, "linkedin_user_full_")
    if not merged and not existing:
        print("\nℹ️ 통합본에 넣을 글이 없습니다.")
        return 0, auth_required

    posts, removed = merge_and_cap(existing, merged)
    report_removed(removed)

    stamp = datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(OUTPUT_DIR, f"linkedin_user_full_{stamp}.json")
    payload = {
        "metadata": {
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "crawl_mode": "benchmark",
            "platform": "linkedin",
            "account_count": collected_accounts,
            "post_count": len(posts),
            "new_count": len(merged),
            "keep_limit": KEEP_LIMIT,
        },
        "posts": posts,
    }
    if not atomic_save_json(out_path, payload):
        return 0, auth_required
    print(
        f"\n💾 저장: {out_path} (누적 {len(posts)}편 · 이번 {len(merged)}편"
        f" · 계정 {collected_accounts}개)"
    )
    return len(posts), auth_required


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="벤치마킹 계정의 LinkedIn 글 수집 (계정 단위)"
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="계정별 상한을 강제한다. 생략하면 계정 설정값(기본 5)")
    parser.add_argument("--only", type=str, default=None,
                        help="계정 id 하나만 돌린다. 연결부 검증용")
    parser.add_argument("--dry-run", action="store_true",
                        help="수집기를 부르지 않고 대상만 출력한다")
    args = parser.parse_args(argv)

    count, auth_required = collect(args.limit, args.dry_run, args.only)
    if auth_required:
        # 수집한 만큼은 이미 저장했다. 종료코드로 인증 필요를 위에 알린다 —
        # total_scrap 이 이 코드를 bench_linkedin 의 auth_required 로 기록한다.
        return AUTH_REQUIRED_EXIT_CODE
    return 0 if count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
