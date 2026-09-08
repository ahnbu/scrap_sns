"""벤치마킹 계정 수집분의 누적 저장소.

왜 이 파일이 필요한가
---------------------
Threads·LinkedIn 벤치마킹 수집기는 **이번 실행분만** 새 파일로 썼다. 그런데
`total_scrap.merge_results()` 는 각 폴더의 **최신 파일 하나**만 읽는다. 두 성질이
겹치면 수집할 때마다 직전 수집분이 통합본에서 사라진다 - 계정당 상한이 5편이니
「쌓이는 자료」가 아니라 「최근 5편 스냅샷」이 된다.

`youtube_scrap.py` 는 `load_existing_posts()` 로 이미 누적한다. 여기는 그 방식을
Threads·LinkedIn 에도 주되, 무한히 커지지 않게 계정당 보관 상한을 둔다.

계획: _docs/20260908_01 (W1)
"""

from __future__ import annotations

import glob
import json
import os
import re

# 계정당 보관 상한. 1회 수집량(`limit`, 기본 5편)과 다른 값이다 - 이쪽은 쌓아둘
# 상한이다. 근거: BACKLOG.md#BL-0906-01 의 「계정당 최근 N편(초기 30 제안)」
KEEP_LIMIT = 30


def latest_full_file(output_dir: str, prefix: str) -> str | None:
    """`<prefix>YYYYMMDD.json` 중 날짜가 가장 큰 파일.

    mtime 이 아니라 파일명 날짜로 고른다 - 같은 날 여러 번 돌면 mtime 은 순서를
    보장하지만, 파일을 복사·복원한 뒤에는 어긋난다.
    """
    pattern = os.path.join(output_dir, f"{prefix}*.json")
    candidates = [
        path for path in glob.glob(pattern)
        if re.fullmatch(rf"{re.escape(prefix)}\d{{8}}\.json", os.path.basename(path))
    ]
    return max(candidates, key=os.path.basename) if candidates else None


def load_existing_posts(output_dir: str, prefix: str) -> list[dict]:
    """직전까지 쌓아둔 글. 파일이 없거나 깨져 있으면 빈 목록이다.

    최초 수집·갓 클론한 환경에서 예외로 죽지 않아야 한다.
    """
    path = latest_full_file(output_dir, prefix)
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as error:
        print(f"   ⚠️ 기존 누적분을 읽지 못했다({os.path.basename(path)}): {error}")
        return []
    posts = data.get("posts", []) if isinstance(data, dict) else data
    return [post for post in posts if isinstance(post, dict)]


def _sort_key(post: dict) -> str:
    """최신순 정렬 키. created_at 이 없으면 date 로 떨어진다."""
    return str(post.get("created_at") or post.get("date") or "")


def _account_of(post: dict) -> str:
    accounts = post.get("benchmark_accounts") or []
    return str(accounts[0]) if accounts else ""


def merge_and_cap(
    existing: list[dict],
    incoming: list[dict],
    keep_limit: int = KEEP_LIMIT,
) -> tuple[list[dict], dict[str, int]]:
    """기존 누적분에 이번 수집분을 얹고 계정당 상한으로 자른다.

    - 중복 키는 `code`. 겹치면 **이번 수집분이 이긴다** - 좋아요·댓글 수가 최신이다.
    - 계정당 `keep_limit` 편까지만 남긴다. 넘치면 오래된 것부터 버린다.
    - 켜져 있지 않은 계정의 과거분도 그대로 남는다. 계정을 껐다고 이미 모은 글을
      지우지 않는다.
    - 계정 표식이 없는 레코드는 상한을 적용하지 않고 보존한다(레거시 안전판).

    반환: (남은 글, {계정 id: 잘라낸 건수})
    """
    by_code: dict[str, dict] = {}
    order: list[str] = []
    for post in list(existing) + list(incoming):
        code = str(post.get("code") or post.get("platform_id") or "")
        if not code:
            continue
        if code not in by_code:
            order.append(code)
        # 뒤에 오는 쪽(= 이번 수집분)이 이긴다.
        by_code[code] = post

    grouped: dict[str, list[dict]] = {}
    for code in order:
        grouped.setdefault(_account_of(by_code[code]), []).append(by_code[code])

    kept: list[dict] = []
    removed: dict[str, int] = {}
    for account_id, posts in grouped.items():
        if not account_id:
            kept.extend(posts)
            continue
        posts.sort(key=_sort_key, reverse=True)
        if len(posts) > keep_limit:
            removed[account_id] = len(posts) - keep_limit
            posts = posts[:keep_limit]
        kept.extend(posts)

    kept.sort(key=_sort_key, reverse=True)
    return kept, removed


def report_removed(removed: dict[str, int], keep_limit: int = KEEP_LIMIT) -> None:
    """상한 초과로 버린 것을 드러낸다.

    조용히 사라지면 「한 건도 사라지지 않는다」는 완료 기준과 구분되지 않는다.
    """
    for account_id, count in sorted(removed.items()):
        print(f"   ✂️ {account_id} 보관 상한 {keep_limit}편 초과 — {count}편 제거")


def atomic_save_json(path: str, data) -> bool:
    """임시 파일에 쓴 뒤 교체한다.

    `utils.common.save_json()` 은 대상 파일을 바로 열어 덮어쓴다. 누적본은 한
    파일에 계정당 최대 30편이 들어가므로, 쓰는 도중 실패하면 그동안 쌓은 것을
    통째로 잃는다. 여기서는 실패해도 원본이 그대로 남는다.

    같은 방식이 레포에 이미 셋 있다 - `scrap_sns_server._atomic_write_json`,
    `scripts/sync_benchmark_accounts.atomic_write_json`,
    `scripts/backfill_youtube_channel_id.atomic_write_json`.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
        return True
    except Exception as error:  # noqa: BLE001
        # 실패하면 `.tmp` 가 남지만 지우지 않는다 - 다음 성공이 덮어쓴다.
        # 레포의 다른 원자적 쓰기도 같은 관례다.
        print(f"⚠️ [benchmark_store] 저장 실패 ({path}): {error}")
        return False
