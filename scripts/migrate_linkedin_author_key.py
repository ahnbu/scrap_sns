"""LinkedIn 벤치마킹 수집분의 저자 키를 피드 수집분과 맞춘다.

무엇을 고치나
-------------
같은 사람이 두 저자로 갈려 있다.

    피드 수집    `username` = 불투명 ID `ACoAA...`   (2026-09-10 실측 722건)
    벤치마킹 수집 `username` = 표시명 `Seungpil Lee` (동 47건)

뷰어의 「이 저자만 보기」는 `(platform, username)` 동일성으로 판정하므로
(`web_viewer/script.js` `isSameAuthor`), 이승필이 24건과 5건으로 쪼개진다.
여기서 표시명 쪽을 계정 정본 키로 바꾼다. 표시명은 `display_name` 에 남는다.

수집기 쪽은 `linkedin_scrap_benchmark.canonical_author_key()` 가 이미 고쳤다.
이 스크립트는 그 전에 쌓인 것을 맞춘다.

안전장치
--------
대상 디렉토리는 `.gitignore` 의 `output_*` 에 걸려 **git 으로 되돌릴 수 없다**.
그래서 셋을 둔다.
  1. 쓰기 전에 전량 백업하고 개수·바이트 수를 대조한다
  2. 파일 단위로 `.tmp` 에 쓰고 `os.replace()` 로 교체한다
  3. 도중 실패하면 그때까지 교체한 파일을 백업본으로 되돌린다

`post_key` 는 `platform:platform_id` 라 `username` 을 바꿔도 별표·메모는
영향받지 않는다(`utils/post_meta.build_post_key`).

사용법
------
    python scripts/migrate_linkedin_author_key.py --dry-run
    python scripts/migrate_linkedin_author_key.py

계획: _docs/20260910_01 (W2 T2-b)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# 경로 정본은 total_scrap.OUTPUT_LINKEDIN_BENCHMARK_DIR 이다. 같은 값을 두 곳에
# 적으면 갈라지므로 여기서 다시 조립하되 아래 assert 로 묶는다.
TARGET_DIR = os.path.join(REPO_ROOT, "output_linkedin_user", "python")
TARGET_GLOB = os.path.join(TARGET_DIR, "linkedin_user_full_*.json")
ACCOUNTS_PATH = os.path.join(REPO_ROOT, "web_viewer", "benchmark_accounts.json")


def load_accounts() -> list:
    with open(ACCOUNTS_PATH, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    accounts = data.get("accounts", data) if isinstance(data, dict) else data
    return accounts if isinstance(accounts, list) else []


def canonical_key_by_account(accounts: list) -> dict:
    """{계정 id: 정본 저자 키}. 불투명 ID 가 없으면 vanity slug."""
    mapping: dict[str, str] = {}
    for account in accounts:
        account_id = str(account.get("id") or "")
        if not account_id:
            continue
        linkedin_keys = (account.get("match_keys") or {}).get("linkedin") or []
        opaque = next((str(k) for k in linkedin_keys if str(k).startswith("ACoAA")), "")
        slug = str((account.get("channels") or {}).get("linkedin") or "")
        chosen = opaque or slug
        if chosen:
            mapping[account_id] = chosen
    return mapping


def plan_changes(paths: list, mapping: dict) -> tuple[dict, list]:
    """{경로: (문서, 바뀔 건수)} 와 매핑을 못 찾은 사례 목록."""
    planned: dict[str, tuple] = {}
    unmapped: list[str] = []

    for path in paths:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        posts = data.get("posts", []) if isinstance(data, dict) else data
        changed = 0
        for post in posts:
            if not isinstance(post, dict):
                continue
            if str(post.get("sns_platform") or "").lower() != "linkedin":
                continue
            username = str(post.get("username") or "")
            if username.startswith("ACoAA"):
                continue  # 이미 정본 키다
            account_ids = post.get("benchmark_accounts") or []
            canonical = next(
                (mapping[a] for a in account_ids if a in mapping), ""
            )
            if not canonical:
                unmapped.append(f"{os.path.basename(path)}: {username or '(빈 값)'}")
                continue
            if canonical == username:
                continue
            if username and not post.get("display_name"):
                post["display_name"] = username
            post["username"] = canonical
            changed += 1
        if changed:
            planned[path] = (data, changed)

    return planned, unmapped


def backup(paths: list) -> str:
    """대상 전량을 복사하고 개수·바이트 수를 대조한다."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(TARGET_DIR, f"backup_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)

    for path in paths:
        shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))

    copied = sorted(os.listdir(backup_dir))
    if len(copied) != len(paths):
        raise RuntimeError(
            f"백업 개수 불일치: 원본 {len(paths)}개, 백업 {len(copied)}개"
        )
    for path in paths:
        source_size = os.path.getsize(path)
        backup_size = os.path.getsize(os.path.join(backup_dir, os.path.basename(path)))
        if source_size != backup_size:
            raise RuntimeError(
                f"백업 크기 불일치: {os.path.basename(path)} "
                f"({source_size} != {backup_size})"
            )
    print(f"   💾 백업 완료: {backup_dir} ({len(copied)}개)")
    return backup_dir


def write_atomic(path: str, data) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)
    os.replace(tmp_path, path)


def rollback(written: list, backup_dir: str) -> None:
    for path in written:
        source = os.path.join(backup_dir, os.path.basename(path))
        if os.path.exists(source):
            shutil.copy2(source, path)
    print(f"   ↩️ 롤백 완료: {len(written)}개 파일을 백업본으로 되돌렸다")


def report_leftover_tmp() -> None:
    leftovers = glob.glob(os.path.join(TARGET_DIR, "*.tmp"))
    if leftovers:
        print("   ⚠️ 잔여 임시 파일:")
        for path in leftovers:
            print(f"      {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="변경 대상만 출력한다")
    args = parser.parse_args()

    try:
        from total_scrap import OUTPUT_LINKEDIN_BENCHMARK_DIR
        if os.path.normcase(OUTPUT_LINKEDIN_BENCHMARK_DIR) != os.path.normcase(TARGET_DIR):
            print(
                "❌ 대상 경로가 total_scrap 의 정본과 다르다:\n"
                f"   정본 {OUTPUT_LINKEDIN_BENCHMARK_DIR}\n"
                f"   여기 {TARGET_DIR}"
            )
            return 2
    except ImportError as error:
        print(f"⚠️ 경로 대조를 건너뛴다(total_scrap import 실패: {error})")

    paths = sorted(glob.glob(TARGET_GLOB))
    if not paths:
        print(f"대상 파일이 없다: {TARGET_GLOB}")
        return 0
    print(f"대상 {len(paths)}개: {TARGET_DIR}")

    mapping = canonical_key_by_account(load_accounts())
    planned, unmapped = plan_changes(paths, mapping)

    total_changed = sum(count for _, count in planned.values())
    print(f"변경 예정 {total_changed}건 / 파일 {len(planned)}개")
    for path, (_, count) in sorted(planned.items()):
        print(f"   {os.path.basename(path)}: {count}건")
    if unmapped:
        print(f"   ⚠️ 정본 키를 못 찾은 레코드 {len(unmapped)}건 — 그대로 둔다")
        for line in unmapped[:10]:
            print(f"      {line}")

    if args.dry_run:
        print("\n[DRY-RUN] 파일을 건드리지 않고 종료한다.")
        return 0
    if not planned:
        print("바꿀 것이 없다.")
        return 0

    backup_dir = backup(paths)
    written: list[str] = []
    try:
        for path, (data, _) in sorted(planned.items()):
            write_atomic(path, data)
            written.append(path)
    except Exception as error:  # noqa: BLE001
        print(f"❌ 쓰기 실패({type(error).__name__}: {error}) — 되돌린다")
        rollback(written, backup_dir)
        report_leftover_tmp()
        return 1

    report_leftover_tmp()
    print(f"✅ {len(written)}개 파일 갱신 완료 ({total_changed}건)")
    print(f"   백업은 자동 삭제하지 않는다. 확인 후 지운다: {backup_dir}")
    print("   다음 단계: 통합본을 다시 만들어야 뷰어에 반영된다 (total_scrap 병합)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
