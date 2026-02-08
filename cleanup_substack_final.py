import json
import os
import re
from bs4 import BeautifulSoup

def clean_html_to_clean_text(html_content):
    if not html_content:
        return ""
    
    # BeautifulSoup으로 파싱
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. UI 요소 및 기능성 태그 제거
    selectors = ".header-anchor-parent, .image-link-expand, .post-ufi, button, script, style, iframe"
    for ui in soup.select(selectors):
        ui.decompose()

    # 2. <p> 태그를 줄바꿈으로 대체하기 위한 마킹
    for p in soup.find_all("p"):
        p.insert_after("\n")
        p.unwrap()

    # 3. 기타 블록 요소들도 줄바꿈 처리
    for block in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "div", "li", "br"]):
        block.insert_after("\n")
        block.unwrap()

    # 4. 텍스트만 추출
    text = soup.get_text()

    # 5. 남은 모든 HTML 태그 패턴 강제 제거 (정규식)
    text = re.sub(r'<[^>]+>', '', text)

    # 6. 공백 및 개행 정리
    # 줄 끝 공백 제거
    lines = [line.strip() for line in text.split('\n')]
    # 내용이 있는 줄만 남기거나, 단락 구분을 위해 연속 개행은 하나로 유지
    cleaned_text = ""
    last_line_empty = False
    for line in lines:
        if line:
            cleaned_text += line + "\n\n"
            last_line_empty = False
        elif not last_line_empty:
            last_line_empty = True
            
    return cleaned_text.strip()

def finalize_clean_json(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    new_posts = []
    for post in data.get('posts', []):
        # 원하시는 대로 제목과 본문 위주로 정리
        clean_post = {
            "title": post.get("title", ""),
            "subtitle": post.get("subtitle", ""),
            "created_at": post.get("created_at", ""),
            "post_url": post.get("post_url", ""),
            "body_text": clean_html_to_clean_text(post.get("body_html", ""))
        }
        new_posts.append(clean_post)

    final_data = {
        "metadata": data.get("metadata", {}),
        "posts": new_posts
    }
    
    # 불필요한 메타데이터 제거
    if "limit" in final_data["metadata"]:
        del final_data["metadata"]["limit"]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 최종 정제 완료: {output_path}")
    
    # 태그 잔존 여부 체크
    tags_found = False
    for p in new_posts:
        if '<' in p['body_text'] or '>' in p['body_text']:
            tags_found = True
            break
    
    if not tags_found:
        print("✨ 검증 완료: 모든 HTML 태그가 성공적으로 제거되었습니다.")
    else:
        print("⚠️ 주의: 일부 특수 기호(<, >)가 본문에 포함되어 있습니다. 태그인지 확인이 필요합니다.")

if __name__ == "__main__":
    input_file = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208.json'
    output_file = 'output_substack/edwardhan99/substack_edwardhan99_full_20260208_final_clean.json'
    finalize_clean_json(input_file, output_file)