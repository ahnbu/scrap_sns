import json
import re
import os
import urllib.request

def extract_urn_id(urn):
    match = re.search(r'activity:(\d+)', urn)
    return match.group(1) if match else urn

class ImageDownloader:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def find_images_recursively(self, obj, found_urls=None):
        if found_urls is None: found_urls = []
        if not obj or not isinstance(obj, (dict, list)): return found_urls
        if isinstance(obj, list):
            for item in obj: self.find_images_recursively(item, found_urls)
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
                self.find_images_recursively(v, found_urls)
        return list(set(found_urls))

    def download_images(self, file_path):
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            json_data = json.load(f)
        included = json_data.get("included", [])
        count = 0
        for item in included:
            if item.get("$type") == "com.linkedin.voyager.dash.search.EntityResultViewModel":
                tracking_id = item.get("trackingId", "unknown")
                images = self.find_images_recursively(item)
                embedded = item.get("entityEmbeddedObject")
                if embedded:
                    images.extend(self.find_images_recursively(embedded))
                # 화이트리스트: 게시물 미디어 패턴만 수집
                MEDIA_PATTERNS = [
                    "feedshare-shrink_",               # 일반 이미지 게시글
                    "image-shrink_",                    # 뉴스레터/기사 이미지
                    "feedshare-document-cover-images_", # 슬라이드/PDF 커버
                    "feedshare-document-images_",       # 슬라이드/PDF 이미지
                    "videocover-",                      # 동영상 썸네일
                ]
                final_images = [img for img in set(images) if any(p in img for p in MEDIA_PATTERNS)]
                for idx, img_url in enumerate(final_images):
                    try:
                        file_name = f"image_{count}_{idx}.jpg"
                        full_path = os.path.join(self.output_dir, file_name)
                        req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req) as response, open(full_path, 'wb') as out_file:
                            out_file.write(response.read())
                        print(f"✅ Downloaded: {file_name} from Post {tracking_id}")
                        count += 1
                        if count >= 5: return
                    except Exception as e:
                        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    downloader = ImageDownloader(os.path.join(base_dir, "docs", "linkedin_saved", "test_images"))
    downloader.download_images(os.path.join(base_dir, "docs", "linkedin_saved", "response.json"))
