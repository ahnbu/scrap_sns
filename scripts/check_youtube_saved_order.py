"""S13 — 유튜브 「저장순」이 재생목록 추가 최신순과 일치하는지 판정한다.

계획서: _docs/20260825_02_유튜브-요약-파이프라인-재설계-구현계획(실행완료).md 3.7.4

뷰어의 「저장순」은 sequence_id 내림차순이다(web_viewer/script.js sortPosts).
그 순서가 playlist_added_at 내림차순과 같으면 스피어만 상관이 +1.0 이다.
수정 전 실측값은 -1.000(완전 역순)이었다.

종료코드 0 = 통과, 1 = 불일치.
"""

import glob
import json
import sys


def main():
    files = sorted(glob.glob('output_total/total_full_*.json'))
    if not files:
        print('❌ output_total/total_full_*.json 을 찾을 수 없다')
        return 1

    posts = json.load(open(files[-1], encoding='utf-8-sig'))['posts']
    videos = [p for p in posts if str(p.get('sns_platform') or '').lower() == 'youtube']
    count = len(videos)
    if count < 2:
        print(f'⚠️ 유튜브 게시글이 {count}건이라 순서를 판정할 수 없다')
        return 1

    viewer_rank = {
        p['platform_id']: index
        for index, p in enumerate(sorted(videos, key=lambda p: -p['sequence_id']))
    }
    wanted_rank = {
        p['platform_id']: index
        for index, p in enumerate(sorted(
            videos, key=lambda p: str(p.get('playlist_added_at') or ''), reverse=True))
    }

    squared = sum((viewer_rank[key] - wanted_rank[key]) ** 2 for key in viewer_rank)
    rho = round(1 - 6 * squared / (count * (count * count - 1)), 3)

    print(f'파일: {files[-1]}')
    print(f'유튜브 {count}건 스피어만 상관: {rho}  (1.0 = 저장순이 재생목록 추가순과 일치)')
    if rho != 1.0:
        worst = sorted(viewer_rank, key=lambda k: -abs(viewer_rank[k] - wanted_rank[k]))[:5]
        print('가장 많이 어긋난 5건:')
        for key in worst:
            print(f'  {key}  뷰어 {viewer_rank[key]:>3}위 ↔ 실제 {wanted_rank[key]:>3}위')
    return 0 if rho == 1.0 else 1


if __name__ == '__main__':
    sys.exit(main())
