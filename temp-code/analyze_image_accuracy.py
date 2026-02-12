"""현재 find_images_recursively 로직으로 어떤 이미지가 추출되는지 게시글별로 상세 분석"""
import json
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(base_dir, '..', 'docs', 'linkedin_saved', 'response.json')
output_path = os.path.join(base_dir, 'image_accuracy_analysis.txt')

with open(json_path, 'r', encoding='utf-8-sig') as f:
    data = json.load(f)

def find_images_recursively_debug(obj, found=None, path="root"):
    """디버그 버전: 이미지 발견 경로도 함께 기록"""
    if found is None:
        found = []
    if not obj or not isinstance(obj, (dict, list)):
        return found
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            find_images_recursively_debug(item, found, f"{path}[{i}]")
        return found
    
    if obj.get("$type") == "com.linkedin.common.VectorImage" or "artifacts" in obj:
        root_url = obj.get("rootUrl", "")
        artifacts = obj.get("artifacts", [])
        if artifacts:
            best = sorted(artifacts, key=lambda x: x.get("width", 0), reverse=True)[0]
            segment = best.get("fileIdentifyingUrlPathSegment", "")
            full_url = root_url + segment if root_url else segment
            if full_url and "media.licdn.com" in full_url:
                # 이미지 유형 판별
                if "feedshare-shrink" in root_url:
                    img_type = "FEEDSHARE (게시물 이미지)"
                elif "articleshare-shrink" in root_url:
                    img_type = "ARTICLESHARE (기사 미리보기)"
                elif "profile-displayphoto" in full_url:
                    img_type = "PROFILE (프로필 사진)"
                else:
                    img_type = f"OTHER ({root_url[:50]})"
                
                found.append({
                    'url': full_url,
                    'type': img_type,
                    'path': path,
                    'width': best.get('width'),
                    'height': best.get('height'),
                    'root_url': root_url
                })
    elif "url" in obj and isinstance(obj["url"], str) and "media.licdn.com" in obj["url"]:
        found.append({
            'url': obj["url"],
            'type': "DIRECT_URL",
            'path': path,
            'width': None,
            'height': None,
            'root_url': ''
        })
    
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            find_images_recursively_debug(v, found, f"{path}.{k}")
    
    return found

included = data.get("included", [])
lines = []

for item in included:
    if item.get("$type") != "com.linkedin.voyager.dash.search.EntityResultViewModel":
        continue
    
    title = item.get("title", {}).get("text", "N/A")
    tracking_id = item.get("trackingId", "N/A")
    
    # 현재 로직 시뮬레이션
    all_images = find_images_recursively_debug(item)
    
    # 현재 필터 (profile-displayphoto만 제외)
    current_filter = [img for img in all_images if "profile-displayphoto" not in img['url']]
    
    # 제안 필터 (feedshare-shrink만 포함)
    proposed_filter = [img for img in all_images if "feedshare-shrink" in img.get('root_url', '')]
    
    lines.append(f"\n{'='*80}")
    lines.append(f"게시글: {title}")
    lines.append(f"trackingId: {tracking_id}")
    lines.append(f"{'='*80}")
    
    lines.append(f"\n  [전체 발견] {len(all_images)}개:")
    for img in all_images:
        lines.append(f"    - {img['type']} | {img['width']}x{img['height']}")
        lines.append(f"      경로: {img['path']}")
        lines.append(f"      URL: {img['url'][:120]}")
    
    lines.append(f"\n  [현재 필터 적용 후 (profile-displayphoto 제외)] {len(current_filter)}개:")
    for img in current_filter:
        lines.append(f"    - {img['type']} | {img['url'][:120]}")
    
    lines.append(f"\n  [제안 필터 (feedshare-shrink만)] {len(proposed_filter)}개:")
    for img in proposed_filter:
        lines.append(f"    - {img['type']} | {img['url'][:120]}")

# 요약
lines.append(f"\n\n{'='*80}")
lines.append("=== 요약 ===")
lines.append(f"{'='*80}")

total_current = 0
total_proposed = 0
for item in included:
    if item.get("$type") != "com.linkedin.voyager.dash.search.EntityResultViewModel":
        continue
    all_images = find_images_recursively_debug(item)
    current = [img for img in all_images if "profile-displayphoto" not in img['url']]
    proposed = [img for img in all_images if "feedshare-shrink" in img.get('root_url', '')]
    total_current += len(current)
    total_proposed += len(proposed)

lines.append(f"현재 필터(profile-displayphoto 제외): 총 {total_current}개")
lines.append(f"제안 필터(feedshare-shrink만): 총 {total_proposed}개")

with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"분석 완료: {output_path}")
print(f"현재 필터: {total_current}개 | 제안 필터: {total_proposed}개")
