"""수정된 화이트리스트 필터의 정확도 검증"""
import json
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(base_dir, '..', 'docs', 'linkedin_saved', 'response.json')

with open(json_path, 'r', encoding='utf-8-sig') as f:
    data = json.load(f)

MEDIA_PATTERNS = [
    "feedshare-shrink_",
    "image-shrink_",
    "feedshare-document-cover-images_",
    "feedshare-document-images_",
    "videocover-",
]

def find_images_recursively(obj, found_urls=None):
    if found_urls is None: found_urls = []
    if not obj or not isinstance(obj, (dict, list)): return found_urls
    if isinstance(obj, list):
        for item in obj: find_images_recursively(item, found_urls)
        return found_urls
    if obj.get("$type") == "com.linkedin.common.VectorImage" or "artifacts" in obj:
        root_url = obj.get("rootUrl", "")
        artifacts = obj.get("artifacts", [])
        if artifacts:
            best = sorted(artifacts, key=lambda x: x.get("width", 0), reverse=True)[0]
            segment = best.get("fileIdentifyingUrlPathSegment", "")
            full_url = root_url + segment if root_url else segment
            if full_url and "media.licdn.com" in full_url:
                found_urls.append(full_url)
    elif "url" in obj and isinstance(obj["url"], str) and "media.licdn.com" in obj["url"]:
        found_urls.append(obj["url"])
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            find_images_recursively(v, found_urls)
    return list(set(found_urls))

def classify_content_type(images):
    if not images: return "text"
    for img in images:
        if "videocover-" in img: return "video"
        if "feedshare-document" in img: return "document"
    return "carousel" if len(images) > 1 else "image"

included = data.get("included", [])
total = 0

print("=" * 70)
print("수정된 화이트리스트 필터 검증 결과")
print("=" * 70)

for item in included:
    if item.get("$type") != "com.linkedin.voyager.dash.search.EntityResultViewModel":
        continue
    
    title = item.get("title", {}).get("text", "N/A")
    
    all_images = find_images_recursively(item)
    embedded = item.get("entityEmbeddedObject")
    if embedded:
        all_images.extend(find_images_recursively(embedded))
    
    # 화이트리스트 필터
    final = [img for img in set(all_images) if any(p in img for p in MEDIA_PATTERNS)]
    ct = classify_content_type(final)
    total += len(final)
    
    if final:
        print(f"\n✅ {title}")
        print(f"   content_type: {ct}")
        for img in final:
            # 패턴 식별
            matched = [p for p in MEDIA_PATTERNS if p in img]
            print(f"   → [{matched[0]}] {img[:100]}...")
    else:
        print(f"\n⬜ {title} → text (미디어 없음)")

print(f"\n{'=' * 70}")
print(f"총 수집 미디어: {total}개")
print(f"{'=' * 70}")
