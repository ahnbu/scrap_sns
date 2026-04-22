import json
import os
import sys

def convert_json_to_md(json_path, output_path=None):
    """
    SNS 스크래퍼 JSON 출력을 Markdown 파일로 변환합니다.
    
    Args:
        json_path (str): 원본 JSON 파일 경로
        output_path (str, optional): 저장할 Markdown 파일 경로. 
                                     지정하지 않으면 JSON 파일명에서 확장자만 .md로 변경하여 사용.
    
    Returns:
        str: 생성된 Markdown 파일 경로 (실패 시 None)
    """
    if not os.path.exists(json_path):
        print(f"⚠️ [JSON2MD] 파일을 찾을 수 없습니다: {json_path}")
        return None
        
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
    except Exception as e:
        print(f"⚠️ [JSON2MD] JSON 로드 실패 ({json_path}): {e}")
        return None

    # 데이터 구조 정규화 (posts 리스트 추출)
    posts = []
    if isinstance(data, dict):
        posts = data.get('posts', [])
    elif isinstance(data, list):
        posts = data
    else:
        print(f"⚠️ [JSON2MD] 지원되지 않는 데이터 형식입니다.")
        return None

    if not posts:
        print(f"ℹ️ [JSON2MD] 변환할 포스트가 없습니다.")
        return None

    # Markdown 변환 로직
    md_lines = []
    
    # 헤더 (Metadata가 있다면 포함)
    if isinstance(data, dict) and 'metadata' in data:
        meta = data['metadata']
        md_lines.append(f"# Data Export Report")
        md_lines.append(f"")
        md_lines.append(f"- **Generated At**: {meta.get('crawled_at') or meta.get('updated_at') or 'N/A'}")
        md_lines.append(f"- **Total Posts**: {len(posts)}")
        md_lines.append(f"")
        md_lines.append(f"---")
        md_lines.append(f"")

    for i, post in enumerate(posts):
        title = post.get('title') or post.get('username') or f"Post {post.get('code')}"
        subtitle = post.get('subtitle') or post.get('profile_slogan') or ""
        created_at = post.get('created_at') or ""
        url = post.get('post_url') or ""
        
        # 본문 텍스트 (Substack은 body_text, 나머지는 full_text)
        body = post.get('body_text') or post.get('full_text') or ""
        
        # 이미지 목록
        images = post.get('images', [])
        
        # MD 작성
        md_lines.append(f"## {i+1}. {title}")
        if subtitle:
            md_lines.append(f"> **Subtitle**: {subtitle}")
        
        md_lines.append(f"> **Date**: {created_at}")
        if url:
            md_lines.append(f"> **Link**: [Original Post]({url})")
        
        md_lines.append(f"")
        md_lines.append(f"{body}")
        md_lines.append(f"")
        
        if images:
            md_lines.append(f"### Images")
            for img_url in images:
                # 로컬 이미지 경로가 있다면 우선 사용 (Optional)
                md_lines.append(f"![Image]({img_url})")
            md_lines.append(f"")
            
        md_lines.append(f"---")
        md_lines.append(f"")

    # 저장 경로 결정
    if not output_path:
        output_path = os.path.splitext(json_path)[0] + ".md"

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(md_lines))
        print(f"📄 [JSON2MD] 변환 완료: {output_path}")
        return output_path
    except Exception as e:
        print(f"⚠️ [JSON2MD] 파일 저장 실패: {e}")
        return None

if __name__ == "__main__":
    # 테스트용 CLI 실행
    if len(sys.argv) > 1:
        convert_json_to_md(sys.argv[1])
