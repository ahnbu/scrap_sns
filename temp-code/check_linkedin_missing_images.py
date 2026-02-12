import json
import os
import glob

# LinkedIn 이미지 스크래핑 화이트리스트 패턴
MEDIA_PATTERNS = [
    "feedshare-shrink_",              # 일반 이미지 게시글
    "image-shrink_",                   # 뉴스레터/기사 이미지
    "feedshare-document-cover-images_", # 슬라이드/PDF 커버
    "feedshare-document-images_",       # 슬라이드/PDF 이미지
    "videocover-",                     # 동영상 썸네일
]

def check_missing_images():
    """링크드인 데이터에서 이미지 누락 현황 체크 (content_type 기반)"""
    
    # 최신 파일 찾기
    linkedin_files = glob.glob('output_linkedin/python/linkedin_py_full_*.json')
    if not linkedin_files:
        print("❌ LinkedIn 데이터 파일을 찾을 수 없습니다.")
        return
    
    latest_file = max(linkedin_files)
    print(f"📂 분석 파일: {latest_file}\n")
    
    # 데이터 로드
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 메타데이터와 포스트 분리
    if isinstance(data, dict) and 'posts' in data:
        posts = data['posts']
        total_count = data.get('metadata', {}).get('total_count', len(posts))
    else:
        posts = data
        total_count = len(posts)
    
    print(f"📊 전체 게시물 수: {total_count}")
    print("=" * 80)
    
    # content_type별 분류
    by_content_type = {
        'text': [],
        'image': [],
        'carousel': [],
        'video': [],
        'document': [],
        'unknown': []
    }
    
    # 실제 누락 게시물 (content_type이 비텍스트인데 media가 없는 경우)
    actually_missing = []
    
    for post in posts:
        content_type = post.get('content_type', 'unknown')
        media = post.get('media', [])
        
        # content_type별 분류
        if content_type in by_content_type:
            by_content_type[content_type].append(post)
        else:
            by_content_type['unknown'].append(post)
        
        # 실제 누락 판정: content_type이 text가 아닌데 media가 비어있는 경우
        if content_type != 'text' and (not media or len(media) == 0):
            actually_missing.append({
                'platform_id': post.get('platform_id'),
                'username': post.get('username'),
                'display_name': post.get('display_name'),
                'date': post.get('date'),
                'content_type': content_type,
                'full_text': post.get('full_text', '')[:50] + '...' if len(post.get('full_text', '')) > 50 else post.get('full_text', ''),
                'url': post.get('url')
            })
    
    # 통계 출력
    print("📊 content_type별 분포:")
    for ctype, posts_list in by_content_type.items():
        count = len(posts_list)
        if count > 0:
            print(f"  - {ctype}: {count}개")
    
    print("\n" + "=" * 80)
    print("🔍 이미지 분석 결과:")
    
    text_only_count = len(by_content_type['text'])
    has_media_count = sum(len(v) for k, v in by_content_type.items() if k != 'text')
    actually_missing_count = len(actually_missing)
    
    print(f"  ✅ 텍스트 전용 게시물: {text_only_count}개")
    print(f"  ✅ 미디어 있는 게시물: {has_media_count - actually_missing_count}개")
    print(f"  ❌ 실제 이미지 누락: {actually_missing_count}개")
    
    if actually_missing_count > 0:
        missing_ratio = (actually_missing_count / total_count * 100)
        print(f"     (전체의 {missing_ratio:.1f}%)")
    
    # 누락된 게시물 상세 정보
    if actually_missing:
        print("\n" + "=" * 80)
        print("📋 실제 이미지 누락 게시물 목록 (최대 20개)")
        print("=" * 80)
        
        for i, post in enumerate(actually_missing[:20], 1):
            print(f"\n{i}. [{post['date']}] {post['display_name']} (type: {post['content_type']})")
            print(f"   ID: {post['platform_id']}")
            print(f"   내용: {post['full_text']}")
            print(f"   URL: {post['url']}")
    
    # 결과 저장
    report = {
        'analyzed_file': latest_file,
        'total_posts': total_count,
        'content_type_distribution': {k: len(v) for k, v in by_content_type.items()},
        'text_only_posts': text_only_count,
        'has_media_posts': has_media_count - actually_missing_count,
        'actually_missing': actually_missing_count,
        'missing_ratio': f'{(actually_missing_count / total_count * 100):.2f}%' if total_count > 0 else '0%',
        'missing_posts': actually_missing
    }
    
    report_file = 'temp-code/linkedin_image_missing_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n\n💾 상세 리포트 저장: {report_file}")

if __name__ == '__main__':
    check_missing_images()
