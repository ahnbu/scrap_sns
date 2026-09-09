"""내 Threads 게시물 수집 - Buffer 공식 API 경로.

계획: _docs/20260827_02_내-쓰레드-글-수집-계획.md (3.2)
     _docs/20260909_02_내글수집기-Buffer전환대응과-Threads댓글수-부풀림-수행계획.md (T2·T5-b)

수집기 자체는 `D:/vibe-coding/sns_insight_update` 에 있고 이 스크립트는 그것을
호출해 산출물만 받는다. 그 레포는 수정하지 않는다.

⚠️ 2026-09-05 에 그 레포가 Threads MCP 수집을 Buffer 공식 API 로 바꾸고 옛 수집기와
   `threads_mcp_runner` 를 `_archive/` 로 옮겼다. 여기가 옛 모듈명을 계속 불러
   9/6 부터 `ModuleNotFoundError` 로 4회 연속 죽었다.

🔴 **자기 답글 이어붙이기가 사라졌다.** Threads 본문 상한이 499자라 넘치는 분량이
   자기 답글에 있는데, 그것을 가져오던 `get_thread_replies` 가 MCP 러너와 함께
   창고로 갔다. Buffer 에는 대응 API 가 없다 - `metadata.thread.text` 는 Buffer 로
   **발행한** 글에만 채워지고(실측 34건 중 2건), 나머지 32건은 빈 배열이다.

   그래서 **이미 합쳐져 저장된 22건(16,480자)을 지키는 쪽**으로 방향을 바꿨다.
   `utils/my_threads_adapter.merge_own_post()` 가 `full_text`·`is_merged_thread`·
   `media` 를 보존한다. 그 보존이 깨지면 본문이 9,352자로 줄어든다(43% 손실).
   신규 글의 타래글은 당분간 수집하지 않는다 - 재검토 조건은 계획 §4.3.

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
    to_standard_posts,
)

#: 수집기 정본 레포. 두 레포가 같은 ambient Python 을 쓰므로 별도 venv 가 필요 없다.
INSIGHT_REPO = r"D:\vibe-coding\sns_insight_update"
INSIGHT_SRC = os.path.join(INSIGHT_REPO, "src")

OUTPUT_DIR = os.path.join(REPO_ROOT, "output_threads_own", "python")

#: 전수 수집 기준. 내 글은 34건 규모다.
DEFAULT_LIMIT = 100

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
    """insight 수집기를 호출한다. 인증 실패는 레포 표준 신호로 바꿔 던진다.

    Buffer 경로라 MCP 프로세스를 띄우지 않는다.
    """
    _ensure_insight_path()

    from sns_insight_update.collectors.buffer_cli import (  # noqa: E402
        BufferAuthRequired,
        collect_threads_posts,
    )

    try:
        return collect_threads_posts(limit=limit)
    except BufferAuthRequired as exc:
        # exc 메시지에는 키 이름만 담기고 값은 담기지 않는다(buffer_cli 규약).
        exit_auth_required(
            "threads",
            reason="buffer_api_key_required",
            auth_file=str(exc) or None,
            extra={"scope": "my_posts"},
        )
        raise  # exit_auth_required 가 SystemExit 을 던지므로 도달하지 않는다


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="내 Threads 게시물 수집")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)

    print("🧵 [MyThreads] 내 Threads 게시물 수집 시작 (Buffer API)", flush=True)

    records = collect(limit=args.limit)
    # ⚠️ Buffer 레코드에는 `raw.thread.media_type` 이 없어 이 판정이 항상 거짓이다.
    #    Buffer 가 리포스트를 돌려주면 걸러지지 않는다 - 실측 34건에는 없었다.
    reposts = [r for r in records if is_repost(r.to_dict())]
    if reposts:
        print(f"   ↪️ [MyThreads] 리포스트 {len(reposts)}건 제외", flush=True)
    kept = [r for r in records if not is_repost(r.to_dict())]
    print(f"   📥 [MyThreads] 내 원본 글 {len(kept)}건", flush=True)

    # 이어쓰기는 수집하지 않는다(모듈 docstring 참조). 기존 합본은
    # merge_own_post() 가 지킨다.
    incoming = to_standard_posts([r.to_dict() for r in kept])
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
            "source": "sns_insight_update/collectors/buffer_cli",
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
