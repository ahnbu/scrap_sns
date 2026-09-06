"""기존 YouTube 레코드에 channel_id 를 채운다.

왜 필요한가
-----------
유튜브 레코드의 `username` 은 채널 표시명이다. 벤치마킹 계정 주소는 `@handle` 이라
둘이 이어지지 않는다. 실측으로 제어문자가 섞인 이름도 있었다(`\\x08헤이디_...`).
`channel_id`(UC...) 가 유일한 안정 키다. 계획: _docs/20260906_01 (P0, D12)

안전 절차 — 이 레포의 백필 관행을 그대로 따른다
------------------------------------------------
`scripts/linkedin_metric_backfill.py` · `scripts/backfill_threads_display_name.py` 와
같은 형태다.

  1. `--dry-run` 으로 대상 건수만 먼저 센다
  2. 쓰기 전에 대상 파일을 `_backup_youtube_channel_id_<타임스탬프>/` 로 복사한다
     (`.gitignore` 의 `_backup_*/` 에 걸려 커밋되지 않는다)
  3. 임시 파일에 쓰고 `os.replace` 한다 - 중간에 죽어도 원본이 그대로 남는다
  4. API 조회에 실패한 video_id 는 건너뛰고 목록으로 출력한다.
     그 레코드는 channel_id 가 빈 채 남고, 재실행하면 그것만 다시 시도한다

롤백
----
백업 폴더의 파일을 원래 자리로 되돌려 놓으면 끝이다.
`copy _backup_youtube_channel_id_<타임스탬프>\\<파일명> <원래경로>`

사용법
------
    python scripts/backfill_youtube_channel_id.py --dry-run
    python scripts/backfill_youtube_channel_id.py
    python scripts/backfill_youtube_channel_id.py --target "output_total/total_full_*.json"
    python scripts/backfill_youtube_channel_id.py --no-backup   # 재실행용
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

API_BASE = "https://www.googleapis.com/youtube/v3"
# videos.list 는 한 번에 50개까지 받는다. 505건이면 11회 = 11유닛.
BATCH_SIZE = 50

# 기본값은 각 패턴의 **최신 1개**다. 과거 일자 파일은 아무도 읽지 않는다 -
# merge_results() 는 find_latest_full_file() 로 최신본만 가져오고, 통합본은
# 거기서 다시 만들어진다. 전량을 건드리면 유닛만 쓰고 얻는 게 없다.
# 과거 파일까지 채우려면 --target 으로 명시한다.
DEFAULT_TARGETS = [
    "output_youtube/python/youtube_py_full_*.json",
    "output_total/total_full_*.json",
]


def load_env() -> None:
    """~/.env 에서 키를 읽는다. youtube_scrap.py 와 같은 규칙이다."""
    env_path = os.path.join(os.path.expanduser("~"), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_json(path: str):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def atomic_write_json(path: str, data) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def backup_files(paths: list[str]) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(REPO_ROOT, f"_backup_youtube_channel_id_{stamp}")
    os.makedirs(backup_dir, exist_ok=True)
    for path in paths:
        shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    return backup_dir


def posts_of(data):
    if isinstance(data, dict):
        return data.get("posts", [])
    return data


def is_youtube(post: dict) -> bool:
    return str(post.get("sns_platform") or "").lower() == "youtube"


def needs_channel_id(post: dict) -> bool:
    return is_youtube(post) and not str(post.get("channel_id") or "").strip()


def fetch_channel_ids(video_ids: list[str], api_key: str) -> tuple[dict, list[str]]:
    """{video_id: channel_id} 와 실패한 video_id 목록을 돌려준다.

    한 배치가 통째로 실패해도 다른 배치는 계속 간다 - 일시 장애로 전체를
    멈추면 이미 받은 것까지 버리게 된다.
    """
    resolved: dict[str, str] = {}
    failed: list[str] = []
    for start in range(0, len(video_ids), BATCH_SIZE):
        batch = video_ids[start:start + BATCH_SIZE]
        params = urllib.parse.urlencode(
            {"part": "snippet", "id": ",".join(batch), "key": api_key}
        )
        url = f"{API_BASE}/videos?{params}"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - 원인을 그대로 보여준다
            print(f"   [WARN] 배치 조회 실패 ({start}~{start + len(batch)}): {error}")
            failed.extend(batch)
            continue

        returned = set()
        for item in payload.get("items", []):
            video_id = item.get("id")
            channel_id = str((item.get("snippet") or {}).get("channelId") or "")
            if video_id and channel_id:
                resolved[video_id] = channel_id
                returned.add(video_id)
        # 삭제·비공개 영상은 items 에 안 실린다. 그것도 실패로 남긴다.
        failed.extend([vid for vid in batch if vid not in returned])
        time.sleep(0.2)
    return resolved, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube 레코드에 channel_id 백필")
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=f"대상 glob(반복 가능). 기본값: {DEFAULT_TARGETS}",
    )
    parser.add_argument("--dry-run", action="store_true", help="대상만 세고 종료")
    parser.add_argument("--no-backup", action="store_true", help="백업 생략(재실행용)")
    parser.add_argument(
        "--all-history",
        action="store_true",
        help="패턴에 맞는 과거 일자 파일까지 전부. 기본은 패턴별 최신 1개",
    )
    args = parser.parse_args()

    patterns = args.target or DEFAULT_TARGETS
    paths: list[str] = []
    for pattern in patterns:
        matched = sorted(glob.glob(os.path.join(REPO_ROOT, pattern)))
        if not matched:
            continue
        paths.extend(matched if args.all_history else [matched[-1]])
    if not paths:
        print(f"[ERROR] 대상 파일이 없다: {patterns}", file=sys.stderr)
        return 1

    # 1) 대상 집계
    per_file: dict[str, list[str]] = {}
    all_ids: set[str] = set()
    for path in paths:
        data = load_json(path)
        pending = [
            str(post.get("platform_id") or post.get("code") or "")
            for post in posts_of(data)
            if needs_channel_id(post)
        ]
        pending = [vid for vid in pending if vid]
        per_file[path] = pending
        all_ids.update(pending)
        total_yt = sum(1 for post in posts_of(data) if is_youtube(post))
        print(f"   {os.path.basename(path)}: 유튜브 {total_yt}건 중 채울 것 {len(pending)}건")

    if not all_ids:
        print("✅ 채울 레코드가 없다. 이미 전부 channel_id 를 갖고 있다.")
        return 0

    print(f"\n대상 고유 video_id {len(all_ids)}건 · API 호출 {-(-len(all_ids) // BATCH_SIZE)}회(유닛)")

    if args.dry_run:
        print("[DRY-RUN] 파일을 건드리지 않고 종료한다.")
        return 0

    # 2) 조회
    load_env()
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("[ERROR] YOUTUBE_API_KEY 가 없다 (~/.env 확인).", file=sys.stderr)
        return 1

    resolved, failed = fetch_channel_ids(sorted(all_ids), api_key)
    print(f"\n조회 성공 {len(resolved)}건 · 실패 {len(failed)}건")
    if not resolved:
        print("[ERROR] 한 건도 못 받았다. 파일을 건드리지 않고 종료한다.", file=sys.stderr)
        return 1

    # 3) 백업 후 쓰기
    if not args.no_backup:
        backup_dir = backup_files(paths)
        print(f"백업 생성: {backup_dir}")

    total_written = 0
    for path, pending in per_file.items():
        if not pending:
            continue
        data = load_json(path)
        written = 0
        for post in posts_of(data):
            if not needs_channel_id(post):
                continue
            video_id = str(post.get("platform_id") or post.get("code") or "")
            channel_id = resolved.get(video_id)
            if channel_id:
                post["channel_id"] = channel_id
                written += 1
        if written:
            atomic_write_json(path, data)
            total_written += written
            print(f"   {os.path.basename(path)}: {written}건 반영")

    print(f"\n=== 반영 {total_written}건 ===")
    if failed:
        print(f"⚠️ 채우지 못한 video_id {len(failed)}건 (삭제·비공개이거나 조회 실패):")
        for video_id in failed[:20]:
            print(f"   {video_id}")
        if len(failed) > 20:
            print(f"   ... 외 {len(failed) - 20}건")
        print("   재실행하면 이 건들만 다시 시도한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
