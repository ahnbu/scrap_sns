"""LinkedIn API 응답에서 게시물 이미지(feedshare)를 찾는 재귀 탐색 스크립트 - 결과를 파일로 저장"""
import json
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
json_path = os.path.join(base_dir, 'docs', 'linkedin_saved', 'response.json')
output_path = os.path.join(base_dir, 'temp-code', 'analysis_result.txt')

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

lines = []

# 1. feedshare 이미지 찾기
image_results = []

def find_feedshare_images(obj, path="root"):
    if isinstance(obj, dict):
        root_url = obj.get('rootUrl', '')
        if isinstance(root_url, str) and 'feedshare-shrink' in root_url:
            artifacts = obj.get('artifacts', [])
            asset = obj.get('digitalmediaAsset', 'N/A')
            image_results.append({
                'path': path,
                'rootUrl': root_url,
                'digitalmediaAsset': asset,
                'artifacts': artifacts
            })
            return
        for key, value in obj.items():
            find_feedshare_images(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_feedshare_images(item, f"{path}[{i}]")

find_feedshare_images(data)

lines.append(f"=== feedshare(게시물) 이미지 발견: {len(image_results)}개 ===\n")
for idx, result in enumerate(image_results):
    lines.append(f"--- 이미지 #{idx + 1} ---")
    lines.append(f"  경로: {result['path']}")
    lines.append(f"  digitalmediaAsset: {result['digitalmediaAsset']}")
    lines.append(f"  rootUrl: {result['rootUrl']}")
    lines.append(f"  해상도 옵션 ({len(result['artifacts'])}개):")
    for art in result['artifacts']:
        full_url = result['rootUrl'] + art.get('fileIdentifyingUrlPathSegment', '')
        lines.append(f"    - {art.get('width')}x{art.get('height')} => {full_url}")
    lines.append("")

# 2. articleshare 이미지 찾기
article_results = []
def find_articleshare_images(obj, path="root"):
    if isinstance(obj, dict):
        root_url = obj.get('rootUrl', '')
        if isinstance(root_url, str) and 'articleshare-shrink' in root_url:
            artifacts = obj.get('artifacts', [])
            article_results.append({
                'path': path,
                'rootUrl': root_url,
                'artifacts': artifacts
            })
            return
        for key, value in obj.items():
            find_articleshare_images(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_articleshare_images(item, f"{path}[{i}]")

find_articleshare_images(data)
lines.append(f"\n=== articleshare(기사 미리보기) 이미지 발견: {len(article_results)}개 ===")
for r in article_results:
    lines.append(f"  {r['rootUrl']}")

# 3. 게시글 제목/trackingId 목록
lines.append(f"\n\n=== 게시글 목록 (included 배열에서 EntityResultViewModel 찾기) ===")
included = data.get('included', [])
if not included:
    # data.data 아래에서 찾기
    included = data.get('data', {}).get('included', [])

lines.append(f"included 배열 길이: {len(included)}")

# included에서 trackingId 있는 엔티티 찾기
entity_count = 0
for idx, item in enumerate(included):
    type_val = item.get('$type', '')
    if 'EntityResultViewModel' in type_val:
        entity_count += 1
        title_obj = item.get('title')
        title = title_obj.get('text', 'N/A')[:50] if isinstance(title_obj, dict) else 'N/A'
        tid = item.get('trackingId', 'N/A')
        nav_url = item.get('navigationUrl', 'N/A')[:100]
        
        # embedded 이미지 확인
        embedded = item.get('entityEmbeddedObject')
        has_feedshare = False
        if embedded and embedded.get('image'):
            for attr in embedded['image'].get('attributes', []):
                vi = attr.get('detailData', {}).get('vectorImage')
                if vi and 'feedshare-shrink' in vi.get('rootUrl', ''):
                    has_feedshare = True
        
        img_mark = " *** HAS FEEDSHARE IMAGE ***" if has_feedshare else ""
        lines.append(f"  [{idx}] trackingId={tid} | {title}{img_mark}")
        lines.append(f"       url: {nav_url}")

lines.append(f"\nEntityResultViewModel 총: {entity_count}개")

# 4. 최상위 JSON 구조 분석
lines.append(f"\n\n=== JSON 최상위 구조 ===")
def describe_structure(obj, prefix='', depth=0, max_depth=3):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k in sorted(obj.keys()):
            if k.startswith('$'):
                continue
            v = obj[k]
            if v is None:
                continue
            if isinstance(v, dict):
                lines.append(f"{prefix}{k}/ (dict, {len(v)} keys)")
                if depth < 2:
                    describe_structure(v, prefix + '  ', depth + 1, max_depth)
            elif isinstance(v, list):
                lines.append(f"{prefix}{k}[] (list, len={len(v)})")
            elif isinstance(v, str):
                lines.append(f"{prefix}{k}: {v[:80]}")
            else:
                lines.append(f"{prefix}{k}: {v}")

describe_structure(data)

with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"분석 결과가 {output_path} 에 저장되었습니다.")
print(f"feedshare 이미지: {len(image_results)}개")
print(f"articleshare 이미지: {len(article_results)}개")
