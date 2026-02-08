import json
import os
from bs4 import BeautifulSoup

def clean_substack_html(html_content):
    if not html_content:
        return ""
    
    # BeautifulSoup으로 HTML 파싱
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. UI 및 기능성 요소 제거
    # - .header-anchor-parent: 제목 옆의 링크 아이콘
    # - .image-link-expand: 이미지 우상단 확대 버튼
    # - button, script, style, iframe: 기타 기능성 태그
    # - .post-ufi: 좋아요/댓글 버튼 영역
    for ui_elem in soup.select(".header-anchor-parent, .image-link-expand, .post-ufi, button, script, style, iframe"):
        ui_elem.decompose()
        
    # 2. 모든 태그에서 불필요한 속성(Attribute) 삭제
    # - 가독성을 위해 class, id, data-* 등 제거
    # - 이미지의 src, 링크의 href 등 필수 속성만 유지
    for tag in soup.find_all(True):
        allowed_attrs = ['src', 'href', 'alt', 'width', 'height', 'title']
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in allowed_attrs:
                del tag[attr]
                
    # 3. 빈 태그 정리
    # - 텍스트가 없고 이미지도 없는 <p>, <div> 등 제거
    for empty_tag in soup.find_all(["p", "div", "span"]):
        if not empty_tag.get_text(strip=True) and not empty_tag.find("img"):
            empty_tag.decompose()
            
    # 정제된 HTML 문자열 반환
    return str(soup).strip()

def process_substack_json(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"파일을 찾을 수 없습니다: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"🔄 데이터 정제 시작: {len(data.get('posts', []))}개 게시글")
    
    for post in data.get('posts', []):
        original_body = post.get('body_html', '')
        # HTML 정제 로직 적용
        cleaned_body = clean_substack_html(original_body)
        post['body_html'] = cleaned_body
        
    # 별도 파일로 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 정제 완료! 새 파일이 저장되었습니다: {output_path}")

if __name__ == "__main__":
    input_file = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208.json'
    output_file = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208_cleaned.json'
    
    process_substack_json(input_file, output_file)
