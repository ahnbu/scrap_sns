"""X(Twitter) created_at UTC → KST 백필 스크립트.

배경:
    twitter_scrap.py 의 두 날짜 경로가 UTC 를 KST 로 변환하지 않고 그대로 기록했다.
    - GraphQL 경로: `+0000` 을 `%z` 가 아니라 포맷 리터럴로 파싱해 naive UTC 가 됨
    - HTML 폴백 경로: tz-aware UTC 를 만들고 `astimezone` 없이 `strftime`
    Threads·LinkedIn·YouTube 는 모두 KST 로 저장하므로 X 만 9시간 어긋나 있었다.

    코드만 고치면 안 된다. twitter_scrap.py 는 기존 레코드를 ①신규 ②본문이 길어짐
    ③지표가 새로 생김 셋 중 하나일 때만 교체하고, `stop_ids` 중단점 때문에 옛 트윗을
    다시 긁지도 않는다. 그래서 재수집으로는 복구되지 않고, 신규만 KST 가 되어
    KST/UTC 가 섞인다 — 지금(전량 UTC 로 일관)보다 나쁜 상태다.

    보정은 저장값에 +9시간을 더하지 않는다. 트윗 Snowflake ID 에서 발행 시각을
    **재계산**한다. 멱등이라 몇 번 실행해도 결과가 같고, 이중 보정을 막을 실행
    마커가 필요 없다. 95건 전부에서 저장값 == Snowflake UTC 임을 확인했다.

    경위 전문: _docs/20260905_01_X-게시일시-UTC저장-결함수정과-95건-백필-계획_실행완료.md

사용법:
    python scripts/backfill_twitter_created_at_kst.py --dry-run   # 대상 집계 (기본)
    python scripts/backfill_twitter_created_at_kst.py --apply     # 실제 보정
    python scripts/backfill_twitter_created_at_kst.py --verify    # 결과 검증

대상:
    output_twitter/python/ 의 **최신** twitter_py_simple_*.json 과 twitter_py_full_*.json 둘 다.
    과거 스냅샷은 시점 아카이브로 둔다 — total_scrap.py 의 merge_results() 가
    플랫폼별 최신 파일 1개만 읽는다.

    🔴 **simple 을 빼면 안 된다.** twitter_scrap_single.py 는 simple 을 읽어(58-68줄)
    full 을 만든다(141줄). full 만 고치면 다음 consumer 실행 때 simple 의 UTC 값으로
    덮어써져 원상복구된다 — 2026-09-05 에 실제로 겪었다(`pytest tests/smoke` 가
    consumer 를 돌렸고 95건이 전부 되돌아갔다).

    --file 로 다른 파일을 직접 지정할 수 있다(output_total 검증 등).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.x_time import created_at_from_id, format_kst  # noqa: E402

DEFAULT_DIR = "output_twitter/python"
# simple 이 먼저다. full 은 simple 에서 파생되므로 상류부터 고쳐야 한다.
DEFAULT_PATTERNS = ("twitter_py_simple_*.json", "twitter_py_full_*.json")


def latest_full_file(directory: str, pattern: str) -> str | None:
    files = sorted(
        f for f in glob.glob(os.path.join(directory, pattern)) if ".bak" not in os.path.basename(f)
    )
    return files[-1] if files else None


def resolve_targets(args) -> list[str]:
    """작업 대상 파일 목록. --file 이 있으면 그것만, 없으면 최신 simple + full."""
    if args.file:
        return [args.file]
    patterns = (args.pattern,) if args.pattern else DEFAULT_PATTERNS
    found = [latest_full_file(args.dir, p) for p in patterns]
    return [f for f in found if f]


def load_records(path: str):
    """파일을 읽고 (원본 컨테이너, 레코드 리스트)를 돌려준다.

    산출물은 최상위 리스트이거나 {"posts": [...]} 형태다. 저장할 때 원래
    모양을 그대로 돌려놓아야 하므로 컨테이너를 함께 들고 다닌다.
    """
    with open(path, "r", encoding="utf-8") as fp:
        data = json.loads(fp.read().lstrip("﻿"))
    if isinstance(data, list):
        return data, data
    for key in ("posts", "data", "items"):
        if isinstance(data.get(key), list):
            return data, data[key]
    raise ValueError(f"게시물 배열을 찾을 수 없습니다: {path}")


def is_x(record: dict) -> bool:
    return (record.get("sns_platform") or record.get("platform")) == "x"


def plan_changes(records):
    """(변경목록, 이미맞음, 복원불가) 를 돌려준다. 파일은 건드리지 않는다."""
    changes, already_ok, unresolved = [], [], []
    for record in records:
        if not is_x(record):
            continue
        restored = created_at_from_id(record.get("platform_id"))
        if restored is None:
            unresolved.append(record)
            continue
        new_created_at, new_date = format_kst(restored)
        old_created_at = record.get("created_at")
        old_date = record.get("date")
        if old_created_at == new_created_at and old_date == new_date:
            already_ok.append(record)
            continue
        changes.append(
            {
                "record": record,
                "platform_id": record.get("platform_id"),
                "old_created_at": old_created_at,
                "new_created_at": new_created_at,
                "old_date": old_date,
                "new_date": new_date,
            }
        )
    return changes, already_ok, unresolved


def report(path, records, changes, already_ok, unresolved, *, preview=5):
    x_total = sum(1 for r in records if is_x(r))
    date_shifts = sum(1 for c in changes if c["old_date"] != c["new_date"])
    print(f"대상 파일 : {path}")
    print(f"전체 레코드: {len(records)}건 (그중 X: {x_total}건)")
    print(f"보정 대상  : {len(changes)}건 (날짜까지 바뀌는 건: {date_shifts}건)")
    print(f"이미 정상  : {len(already_ok)}건")
    print(f"복원 불가  : {len(unresolved)}건")
    for change in changes[:preview]:
        print(
            f"   {change['platform_id']}: "
            f"{change['old_created_at']} → {change['new_created_at']}"
        )
    if len(changes) > preview:
        print(f"   … 외 {len(changes) - preview}건")
    if unresolved:
        ids = [r.get("platform_id") for r in unresolved[:preview]]
        print(f"   ⚠️ 복원 불가 platform_id: {ids} — 값을 바꾸지 않고 그대로 둡니다")


def apply_changes(path, container, changes):
    backup = f"{path}.bak"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print(f"백업 생성 : {backup}")
    for change in changes:
        change["record"]["created_at"] = change["new_created_at"]
        change["record"]["date"] = change["new_date"]
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(container, fp, ensure_ascii=False, indent=2)
    print(f"✅ {len(changes)}건 보정 완료 → {path}")


def verify(path, records):
    """전 X 레코드를 Snowflake 재계산값과 대조한다. 종료코드로 판정한다."""
    mismatched, unresolved, date_mismatch = [], [], []
    x_records = [r for r in records if is_x(r)]
    for record in x_records:
        restored = created_at_from_id(record.get("platform_id"))
        if restored is None:
            unresolved.append(record.get("platform_id"))
            continue
        expected_created_at, expected_date = format_kst(restored)
        if record.get("created_at") != expected_created_at:
            mismatched.append(
                (record.get("platform_id"), record.get("created_at"), expected_created_at)
            )
        if record.get("date") != expected_date:
            date_mismatch.append((record.get("platform_id"), record.get("date"), expected_date))

    print(f"검증 파일  : {path}")
    print(f"X 레코드   : {len(x_records)}건")
    print(f"created_at 불일치: {len(mismatched)}건")
    print(f"date 불일치      : {len(date_mismatch)}건")
    print(f"복원 불가        : {len(unresolved)}건")
    for item in mismatched[:5]:
        print(f"   ❌ {item[0]}: 저장={item[1]} 기대={item[2]}")
    for item in date_mismatch[:5]:
        print(f"   ❌ {item[0]}: date 저장={item[1]} 기대={item[2]}")

    if mismatched or date_mismatch:
        print("❌ 검증 실패")
        return 1
    print(f"✅ 검증 통과 — X {len(x_records)}건 전부 KST 기준과 일치")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="X created_at 을 KST 로 백필한다.")
    parser.add_argument("--apply", action="store_true", help="실제로 파일을 고친다")
    parser.add_argument("--dry-run", action="store_true", help="대상만 집계한다 (기본)")
    parser.add_argument("--verify", action="store_true", help="보정 결과를 검증한다")
    parser.add_argument("--file", help="대상 파일을 직접 지정한다")
    parser.add_argument("--dir", default=DEFAULT_DIR, help=f"탐색 디렉터리 (기본 {DEFAULT_DIR})")
    parser.add_argument("--pattern", help="파일 패턴 하나만 지정한다 (기본: simple + full)")
    args = parser.parse_args()

    targets = resolve_targets(args)
    if not targets:
        print(f"❌ 대상 파일을 찾을 수 없습니다: {args.file or f'{args.dir}/{DEFAULT_PATTERNS}'}")
        return 1

    exit_code = 0
    for index, path in enumerate(targets):
        if index:
            print()
        if not os.path.exists(path):
            print(f"❌ 대상 파일이 없습니다: {path}")
            exit_code = 1
            continue

        container, records = load_records(path)

        if args.verify:
            exit_code = verify(path, records) or exit_code
            continue

        changes, already_ok, unresolved = plan_changes(records)
        report(path, records, changes, already_ok, unresolved)

        if not args.apply:
            continue

        if not changes:
            print("보정할 레코드가 없습니다.")
            continue

        apply_changes(path, container, changes)

    if not args.verify and not args.apply:
        print("\n(dry-run) 실제로 고치려면 --apply 를 붙이세요.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
