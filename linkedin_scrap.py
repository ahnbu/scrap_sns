import json
import time
import os
import glob
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# --- 설정 ---
TARGET_URL = "https://www.linkedin.com/my-items/saved-posts/"
LOGIN_URL = "https://www.linkedin.com/login"
AUTH_FILE = "auth_linkedin.json"
DATA_DIR = "d:/Vibe_Coding/sns_crawler/data"
OUTPUT_FILE = os.path.join(DATA_DIR, "linkedin_saved.json")
OUTPUT_FULL_FILE = os.path.join(DATA_DIR, "linkedin_saved_full.json")
TARGET_LIMIT = 50   # 초기 테스트용 제한
CRAWL_MODE = "update only" # "all" or "update only"

# --- 헬퍼 함수 ---
def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_text(text):
    if not text:
        return ""
    # 불필요한 공백/개행 제거
    text = re.sub(r'\s+', ' ', text).strip()
    # "…더보기" 같은 UI 텍스트 제거
    text = text.replace("…더보기", "")
    return text

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
        # 상위 41비트? 아니면 쉬프트? 
        # LinkedIn Snowflake: 첫 41비트가 타임스탬프 (epoch ms)
        # 정확히는: id >> 22 (하위 22비트가 시퀀스/샤드정보)
        timestamp_ms = id_int >> 22
        # Epoch(1970) 기준 ms -> datetime
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y-%m-%d')
    except:
        return datetime.now().strftime('%Y-%m-%d')

# --- 메인 클래스 ---
class LinkedinScraper:
    def __init__(self):
        self.posts = [] # collected data
        self.new_posts_count = 0
        self.stopped_early = False
        self.collected_codes = set()
        
        # 기존 데이터 로드 (증분 업데이트용)
        self.existing_codes = set()
        if CRAWL_MODE == "update only":
            full_data = load_json(OUTPUT_FULL_FILE)
            for p in full_data:
                if "code" in p:
                    self.existing_codes.add(p["code"])
                    
            # 개별 파일들도 체크
            for file_path in glob.glob(os.path.join(DATA_DIR, "linkedin_saved_*.json")):
                if "full" not in file_path:
                    partial_data = load_json(file_path)
                    for p in partial_data:
                        if "code" in p:
                            self.existing_codes.add(p["code"])
                            
            print(f"📊 기존 데이터 {len(self.existing_codes)}개 로드됨 (중복 제외).")

    def manage_login(self, page):
        """로그인 처리 및 세션 관리"""
        if os.path.exists(AUTH_FILE):
            print(f"📂 세션 파일 로드: {AUTH_FILE}")
            try:
                page.goto(TARGET_URL)
                time.sleep(3)
            except Exception as e:
                print(f"⚠️ 페이지 이동 중 에러 (무시): {e}")
            
            current_url = page.url
            if "login" in current_url or "signup" in current_url:
                print("⚠️ 세션 만료됨. 다시 로그인 필요.")
            elif "about:blank" in current_url:
                print("⚠️ 페이지가 로드되지 않았습니다 (about:blank). 재시도 중...")
                page.goto(TARGET_URL)
                time.sleep(3)
                if "about:blank" in page.url:
                     print("❌ 페이지 로드 실패.")
            else:
                print(f"✅ 세션 유효함 (URL: {current_url})")
                return

        if "login" in page.url or "signup" in page.url or "guest" in page.url or "about:blank" in page.url:
            print("🚨 로그인이 필요하거나 페이지 로드에 실패했습니다! (수동 개입 필요)")
            print(f"   현재 URL: {page.url}")
            page.goto(LOGIN_URL)
            print("   로그인을 완료하고 '저장된 게시물' 목록이 보이면 엔터키를 눌러주세요.")
            input(">>> 로그인 완료 후 Enter: ")
            
            page.context.storage_state(path=AUTH_FILE)
            print("💾 새 세션 저장됨.")
            
            if page.url != TARGET_URL:
                page.goto(TARGET_URL)
                time.sleep(3)

    def handle_response(self, response):
        """네트워크 응답 가로채기 (GraphQL)"""
        if TARGET_LIMIT > 0 and len(self.posts) >= TARGET_LIMIT:
            return

        url = response.url
        # LinkedIn Voyager GraphQL 엔드포인트 체크
        if "voyager/api/graphql" in url and response.request.method == "GET":
            try:
                # 쿼리 파라미터나 URL 패턴을 좀 더 정교하게 체크할 수도 있음
                # 예: queryId=voyagerSearchDashClusters...
                
                resp_json = response.json()
                
                # 데이터 파싱 위임
                self.process_network_data(resp_json)
                
            except Exception as e:
                # JSON 파싱 실패 등은 조용히 무시 (다른 요청일 수 있음)
                pass

    def process_network_data(self, json_data):
        """JSON 데이터에서 게시물 정보 추출"""
        if "included" not in json_data:
            return

        # included 배열 순회
        included = json_data.get("included", [])
        
        # included 내의 객체들을 dict로 매핑 (URN -> Object)
        # 참조 해결을 위해 필요할 수 있음
        # urn_map = {item.get("entityUrn"): item for item in included}

        for item in included:
            # 타겟 엔티티 타입 확인
            # EntityResultViewModel이 실제 화면에 보여지는 카드 정보를 담고 있음
            if item.get("$type") == "com.linkedin.voyager.dash.search.EntityResultViewModel":
                self.extract_post_from_view_model(item)

    def extract_post_from_view_model(self, item):
        try:
            entity_urn = item.get("entityUrn", "")
            # URN에서 Activity ID 추출 (예: urn:li:activity:7422...)
            activity_id = extract_urn_id(entity_urn)
            
            if not activity_id or activity_id in self.collected_codes:
                return

            # 중복 체크 (기존 수집 데이터)
            if CRAWL_MODE == "update only" and activity_id in self.existing_codes:
                # print(f"   ⏭️ 이미 수집된 게시물 (Skip): {activity_id}")
                return

            # 1. 텍스트 (summary.text)
            text_obj = item.get("summary", {})
            text = text_obj.get("text", "")
            
            # 2. 작성자 및 링크
            # actorNavigationUrl: https://www.linkedin.com/in/abcd...?
            actor_url_full = item.get("actorNavigationUrl", "")
            user_link = actor_url_full.split("?")[0]
            
            # primarySubtitle: 이름/헤드라인 (예: "Hong GilDong")
            author_obj = item.get("primarySubtitle", {})
            username = author_obj.get("text", "")
            
            # 3. 날짜 (Activity ID 기반)
            date_str = get_date_from_snowflake_id(activity_id)

            # 4. 이미지
            images = []
            embedded = item.get("entityEmbeddedObject", {})
            img_obj = embedded.get("image", {})
            if img_obj:
                img_attrs = img_obj.get("attributes", [])
                for attr in img_attrs:
                    detail = attr.get("detailData", {})
                    vector_img = detail.get("vectorImage", {})
                    if vector_img:
                        root_url = vector_img.get("rootUrl", "")
                        artifacts = vector_img.get("artifacts", [])
                        # 가장 큰 이미지 찾기
                        if artifacts:
                            sorted_artifacts = sorted(artifacts, key=lambda x: x.get("width", 0), reverse=True)
                            best_artifact = sorted_artifacts[0]
                            path_segment = best_artifact.get("fileIdentifyingUrlPathSegment", "")
                            full_img_url = root_url + path_segment
                            images.append(full_img_url)

            # 5. 게시물 링크
            # navigationUrl
            post_url = item.get("navigationUrl", "")
            
            post_data = {
                "code": activity_id,
                "username": username,
                "text": clean_text(text),
                "date": date_str,
                "images": images,
                "user_link": user_link,
                "post_url": post_url,
                "collected_at": datetime.now().isoformat(),
                "source": "network"
            }
            
            self.posts.append(post_data)
            self.collected_codes.add(activity_id)
            print(f"   ⚡ [Network] [{activity_id}] ({date_str}) {username}: {text[:20]}...")

        except Exception as e:
            # print(f"Error parsing item: {e}")
            pass

    def run(self):
        print("🚀 링크드인 스크래퍼 시작 (Network 모드)")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            
            context_options = {"viewport": {"width": 1280, "height": 1000}}
            if os.path.exists(AUTH_FILE):
                context_options["storage_state"] = AUTH_FILE
            
            context = browser.new_context(**context_options)
            page = context.new_page()

            # 네트워크 이벤트 리스너 등록
            page.on("response", self.handle_response)

            self.manage_login(page)
            
            print("📜 스크롤 및 데이터 수집 시작...")
            no_new_data_count = 0
            last_count = 0
            
            # 초기 로딩 대기
            time.sleep(5)
            
            while len(self.posts) < TARGET_LIMIT:
                # 스크롤 다운
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                print(f"   ⬇️ 스크롤 다운... (현재 {len(self.posts)}개)")
                time.sleep(3) # 네트워크 요청 대기
                
                if len(self.posts) == last_count:
                    no_new_data_count += 1
                else:
                    no_new_data_count = 0
                    last_count = len(self.posts)
                
                if no_new_data_count >= 5:
                    print("🛑 더 이상 새로운 데이터가 없습니다.")
                    break
                
                if len(self.posts) >= TARGET_LIMIT:
                    break

            self.save_results()
            browser.close()

    def save_results(self):
        # 1. 이번 실행 데이터 저장
        if self.posts:
            save_json(OUTPUT_FILE, self.posts)
            print(f"💾 수집된 데이터 저장 완료: {OUTPUT_FILE} ({len(self.posts)}개)")
        
        # 2. 전체 데이터 병합
        self.update_full_version()

    def update_full_version(self):
        print("🔄 전체 데이터 병합 중...")
        seen_codes = set()
        final_list = []

        # 기존 전체 파일 로드
        old_full_data = load_json(OUTPUT_FULL_FILE)
        
        # 최신 Full 데이터가 우선 (혹시 모르니)
        # 하지만 보통은 [신규] + [구형] 순으로 저장함
        
        # 1. 신규 데이터 추가
        for post in self.posts:
            code = post.get("code")
            if code and code not in seen_codes:
                final_list.append(post)
                seen_codes.add(code)
        
        # 2. 기존 데이터 추가 (중복 제외)
        for post in old_full_data:
            code = post.get("code")
            if code and code not in seen_codes:
                final_list.append(post)
                seen_codes.add(code)
        
        save_json(OUTPUT_FULL_FILE, final_list)
        print(f"💾 전체 데이터 파일 업데이트 완료: {OUTPUT_FULL_FILE} (총 {len(final_list)}개)")

if __name__ == "__main__":
    scraper = LinkedinScraper()
    scraper.run()