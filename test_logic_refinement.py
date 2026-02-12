import json
import re
from datetime import datetime
from collections import OrderedDict

def extract_urn_id(urn):
    match = re.search(r'activity:(\d+)', urn)
    return match.group(1) if match else urn

class TestLinkedinParser:
    def __init__(self):
        self.posts = []

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

    def process_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            json_data = json.load(f)
        
        included = json_data.get("included", [])
        for item in included:
            if item.get("$type") == "com.linkedin.voyager.dash.search.EntityResultViewModel":
                self.extract_post(item)

    def extract_post(self, item):
        entity_urn = item.get("entityUrn", "")
        activity_id = extract_urn_id(entity_urn)
        tracking_id = item.get("trackingId", "")
        
        images = self.find_images_recursively(item)
        embedded = item.get("entityEmbeddedObject")
        if embedded:
            images.extend(self.find_images_recursively(embedded))
        
        final_images = [img for img in set(images) if "profile-displayphoto" not in img]
        
        if final_images or tracking_id == "6cPxrLXvTeiGI8LJT6r0oA==":
            print(f"✅ Found Post: {activity_id} (trackingId: {tracking_id})")
            print(f"   📸 Images found: {len(final_images)}")
            for img in final_images:
                print(f"   🔗 {img[:100]}...")

if __name__ == "__main__":
    parser = TestLinkedinParser()
    parser.process_file(r"D:\vibe-coding\scrap_sns\docs\linkedin_saved\response.json")
