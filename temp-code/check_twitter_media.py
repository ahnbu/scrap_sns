import json
import os
import glob

def check_twitter_media():
    """트위터 데이터에서 미디어 수집 현황 체크"""
    
    # 최신 파일 찾기
    twitter_files = glob.glob('output_twitter/python/twitter_py_simple_*.json')
    if not twitter_files:
        print("❌ Twitter 데이터 파일을 찾을 수 없습니다.")
        return
    
    latest_file = max(twitter_files)
    print(f"📂 분석 파일: {latest_file}\n")
    
    # 데이터 로드 (UTF-8-SIG로 BOM 처리)
    with open(latest_file, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    # 메타데이터와 포스트 분리
    if isinstance(data, dict) and 'posts' in data:
        posts = data['posts']
        metadata = data.get('metadata', {})
        total_count = metadata.get('total_count', len(posts))
    else:
        posts = data
        total_count = len(posts)
    
    print(f"📊 전체 게시물 수: {total_count}")
    print("=" * 80)
    
    # 미디어 타입별 분류
    only_images = []     # 이미지만 있는 게시물
    only_videos = []     # 비디오만 있는 게시물
    mixed_media = []     # 이미지와 비디오 둘 다 있는 게시물
    no_media = []        # 미디어 없는 게시물
    
    for post in posts:
        media = post.get('media', [])
        
        if not media or len(media) == 0:
            no_media.append(post)
            continue
        
        # 미디어 타입 체크 (URL 패턴으로)
        has_image = any('.jpg' in m or '.png' in m or '.webp' in m for m in media)
        has_video = any('video' in m.lower() or 'amplify' in m.lower() for m in media)
        
        if has_image and has_video:
            mixed_media.append(post)
        elif has_image:
            only_images.append(post)
        elif has_video:
            only_videos.append(post)
    
    total_with_media = len(only_images) + len(only_videos) + len(mixed_media)
    
    # 통계 출력
    print("📊 미디어 타입별 분류:")
    print(f"  ✅ 총 미디어 있음: {total_with_media}개 ({total_with_media*100/total_count:.1f}%)")
    print(f"     - 이미지만: {len(only_images)}개")
    print(f"     - 비디오만: {len(only_videos)}개")
    print(f"     - 이미지+비디오: {len(mixed_media)}개")
    print(f"  ❌ 미디어 없음: {len(no_media)}개 ({len(no_media)*100/total_count:.1f}%)")
    
    # 미디어 없는 게시물 샘플 확인
    if no_media:
        print("\n" + "=" * 80)
        print("📋 미디어 없는 게시물 샘플 (최대 10개)")
        print("=" * 80)
        
        for i, post in enumerate(no_media[:10], 1):
            text = post.get('full_text', '')[:60] + '...' if len(post.get('full_text', '')) > 60 else post.get('full_text', '')
            print(f"\n{i}. [{post.get('date')}] {post.get('display_name')}")
            print(f"   내용: {text}")
            print(f"   URL: {post.get('url')}")
    
    # 미디어 URL 패턴 분석
    print("\n" + "=" * 80)
    print("🔍 미디어 URL 패턴 분석")
    print("=" * 80)
    
    url_patterns = {}
    all_media_posts = only_images + only_videos + mixed_media
    for post in all_media_posts:
        for url in post.get('media', []):
            # 도메인 추출
            if 'twimg.com' in url:
                pattern = 'twimg.com (Twitter 이미지)'
            elif 'video.twimg.com' in url:
                pattern = 'video.twimg.com (Twitter 비디오)'
            elif 'pbs.twimg.com' in url:
                pattern = 'pbs.twimg.com (Twitter 사진)'
            else:
                pattern = '기타'
            
            url_patterns[pattern] = url_patterns.get(pattern, 0) + 1
    
    for pattern, count in sorted(url_patterns.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {pattern}: {count}개")
    
    # 결과 저장
    report = {
        'analyzed_file': latest_file,
        'total_posts': total_count,
        'total_with_media': total_with_media,
        'only_images': len(only_images),
        'only_videos': len(only_videos),
        'mixed_media': len(mixed_media),
        'no_media': len(no_media),
        'media_ratio': f'{total_with_media*100/total_count:.2f}%',
        'url_patterns': url_patterns,
        'sample_no_media': [
            {
                'platform_id': p.get('platform_id'),
                'display_name': p.get('display_name'),
                'date': p.get('date'),
                'full_text': p.get('full_text', '')[:100],
                'url': p.get('url')
            }
            for p in no_media[:20]
        ]
    }
    
    report_file = 'temp-code/twitter_media_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n\n💾 상세 리포트 저장: {report_file}")

if __name__ == '__main__':
    check_twitter_media()
