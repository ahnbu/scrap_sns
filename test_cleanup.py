import json
import os
from bs4 import BeautifulSoup

def clean_substack_html(html_content):
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. UI 요소 제거 (링크 버튼, 확장 버튼 등)
    # .header-anchor-parent: 제목 옆의 링크 아이콘
    # .image-link-expand: 이미지 우상단 확대 버튼
    # button, script, style, iframe: 기타 기능성 태그
    for ui_elem in soup.select(".header-anchor-parent, .image-link-expand, button, script, style, iframe"):
        ui_elem.decompose()
        
    # 2. 이미지 캡션 및 기타 불필요한 속성 정리
    for tag in soup.find_all(True):
        # src, href, alt 등 필수 속성만 남기기
        allowed_attrs = ['src', 'href', 'alt', 'width', 'height']
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in allowed_attrs:
                del tag[attr]
                
    # 3. 빈 태그 정리
    for empty_p in soup.find_all("p"):
        if not empty_p.get_text(strip=True) and not empty_p.find("img"):
            empty_p.decompose()
            
    return str(soup).strip()

# 샘플 데이터 테스트
json_path = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208.json'
if os.path.exists(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    sample_post = data['posts'][0]
    original_html = sample_post['body_html']
    cleaned_html = clean_substack_html(original_html)
    
    print("=== Original HTML (Partial) ===")
    print(original_html[:200])
    print("\n=== Cleaned HTML (Partial) ===")
    print(cleaned_html[:200])
    
    # 파일로 저장해서 확인 가능하게 함
    with open('temp_cleaned_sample.html', 'w', encoding='utf-8') as f:
        f.write(f"<h1>{sample_post['title']}</h1>")
        f.write(f"<h3>{sample_post['subtitle']}</h3>")
        f.write("<hr>")
        f.write(cleaned_html)
    print("\n✅ Cleaned sample saved to temp_cleaned_sample.html")
else:
    print(f"File not found: {json_path}")