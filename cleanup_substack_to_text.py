import json
import os
import re
from bs4 import BeautifulSoup

def clean_to_plain_text(html_content):
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. UI 요소 제거 (이전 로직 활용)
    for ui_elem in soup.select(".header-anchor-parent, .image-link-expand, .post-ufi, button, script, style, iframe"):
        ui_elem.decompose()

    # 2. <p> 태그 뒤에 개행 추가
    for p in soup.find_all("p"):
        p.insert_after("\n")
        
    # 3. 기타 주요 태그 뒤에도 개행 추가 (제목 등)
    for block in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "div", "li", "br"]):
        block.insert_after("\n")
        
    # 4. 모든 태그 제거 및 텍스트만 추출
    text = soup.get_text()
    
    # 5. 여러 개의 연속된 개행 정리 (최대 2개까지)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    
    return text.strip()

def process_substack_json_to_text(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"File not found: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Processing {len(data.get('posts', []))} posts...")
    
    for post in data.get('posts', []):
        post['body_text'] = clean_to_plain_text(post.get('body_html', ''))
        # HTML 원본은 유지하되 body_text 필드 추가 (비교용)
        
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Success! Cleaned text saved to: {output_path}")

if __name__ == "__main__":
    input_file = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208.json'
    output_file = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208_text_only.json'
    process_substack_json_to_text(input_file, output_file)