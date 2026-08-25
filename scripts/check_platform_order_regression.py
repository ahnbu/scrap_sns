"""S14 — 「저장순」 정렬 키 변경이 다른 플랫폼 순서를 흔들지 않았는지 판정한다.

계획서: _docs/20260825_02_유튜브-요약-파이프라인-재설계-구현계획(실행완료).md 3.7.4

유튜브만 playlist_added_at 을 쓰도록 바꿨으므로 Threads·LinkedIn·X 의 상대
순서는 그대로여야 한다. 정렬 키 수정 전에 --snapshot 으로 찍어두고, 통합본을
재생성한 뒤 --compare 로 대조한다.

스냅샷 파일은 logs/ 라 .gitignore 대상이다(local-only). 스크립트만 커밋한다.

종료코드 0 = 통과, 1 = 순서 변경 감지 또는 스냅샷 없음.
"""

import glob
import json
import os
import sys

SNAPSHOT_PATH = 'logs/platform_order_snapshot.json'
WATCHED_PLATFORMS = ('threads', 'linkedin', 'twitter', 'x')


def current_order():
    files = sorted(glob.glob('output_total/total_full_*.json'))
    if not files:
        raise SystemExit('❌ output_total/total_full_*.json 을 찾을 수 없다')
    posts = json.load(open(files[-1], encoding='utf-8-sig'))['posts']
    order = {}
    for post in sorted(posts, key=lambda p: p['sequence_id']):
        platform = str(post.get('sns_platform') or '').lower()
        if platform in WATCHED_PLATFORMS:
            order.setdefault(platform, []).append(str(post.get('platform_id')))
    return order


def main():
    if '--snapshot' in sys.argv:
        order = current_order()
        os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
        with open(SNAPSHOT_PATH, 'w', encoding='utf-8') as handle:
            json.dump(order, handle)
        print('스냅샷 저장:', {key: len(value) for key, value in order.items()})
        return 0

    if not os.path.exists(SNAPSHOT_PATH):
        print(f'❌ 스냅샷이 없다: {SNAPSHOT_PATH}')
        print('   정렬 키를 고치기 전에 --snapshot 을 먼저 실행했어야 한다.')
        return 1

    with open(SNAPSHOT_PATH, encoding='utf-8') as handle:
        before = json.load(handle)
    after = current_order()

    changed = []
    for platform in sorted(set(before) | set(after)):
        old_list = before.get(platform, [])
        new_list = after.get(platform, [])

        # 통합본을 재생성하면 그 사이 신규 글이 수집돼 목록 길이가 달라진다.
        # 그래서 리스트를 통째로 비교하면 안 되고, 양쪽에 공통으로 있는 항목의
        # 상대 순서만 본다 - 정렬 키가 흔들렸는지는 그것으로 판정된다.
        common = set(old_list) & set(new_list)
        old_seq = [pid for pid in old_list if pid in common]
        new_seq = [pid for pid in new_list if pid in common]
        same = old_seq == new_seq
        if not same:
            changed.append(platform)

        added = len(new_list) - len(common)
        removed = len(old_list) - len(common)
        note = f'공통 {len(common)}건'
        if added:
            note += f', 신규 +{added}'
        if removed:
            note += f', 사라짐 -{removed}'
        print(f'{platform:<10} {"OK" if same else "CHANGED"}  '
              f'{len(old_list)}건 → {len(new_list)}건 ({note})')

        if not same:
            for index, (old_pid, new_pid) in enumerate(zip(old_seq, new_seq)):
                if old_pid != new_pid:
                    print(f'           첫 불일치 {index}번째: {old_pid} → {new_pid}')
                    break

    if changed:
        print(f'\n❌ 상대 순서가 바뀐 플랫폼: {", ".join(changed)}')
        return 1
    print('\n✅ 타 플랫폼 상대 순서 불변')
    return 0


if __name__ == '__main__':
    sys.exit(main())
