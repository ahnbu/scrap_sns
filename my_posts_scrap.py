"""내 LinkedIn 게시물 성과 수집 - Buffer 공식 API 경로.

계획: _docs/20260826_03_내-게시물-성과지표-통합-수집-계획.md (3.4)
     _docs/20260909_02_내글수집기-Buffer전환대응과-Threads댓글수-부풀림-수행계획.md (T1)

수집기 자체는 `D:/vibe-coding/sns_insight_update` 에 있고 이 스크립트는 그것을
호출해 산출물만 받는다. 그 레포는 수정하지 않는다.

⚠️ 2026-09-05 에 그 레포가 Playwright 로그인 수집을 Buffer 공식 API 로 바꾸고
   옛 수집기를 `_archive/` 로 옮겼다. 여기가 옛 모듈명을 계속 불러 9/6 부터
   `ModuleNotFoundError` 로 4회 연속 죽었다. 그래서 `buffer_cli` 로 옮겼다.

⚠️ 노출수는 Buffer 가 전건 준다(실측 37/37). 옛 로그인 카드는 반응수를 상위 몇 건만
   렌더링해서(5/36) 반응·댓글을 비로그인 경로에 맡겼는데, Buffer 는 셋 다 전건 준다.
   다만 이번 복구는 **원래대로 되돌리는 것**이라 두 경로 분담을 그대로 둔다 -
   이 스크립트는 여전히 `view_count` 만 쓰고 반응·댓글은 건드리지 않는다.
   분담 정리는 별건이다(계획 §4.2).

⚠️ 출력은 저장글과 **다른 파일**이다. 같은 파일을 쓰면 consumer 웨이브에서
   `linkedin_metric_single.py` 와 동시에 read-modify-write 해 경합이 난다(계획 3.4.1).
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
       이 모듈을 import 하는 pytest 의 출력 캡처가 통째로 망가진다(실측: 375 errors).
       스크립트로 실행될 때만 부른다.
    """
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


from utils.auth_status import exit_auth_required  # noqa: E402
from utils.common import load_json, save_json  # noqa: E402
from utils.my_posts_adapter import merge_own_post, to_standard_posts  # noqa: E402

#: 수집기 정본 레포. 두 레포가 같은 ambient Python 을 쓰므로 별도 venv 가 필요 없다
#: (계획 1.1 #23). 경로가 없으면 추측하지 않고 즉시 끊는다.
INSIGHT_REPO = r"D:\vibe-coding\sns_insight_update"
INSIGHT_SRC = os.path.join(INSIGHT_REPO, "src")

OUTPUT_DIR = os.path.join(REPO_ROOT, "output_linkedin_own", "python")

#: 직전 파일 대비 이 비율 미만으로 줄면 저장을 거부한다.
#: sns_insight_update 의 2026-07-15·07-24 데이터 소실 사고에서 가져온 가드다.
REGRESSION_RATIO = 0.5


class SnapshotRegression(RuntimeError):
    """직전 수집 대비 건수가 급감했을 때."""


def output_path(now=None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d")
    return os.path.join(OUTPUT_DIR, f"linkedin_own_full_{stamp}.json")


def latest_existing_file() -> str | None:
    """가장 최근 내 게시물 full 파일. 없으면 None."""
    if not os.path.isdir(OUTPUT_DIR):
        return None
    files = sorted(
        name for name in os.listdir(OUTPUT_DIR)
        if name.startswith("linkedin_own_full_") and name.endswith(".json")
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
    """부분 수집이 전수 수집을 덮어쓰는 것을 막는다.

    스크롤 예산 소진이나 세션 만료로 절반도 못 긁었을 때 조용히 덮어쓰면
    과거 성과 이력이 사라진다. 실제로 그 사고가 두 번 있었다.
    """
    if previous_count <= 0:
        return
    if incoming_count < previous_count * REGRESSION_RATIO:
        raise SnapshotRegression(
            f"{previous_count}건 → {incoming_count}건 (기준 {REGRESSION_RATIO:.0%} 미만). "
            f"부분 수집이 전수 수집을 덮어쓰는 것으로 보입니다. "
            f"세션 상태를 확인하고 다시 실행하거나, 의도한 결과라면 기존 파일을 먼저 옮기세요."
        )


def collect() -> list:
    """insight 수집기를 호출한다. 인증 실패는 레포 표준 신호로 바꿔 던진다.

    Buffer 경로라 브라우저를 띄우지 않는다 - 옛 `scrolls`·`headed` 인자는 없다.
    """
    if not os.path.isdir(INSIGHT_SRC):
        print(
            f"❌ [MyPosts] 수집기 경로를 찾을 수 없습니다: {INSIGHT_SRC}",
            flush=True,
        )
        raise SystemExit(1)

    if INSIGHT_SRC not in sys.path:
        sys.path.insert(0, INSIGHT_SRC)

    from sns_insight_update.collectors.buffer_cli import (  # noqa: E402
        BufferAuthRequired,
        collect_linkedin_posts,
    )

    try:
        return collect_linkedin_posts(limit=None)
    except BufferAuthRequired as exc:
        # exc 메시지에는 키 이름만 담기고 값은 담기지 않는다(buffer_cli 규약).
        exit_auth_required(
            "linkedin",
            reason="buffer_api_key_required",
            auth_file=str(exc) or None,
            extra={"scope": "my_posts"},
        )
        raise  # exit_auth_required 가 SystemExit 을 던지므로 도달하지 않는다


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="내 LinkedIn 게시물 성과 수집")
    parser.parse_args(argv)

    print("🙋 [MyPosts] 내 게시물 성과 수집 시작 (Buffer API)", flush=True)

    records = collect()
    incoming = to_standard_posts([r.to_dict() for r in records])
    print(f"   📥 [MyPosts] 수집 {len(incoming)}건", flush=True)

    previous_path = latest_existing_file()
    existing = load_existing_posts(previous_path)

    try:
        check_regression(len(existing), len(incoming))
    except SnapshotRegression as exc:
        print(f"❌ [MyPosts] 저장 거부 - {exc}", flush=True)
        return 4

    # 필드 단위 병합. 비로그인 경로가 채운 반응·댓글을 로그인 결과가 덮지 않는다.
    by_id = {str(p.get("platform_id")): p for p in existing if p.get("platform_id")}
    merged = []
    for post in incoming:
        pid = str(post.get("platform_id"))
        merged.append(merge_own_post(by_id.pop(pid, None), post))
    # 이번 수집에 안 잡힌 과거 글은 버리지 않는다(스크롤 예산 밖일 수 있다).
    merged.extend(by_id.values())

    for index, post in enumerate(sorted(merged, key=lambda p: str(p.get("created_at") or ""), reverse=True), start=1):
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
    print(f"   💾 [MyPosts] 저장 완료: {os.path.basename(target)} ({len(merged)}건)", flush=True)
    print(f"✅ [MyPosts] 내 게시물 수집 완료 - 총 {len(merged)}건 / 노출수 보유 {with_views}건", flush=True)
    return 0


if __name__ == "__main__":
    _force_utf8_console()
    raise SystemExit(main())
