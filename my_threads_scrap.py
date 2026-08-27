"""내 Threads 게시물 수집 - Graph API(MCP) 경로.

계획: _docs/20260827_02_내-쓰레드-글-수집-계획.md (3.2)

수집기 자체는 `D:/vibe-coding/sns_insight_update` 에 있고 이 스크립트는 그것을
호출해 산출물만 받는다. 그 레포는 수정하지 않는다.

⚠️ 그 수집기는 답글을 주지 않는다(계획 1.1 #10). Threads 본문 상한이 499자라
   넘치는 분량이 자기 답글에 있고, 그대로 두면 32건 중 21건의 본문이 끊긴다
   (계획 P2). 그래서 여기서 글마다 `get_thread_replies` 를 한 번 더 부른다.

⚠️ 출력은 저장글과 **다른 파일**이다. 같은 파일을 쓰면 consumer 웨이브에서
   저장글 수집과 동시에 read-modify-write 해 경합이 난다(선례: 계획 20260826_03 3.4.1).
"""

from __future__ import annotations

import io
import os
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _force_utf8_console() -> None:
    """Windows 콘솔 인코딩 문제를 피한다.

    ⚠️ import 시점에 실행하지 않는다. 모듈 수준에서 sys.stdout 을 갈아끼우면
       이 모듈을 import 하는 pytest 의 출력 캡처가 통째로 망가진다
       (선례 실측: 375 errors).
    """
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


from utils.auth_status import exit_auth_required  # noqa: E402
from utils.common import load_json, save_json  # noqa: E402
from utils.my_threads_adapter import (  # noqa: E402
    is_repost,
    merge_own_post,
    select_continuations,
    to_standard_posts,
)

#: 수집기 정본 레포. 두 레포가 같은 ambient Python 을 쓰므로 별도 venv 가 필요 없다.
INSIGHT_REPO = r"D:\vibe-coding\sns_insight_update"
INSIGHT_SRC = os.path.join(INSIGHT_REPO, "src")

OUTPUT_DIR = os.path.join(REPO_ROOT, "output_threads_own", "python")

#: 전수 수집 기준. 내 글은 32건 규모다(계획 1.1 #4).
DEFAULT_LIMIT = 100

#: 답글에서 이어쓰기를 고를 때 요청하는 필드. 기본 필드셋에는 username 이 없어
#: 명시하지 않으면 남의 댓글을 걸러낼 수 없다(계획 3.3).
REPLY_FIELDS = ["id", "text", "timestamp", "username"]

#: 직전 파일 대비 이 비율 미만으로 줄면 저장을 거부한다.
#: 선례(`my_posts_scrap.py`)와 같은 가드다.
REGRESSION_RATIO = 0.5


class SnapshotRegression(RuntimeError):
    """직전 수집 대비 건수가 급감했을 때."""


def output_path(now=None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d")
    return os.path.join(OUTPUT_DIR, f"threads_own_full_{stamp}.json")


def latest_existing_file() -> str | None:
    """가장 최근 내 게시물 full 파일. 없으면 None."""
    if not os.path.isdir(OUTPUT_DIR):
        return None
    files = sorted(
        name for name in os.listdir(OUTPUT_DIR)
        if name.startswith("threads_own_full_") and name.endswith(".json")
    )
    return os.path.join(OUTPUT_DIR, files[-1]) if files else None


def load_existing_posts(path: str | None) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    data = load_json(path, default=None)
    if isinstance(data, dict):
        return data.get("posts", []) or []
    return data or []


def check_regression(previous_count: int, incoming_count: int) -> None:
    """부분 수집이 전수 수집을 덮어쓰는 것을 막는다."""
    if previous_count <= 0:
        return
    if incoming_count < previous_count * REGRESSION_RATIO:
        raise SnapshotRegression(
            f"{previous_count}건 → {incoming_count}건 (기준 {REGRESSION_RATIO:.0%} 미만). "
            f"부분 수집이 전수 수집을 덮어쓰는 것으로 보입니다. "
            f"토큰 상태를 확인하고 다시 실행하거나, 의도한 결과라면 기존 파일을 먼저 옮기세요."
        )


def _ensure_insight_path() -> None:
    if not os.path.isdir(INSIGHT_SRC):
        print(f"❌ [MyThreads] 수집기 경로를 찾을 수 없습니다: {INSIGHT_SRC}", flush=True)
        raise SystemExit(1)
    if INSIGHT_SRC not in sys.path:
        sys.path.insert(0, INSIGHT_SRC)


def collect(limit: int = DEFAULT_LIMIT) -> list:
    """insight 수집기를 호출한다. 인증 만료는 레포 표준 신호로 바꿔 던진다."""
    _ensure_insight_path()

    from sns_insight_update.collectors.threads import (  # noqa: E402
        ThreadsAuthRequired,
        collect_threads_posts,
    )

    try:
        return collect_threads_posts(limit=limit)
    except ThreadsAuthRequired as exc:
        exit_auth_required(
            "threads",
            reason="login_required",
            auth_file=str(exc) or None,
            extra={"scope": "my_posts"},
        )
        raise  # exit_auth_required 가 SystemExit 을 던지므로 도달하지 않는다


def fetch_replies(thread_id: str) -> list[dict]:
    """글 하나의 답글 목록. 실패하면 빈 목록으로 넘어간다.

    답글을 못 가져와도 본문 일부는 살아 있으므로 수집 전체를 멈추지 않는다.
    대신 호출부가 경고를 찍는다.
    """
    _ensure_insight_path()

    from sns_insight_update.collectors.threads_mcp_runner import (  # noqa: E402
        run_threads_mcp_tool,
    )

    response = run_threads_mcp_tool(
        "get_thread_replies", {"thread_id": thread_id, "fields": REPLY_FIELDS}
    )
    if isinstance(response, dict):
        items = response.get("data")
    else:
        items = response
    return [item for item in (items or []) if isinstance(item, dict)]


def collect_continuations(records) -> dict[str, list[dict]]:
    """글마다 자기 답글을 모아 이어쓰기 후보를 돌려준다(계획 3.3).

    무엇을 붙였는지 로그로 남긴다. 30분 기준은 실측 표본이 얇아
    (대화형 답글 1건), 엉뚱한 것이 붙었을 때 눈에 띄어야 한다.
    """
    out: dict[str, list[dict]] = {}
    for record in records:
        api_id = str(getattr(record, "platform_post_id", "") or "")
        if not api_id:
            continue
        try:
            replies = fetch_replies(api_id)
        except Exception as exc:  # noqa: BLE001 - 답글 실패로 수집을 멈추지 않는다
            print(f"   ⚠️ [MyThreads] 답글 조회 실패 ({api_id}): {exc}", flush=True)
            continue

        picked = select_continuations(getattr(record, "created_at", None), replies)
        if not picked:
            continue
        out[api_id] = picked

        added = sum(len(item["text"]) for item in picked)
        day = str(getattr(record, "created_at", "") or "")[:10]
        head = picked[0]["text"][:40].replace("\n", " ")
        print(
            f"   🧵 [MyThreads] 본문 이어붙임 {day} · {len(picked)}개 · +{added}자 · \"{head}…\"",
            flush=True,
        )
    return out


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="내 Threads 게시물 수집")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--no-replies",
        action="store_true",
        help="자기 답글 이어붙이기를 건너뛴다(본문이 잘린 채 저장된다). 디버깅용",
    )
    args = parser.parse_args(argv)

    print("🧵 [MyThreads] 내 Threads 게시물 수집 시작 (Graph API)", flush=True)

    records = collect(limit=args.limit)
    reposts = [r for r in records if is_repost(r.to_dict())]
    if reposts:
        print(f"   ↪️ [MyThreads] 리포스트 {len(reposts)}건 제외", flush=True)
    kept = [r for r in records if not is_repost(r.to_dict())]
    print(f"   📥 [MyThreads] 내 원본 글 {len(kept)}건", flush=True)

    continuations = {} if args.no_replies else collect_continuations(kept)
    if continuations:
        total_added = sum(
            len(item["text"]) for items in continuations.values() for item in items
        )
        print(
            f"   🧵 [MyThreads] 본문 이어붙이기 {len(continuations)}건 / 총 +{total_added}자",
            flush=True,
        )

    incoming = to_standard_posts([r.to_dict() for r in kept], continuations)
    print(f"   🔄 [MyThreads] 표준 스키마 변환 {len(incoming)}건", flush=True)

    previous_path = latest_existing_file()
    existing = load_existing_posts(previous_path)

    try:
        check_regression(len(existing), len(incoming))
    except SnapshotRegression as exc:
        print(f"❌ [MyThreads] 저장 거부 - {exc}", flush=True)
        return 4

    by_id = {str(p.get("platform_id")): p for p in existing if p.get("platform_id")}
    merged = []
    for post in incoming:
        pid = str(post.get("platform_id"))
        merged.append(merge_own_post(by_id.pop(pid, None), post))
    # 이번 수집에 안 잡힌 과거 글은 버리지 않는다(limit 밖일 수 있다).
    merged.extend(by_id.values())

    ordered = sorted(merged, key=lambda p: str(p.get("created_at") or ""), reverse=True)
    for index, post in enumerate(ordered, start=1):
        post["sequence_id"] = index

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    target = output_path()
    save_json(target, {
        "metadata": {
            "updated_at": datetime.now().isoformat(),
            "total_count": len(merged),
            "source": "sns_insight_update/collectors/threads",
        },
        "posts": sorted(merged, key=lambda p: p.get("sequence_id", 0)),
    })

    with_views = sum(1 for p in merged if p.get("view_count") is not None)
    merged_bodies = sum(1 for p in merged if p.get("is_merged_thread"))
    print(f"   💾 [MyThreads] 저장 완료: {os.path.basename(target)} ({len(merged)}건)", flush=True)
    print(
        f"✅ [MyThreads] 내 Threads 게시물 수집 완료 - 총 {len(merged)}건 / "
        f"노출수 보유 {with_views}건 / 본문 이어붙임 {merged_bodies}건",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    _force_utf8_console()
    raise SystemExit(main())
