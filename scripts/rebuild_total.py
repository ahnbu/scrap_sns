"""수집 없이 통합본만 다시 만든다.

정렬 키·병합 규칙을 손봤을 때 전체 재수집(수십 분 + 로그인) 없이 결과를 보려고
쓴다. 이미 저장된 플랫폼별 full 파일만 다시 합치므로 1분 안에 끝난다.

계획: _docs/20260827_03_내-글-정렬역순-수정과-뷰어-표시옵션-계획(실행완료).md (3.6 T4)

사용:
    python scripts/rebuild_total.py --dry-run   # 저장 없이 순서만 출력
    python scripts/rebuild_total.py             # 통합본 재생성

⚠️ 통합본은 git 추적 대상이다. 결과가 틀렸으면 `git checkout` 으로 되돌린다.
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _force_utf8_console() -> None:
    """Windows 콘솔 인코딩 문제를 피한다.

    ⚠️ `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, ...)` 로 갈아끼우지 않는다.
       원래 stdout 객체가 참조를 잃고 GC 되면서 buffer 를 닫아버려, 출력이 파이프로
       넘어가는 순간 `ValueError: I/O operation on closed file` 로 죽는다(실측).
    ⚠️ import 시점에 실행하지 않는다. 스크립트로 실행될 때만 부른다.
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


from total_scrap import (  # noqa: E402
    _saved_at_key,
    collect_existing_post_state,
    download_images,
    merge_results,
    preserve_existing_local_images,
    save_total,
    select_image_download_posts,
)

#: 미리보기에서 앞뒤로 보여줄 건수
PREVIEW_EDGE = 5


def _preview_sort_key(post):
    """`save_total()` 의 `sort_key` 를 미리보기용으로 재현한다.

    정본은 `total_scrap.save_total.sort_key` 다. 그쪽이 중첩 함수라 밖에서 부를 수
    없어 여기서 같은 식을 쓴다. 정본이 바뀌면 이 함수도 함께 고친다.
    """
    return (_saved_at_key(post), post.get("platform_sequence_id", 0))


def _print_own_preview(posts):
    """내 글이 뷰어에서 어떤 순서로 보일지 저장 없이 보여준다.

    뷰어 「로컬수집순」은 sequence_id 내림차순이므로(web_viewer/script.js),
    정렬 결과를 뒤집어 출력하면 화면 위에서 아래 순서가 된다.
    """
    ordered = sorted(posts, key=_preview_sort_key)
    own_index = {
        id(post): rank
        for rank, post in enumerate(ordered, start=1)
        if post.get("is_own_post") is True
    }
    if not own_index:
        print("   ℹ️ 내 글이 없어 미리보기를 건너뜁니다.")
        return

    for platform in ("linkedin", "threads"):
        group = [
            post for post in ordered
            if post.get("is_own_post") is True
            and str(post.get("sns_platform") or "").lower() == platform
        ]
        if not group:
            continue
        ranks = [own_index[id(post)] for post in group]
        # 뷰어는 큰 번호를 위에 놓는다. 화면 순서로 뒤집는다.
        on_screen = list(reversed(group))
        print(f"\n   🙋 내 {platform} 글 {len(group)}건 / 예상 sequence_id {min(ranks)}~{max(ranks)}")
        print(f"      연속 블록: {'예' if max(ranks) - min(ranks) + 1 == len(ranks) else '아니오'}")
        for label, sample in (("화면 위", on_screen[:PREVIEW_EDGE]), ("화면 아래", on_screen[-PREVIEW_EDGE:])):
            print(f"      [{label}]")
            for post in sample:
                created = str(post.get("created_at") or "")[:19]
                head = str(post.get("full_text") or "").replace("\n", " ")[:34]
                print(f"        {created}  {head}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="수집 없이 통합본만 재생성")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="저장하지 않고 병합 결과와 내 글 예상 순서만 출력",
    )
    args = parser.parse_args(argv)

    print("♻️ [Rebuild] 수집을 건너뛰고 저장된 파일만 다시 합칩니다.", flush=True)

    # 기존 이미지를 보존해 재다운로드를 피한다. 통상 실행과 같은 update 경로를 탄다.
    existing_post_keys, existing_local_images = collect_existing_post_state()

    posts, threads_count, linkedin_count, twitter_count, youtube_count = merge_results()
    if not posts:
        print("❌ [Rebuild] 병합할 데이터가 없습니다.", flush=True)
        return 1

    preserve_existing_local_images(posts, existing_local_images)
    image_posts = select_image_download_posts(posts, "update", existing_post_keys)

    print(
        f"\n   📊 병합 {len(posts)}건 "
        f"(threads {threads_count} / linkedin {linkedin_count} / x {twitter_count} / youtube {youtube_count})",
        flush=True,
    )
    print(f"   🖼️ 이미지 다운로드 대상 {len(image_posts)}건", flush=True)

    if args.dry_run:
        _print_own_preview(posts)
        print("\n✅ [Rebuild] dry-run 종료 - 저장하지 않았습니다.", flush=True)
        return 0

    download_images(image_posts)
    save_total(
        posts,
        threads_count,
        linkedin_count,
        twitter_count,
        youtube_count,
        local_image_link_posts=image_posts,
    )
    print("✅ [Rebuild] 통합본 재생성 완료", flush=True)
    return 0


if __name__ == "__main__":
    _force_utf8_console()
    raise SystemExit(main())
