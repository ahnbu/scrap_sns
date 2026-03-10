import re
from datetime import datetime
from utils.common import clean_text, reorder_post

# 게시물 미디어 URL 패턴 화이트리스트
MEDIA_PATTERNS = [
    "feedshare-shrink_",               # 일반 이미지 게시글
    "image-shrink_",                    # 뉴스레터/기사 이미지
    "feedshare-document-cover-images_", # 슬라이드/PDF 커버
    "feedshare-document-images_",       # 슬라이드/PDF 이미지
    "videocover-",                      # 동영상 썸네일
]

def extract_urn_id(urn):
    # urn:li:activity:7422622332021604353 -> 7422622332021604353
    match = re.search(r'activity:(\d+)', urn)
    return match.group(1) if match else urn

def get_date_from_snowflake_id(id_str):
    """
    LinkedIn Activity ID(Snowflake)에서 타임스탬프 추출
    Bit 0-40: Timestamp (ms)
    """
    try:
        id_int = int(id_str)
        # LinkedIn Snowflake: 첫 41비트가 타임스탬프 (epoch ms)
        # 정확히는: id >> 22 (하위 22비트가 시퀀스/샤드정보)
        timestamp_ms = id_int >> 22
        # Epoch(1970) 기준 ms -> datetime
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return None

def classify_content_type(images):
    """미디어 URL 패턴으로 콘텐츠 유형 분류"""
    if not images:
        return "text"
    for img in images:
        if "videocover-" in img:
            return "video"
        if "feedshare-document" in img:
            return "document"
    return "carousel" if len(images) > 1 else "image"

def find_images_recursively(obj, found_urls=None):
    """객체 내에서 모든 이미지 URL을 재귀적으로 탐색"""
    if found_urls is None: found_urls = []
    if not obj or not isinstance(obj, (dict, list)): return found_urls

    if isinstance(obj, list):
        for item in obj: find_images_recursively(item, found_urls)
        return found_urls

    # 1. VectorImage 구조 (가장 표준적인 고화질 이미지)
    if obj.get("$type") == "com.linkedin.common.VectorImage" or "artifacts" in obj:
        root_url = obj.get("rootUrl", "")
        artifacts = obj.get("artifacts", [])
        if artifacts:
            # 가장 큰 이미지 선택
            best = sorted(artifacts, key=lambda x: x.get("width", 0), reverse=True)[0]
            segment = best.get("fileIdentifyingUrlPathSegment", "")
            full_url = root_url + segment if root_url else segment
            if full_url and "media.licdn.com" in full_url:
                found_urls.append(full_url)
    
    # 2. 고정 URL 구조
    elif "url" in obj and isinstance(obj["url"], str) and "media.licdn.com" in obj["url"]:
        found_urls.append(obj["url"])

    # 3. 더 깊이 탐색
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            find_images_recursively(v, found_urls)
    
    return list(set(found_urls))

def parse_linkedin_post(item, include_images=True, crawl_start_time=None):
    """
    LinkedIn GraphQL JSON item 파싱
    성공 시 dict 반환, 실패/스킵 시 None 반환
    """
    if not crawl_start_time:
        crawl_start_time = datetime.now()
        
    try:
        entity_urn = item.get("entityUrn", "")
        activity_id = extract_urn_id(entity_urn)
        
        if not activity_id:
            return None

        # 1. 텍스트
        text_obj = item.get("summary", {})
        text = text_obj.get("text", "")
        
        # 2. 작성자
        actor_url_full = item.get("actorNavigationUrl", "")
        user_link = actor_url_full.split("?")[0]
        title_obj = item.get("title", {})
        username = title_obj.get("text", "")

        subtitle_obj = item.get("primarySubtitle", {})
        profile_slogan = subtitle_obj.get("text", "")
        date_str = get_date_from_snowflake_id(activity_id)

        # 3. 이미지 수집
        images = []
        if include_images:
            images = find_images_recursively(item)
            embedded = item.get("entityEmbeddedObject")
            if embedded:
                images.extend(find_images_recursively(embedded))
        
        final_images = []
        for img in set(images):
            if any(pattern in img for pattern in MEDIA_PATTERNS):
                final_images.append(img)

        post_url = item.get("navigationUrl", "")
        time_text = item.get("secondarySubtitle", {}).get("text", "").replace(" • ", "").replace("\u2022", "").replace("Edited", "").strip()

        post_data = {
            "platform_id": activity_id,
            "sns_platform": "linkedin",
            "username": user_link.split("/in/")[-1].replace("/", "") if "/in/" in user_link else username,
            "display_name": username,
            "full_text": clean_text(text),
            "media": final_images,
            "url": post_url,
            "created_at": date_str,
            "date": date_str[:10] if date_str else None,
            "crawled_at": crawl_start_time.isoformat(timespec='milliseconds'),
            "source": "network",
            "local_images": [],
            "time_text": time_text,
            "profile_slogan": profile_slogan,
            "user_link": user_link,
            "content_type": classify_content_type(final_images),
            "sequence_id": 0
        }
        
        return reorder_post(post_data)

    except Exception as e:
        return None
