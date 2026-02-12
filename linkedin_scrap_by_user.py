import json
import time
import os
import re
import argparse
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from utils.json_to_md import convert_json_to_md

# --- 설정 ---
LOGIN_URL = "https://www.linkedin.com/login"
AUTH_FILE = "auth/auth_linkedin.json"
BASE_DATA_DIR = "output_linkedin_user"

# CLI 인자 파싱
parser = argparse.ArgumentParser(description='LinkedIn User Activity Scraper')
parser.add_argument('--user', required=True, help='LinkedIn User ID (slug)')
parser.add_argument('--limit', type=int, default=0, help='Maximum number of posts to scrap (0 for unlimited)')
parser.add_argument('--duration', type=str, help='Scrap range (e.g., 3d, 1m, 1y). Default unit is day if only number is given.')
parser.add_argument('--after', type=str, help='Skip posts newer than this duration (e.g., 1m). Useful for picking up where you left off.')
args = parser.parse_args()

USER_ID = args.user
TARGET_LIMIT = args.limit
DURATION_STR = args.duration
AFTER_STR = args.after

# 경로 설정
USER_DATA_DIR = os.path.join(BASE_DATA_DIR, USER_ID)
UPDATE_DIR = os.path.join(USER_DATA_DIR, "update")
TARGET_URL = f"https://www.linkedin.com/in/{USER_ID}/recent-activity/all/"

CRAWL_START_TIME = datetime.now()
INCLUDE_IMAGES = True

# 브라우저 UI 설정
WINDOW_X = 1000
WINDOW_Y = 0
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 1000

# --- 마이그레이션 로직 ---
def migrate_old_data(user_id):
    old_dir = os.path.join(BASE_DATA_DIR, user_id, "python")
    new_dir = os.path.join(BASE_DATA_DIR, user_id)
    
    if not os.path.exists(old_dir):
        return

    print(f"📦 기존 데이터 마이그레이션 시작: {old_dir} -> {new_dir}")
    
    # 1. full 파일 이동 및 이름 변경
    if os.path.exists(old_dir):
        for f in os.listdir(old_dir):
            if f.startswith("linkedin_py_full_") and f.endswith(".json"):
                old_path = os.path.join(old_dir, f)
                new_filename = f.replace("linkedin_py_full_", f"linkedin_{user_id}_full_")
                new_path = os.path.join(new_dir, new_filename)
                if not os.path.exists(new_path):
                    os.rename(old_path, new_path)
                    print(f"   🚚 이동: {f} -> {new_filename}")
    
    # 2. update 파일 이동 및 이름 변경
    old_update_dir = os.path.join(old_dir, "update")
    new_update_dir = os.path.join(new_dir, "update")
    if os.path.exists(old_update_dir):
        os.makedirs(new_update_dir, exist_ok=True)
        for f in os.listdir(old_update_dir):
            if f.startswith("linkedin_python_update_") and f.endswith(".json"):
                old_path = os.path.join(old_update_dir, f)
                new_filename = f.replace("linkedin_python_update_", f"linkedin_{user_id}_update_")
                new_path = os.path.join(new_update_dir, new_filename)
                if not os.path.exists(new_path):
                    os.rename(old_path, new_path)
                    print(f"   🚚 이동 (update): {f} -> {new_filename}")
        
        # update 폴더 삭제 시도
        try:
            if not os.listdir(old_update_dir):
                os.rmdir(old_update_dir)
        except: pass

    # 3. python 폴더 삭제 시도
    try:
        if os.path.exists(old_dir) and not os.listdir(old_dir):
            os.rmdir(old_dir)
            print(f"   🗑️ 빈 폴더 삭제됨: {old_dir}")
    except: pass

# --- 헬퍼 함수 ---
def parse_duration(duration_str):
    if not duration_str:
        return None
    match = re.match(r'(\d+)([dmy]?)', duration_str.lower())
    if not match:
        try:
            # 숫자만 입력된 경우
            value = int(duration_str)
            return timedelta(days=value)
        except:
            return None
    
    value = int(match.group(1))
    unit = match.group(2) or 'd'
    
    if unit == 'd':
        return timedelta(days=value)
    elif unit == 'm':
        return timedelta(days=value * 30)
    elif unit == 'y':
        return timedelta(days=value * 365)
    return None

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
    text = text.replace("…더보기", "")
    lines = text.split('\n')
    cleaned_lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    return "\n".join(cleaned_lines).strip()

def extract_urn_id(urn):
    match = re.search(r'activity:(\d+)', urn)
    return match.group(1) if match else urn

def get_date_from_snowflake_id(id_str):
    try:
        id_int = int(id_str)
        timestamp_ms = id_int >> 22
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt
    except:
        return None

# --- 메인 클래스 ---
class LinkedinUserScraper:
    def __init__(self):
        # 마이그레이션 실행
        migrate_old_data(USER_ID)

        self.posts = []
        self.collected_codes = set()
        self.stopped_early = False
        self.max_sequence_id = 0
        
        # 결과 요약용 카운터
        self.success_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.duplicate_count = 0 # 기존 데이터 중복에 의한 스킵
        
        # 기간 제한 설정
        self.stop_duration = parse_duration(DURATION_STR)
        self.stop_date = CRAWL_START_TIME - self.stop_duration if self.stop_duration else None
        
        # 시작 지점 설정 (after)
        self.after_duration = parse_duration(AFTER_STR)
        self.after_date = CRAWL_START_TIME - self.after_duration if self.after_duration else None
        
        if self.stop_date:
            print(f"📅 수집 종료 기준: {self.stop_date.strftime('%Y-%m-%d %H:%M:%S')} 이전 글 발견 시 중단")
        if self.after_date:
            print(f"⏭️ 수집 시작 기준: {self.after_date.strftime('%Y-%m-%d %H:%M:%S')} 이전 글부터 수집 시작")

        # 기존 데이터 로드 (시퀀스 ID 및 중복 체크용)
        self.full_file_path = self.get_latest_full_file()
        self.existing_codes = set()
        
        if self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            full_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj
            for p in full_posts:
                if "code" in p:
                    self.existing_codes.add(p["code"])
            if isinstance(full_data_obj, dict):
                self.max_sequence_id = full_data_obj.get("metadata", {}).get("max_sequence_id", 0)
            print(f"📊 기존 데이터 {len(self.existing_codes)}개 로드됨. max_sequence_id: {self.max_sequence_id}")

    def manage_login(self, page):
        if os.path.exists(AUTH_FILE):
            try:
                page.goto(TARGET_URL)
                time.sleep(3)
            except Exception as e:
                print(f"⚠️ 페이지 이동 중 에러: {e}")
            
            if "login" in page.url or "signup" in page.url:
                print("⚠️ 세션 만료됨. 다시 로그인 필요.")
            else:
                return

        print(f"🚨 로그인이 필요합니다! URL: {page.url}")
        page.goto(LOGIN_URL)
        input(">>> 로그인을 완료하고 엔터키를 눌러주세요: ")
        page.context.storage_state(path=AUTH_FILE)
        print("💾 새 세션 저장됨.")
        page.goto(TARGET_URL)
        time.sleep(3)

    def handle_response(self, response):
        if self.stopped_early:
            return

        url = response.url
        if "voyager/api/graphql" in url and response.request.method == "GET":
            try:
                resp_json = response.json()
                self.process_network_data(resp_json)
            except:
                pass

    def process_network_data(self, json_data):
        if "included" not in json_data:
            return
        included = json_data.get("included", [])
        for item in included:
            item_type = item.get("$type")
            if item_type:
                # print(f"   DEBUG: Found type {item_type}") # 너무 많을 수 있으니 주석 처리하거나 필터링
                pass
            if item_type == "com.linkedin.voyager.dash.search.EntityResultViewModel":
                self.extract_post_from_view_model(item)
            elif "feed.Update" in item_type:
                # 사용자의 활동 페이지에서는 feed.Update 타입일 가능성이 높음
                self.extract_post_from_feed_update(item)

    def extract_post_from_feed_update(self, item):
        try:
            if self.stopped_early:
                return

            entity_urn = item.get("entityUrn", "")
            # urn:li:fsd_update:(urn:li:activity:7422694674299109376,MAIN_FEED,EMPTY,DEFAULT,false)
            activity_id_match = re.search(r'activity:(\d+)', entity_urn)
            activity_id = activity_id_match.group(1) if activity_id_match else None
            
            if not activity_id or activity_id in self.collected_codes:
                return
            
            # 기존 데이터 중복 체크
            if activity_id in self.existing_codes:
                self.duplicate_count += 1
                return

            # 날짜 확인
            post_date = get_date_from_snowflake_id(activity_id)
            
            # 1. After Date 체크 (너무 최신인 경우 스킵)
            if self.after_date and post_date and post_date > self.after_date:
                self.skip_count += 1
                return

            # 2. Stop Date 체크 (너무 오래된 경우 중단)
            if self.stop_date and post_date and post_date < self.stop_date:
                print(f"   🛑 기간 제한 도달 ({post_date.strftime('%Y-%m-%d')}) - 수집 중단 예정")
                self.stopped_early = True
                return

            if TARGET_LIMIT > 0 and len(self.posts) >= TARGET_LIMIT:
                print(f"   🛑 개수 제한 도달 ({TARGET_LIMIT}개) - 수집 중단 예정")
                self.stopped_early = True
                return

            # 텍스트 추출 (commentary)
            commentary = item.get("commentary", {})
            text_obj = commentary.get("text", {})
            text = text_obj.get("text", "")

            # 작성자 정보 (actor)
            actor = item.get("actor", {})
            username = actor.get("name", {}).get("text", "")
            profile_slogan = actor.get("description", {}).get("text", "")
            
            # 상대적 시간 추출 (subDescription)
            sub_desc = item.get("subDescription", {})
            time_text = sub_desc.get("text", "").split(" • ")[0].strip()

            # 이미지 추출
            images = []
            content = item.get("content", {})
            if content:
                # imageComponent 처리
                img_comp = content.get("imageComponent")
                if img_comp:
                    imgs = img_comp.get("images", [])
                    for img in imgs:
                        attrs = img.get("attributes", [])
                        for attr in attrs:
                            detail = attr.get("detailData", {})
                            vector = detail.get("vectorImage", {})
                            if vector:
                                root = vector.get("rootUrl", "")
                                arts = vector.get("artifacts", [])
                                if arts:
                                    best = sorted(arts, key=lambda x: x.get("width", 0), reverse=True)[0]
                                    images.append(root + best.get("fileIdentifyingUrlPathSegment", ""))
                
                # articleComponent의 thumbnail 등 추가 가능
                art_comp = content.get("articleComponent")
                if art_comp:
                    limg = art_comp.get("largeImage", {})
                    attrs = limg.get("attributes", [])
                    for attr in attrs:
                        detail = attr.get("detailData", {})
                        vector = detail.get("vectorImage", {})
                        if vector:
                            root = vector.get("rootUrl", "")
                            arts = vector.get("artifacts", [])
                            if arts:
                                best = sorted(arts, key=lambda x: x.get("width", 0), reverse=True)[0]
                                images.append(root + best.get("fileIdentifyingUrlPathSegment", ""))

            post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}"
            
            post_data = {
                "code": activity_id,
                "username": username,
                "created_at": post_date.strftime('%Y-%m-%d %H:%M:%S') if post_date else None,
                "time_text": time_text,
                "full_text": clean_text(text),
                "post_url": post_url,
                "profile_slogan": profile_slogan,
                "images": list(set(images)),
                "user_link": f"https://www.linkedin.com/in/{USER_ID}",

                "crawled_at": CRAWL_START_TIME.isoformat(),
                "content_type": "carousel" if len(images) > 1 else ("image" if images else "text"),
                "source": "network_user_feed"
            }
            
            self.posts.append(post_data)
            self.collected_codes.add(activity_id)
            self.success_count += 1
            print(f"   ⚡ [FeedUpdate] [{activity_id}] ({post_date.strftime('%Y-%m-%d') if post_date else 'N/A'}) {username}: {text[:20]}...")

        except Exception as e:
            self.fail_count += 1
            pass

    def extract_post_from_view_model(self, item):
        try:
            if self.stopped_early:
                return

            entity_urn = item.get("entityUrn", "")
            activity_id = extract_urn_id(entity_urn)
            
            if not activity_id or activity_id in self.collected_codes:
                return

            # 기존 데이터 중복 체크
            if activity_id in self.existing_codes:
                self.duplicate_count += 1
                return

            # 날짜 확인
            post_date = get_date_from_snowflake_id(activity_id)
            if self.stop_date and post_date and post_date < self.stop_date:
                print(f"   🛑 기간 제한 도달 ({post_date.strftime('%Y-%m-%d')}) - 수집 중단 예정")
                self.stopped_early = True
                return

            # 개수 제한 확인
            if TARGET_LIMIT > 0 and len(self.posts) >= TARGET_LIMIT:
                print(f"   🛑 개수 제한 도달 ({TARGET_LIMIT}개) - 수집 중단 예정")
                self.stopped_early = True
                return

            # 데이터 추출
            text_obj = item.get("summary", {})
            text = text_obj.get("text", "")
            
            actor_url_full = item.get("actorNavigationUrl", "")
            user_link = actor_url_full.split("?")[0]
            
            title_obj = item.get("title", {})
            username = title_obj.get("text", "")

            subtitle_obj = item.get("primarySubtitle", {})
            profile_slogan = subtitle_obj.get("text", "")
            
            images = []
            if INCLUDE_IMAGES:
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
                            if artifacts:
                                sorted_artifacts = sorted(artifacts, key=lambda x: x.get("width", 0), reverse=True)
                                full_img_url = root_url + sorted_artifacts[0].get("fileIdentifyingUrlPathSegment", "")
                                images.append(full_img_url)
                        image_url_obj = detail.get("imageUrl", {})
                        if image_url_obj and image_url_obj.get("url"):
                            images.append(image_url_obj.get("url"))

            post_url = item.get("navigationUrl", "")
            time_text = item.get("secondarySubtitle", {}).get("text", "").replace(" • ", "").strip()

            post_data = {
                "code": activity_id,
                "username": username,
                "created_at": post_date.strftime('%Y-%m-%d %H:%M:%S') if post_date else None,
                "time_text": time_text,
                "full_text": clean_text(text),
                "post_url": post_url,
                "profile_slogan": profile_slogan,
                "images": list(set(images)),
                "user_link": user_link,
                "crawled_at": CRAWL_START_TIME.isoformat(),
                "content_type": "carousel" if len(images) > 1 else ("image" if images else "text"),
                "source": "network_user"
            }
            
            self.posts.append(post_data)
            self.collected_codes.add(activity_id)
            self.success_count += 1
            print(f"   ⚡ [Network] [{activity_id}] ({post_date.strftime('%Y-%m-%d') if post_date else 'N/A'}) {username}: {text[:20]}...")

        except Exception as e:
            self.fail_count += 1
            pass

    def get_latest_full_file(self):
        if not os.path.exists(USER_DATA_DIR):
            return None
        # 새 규칙 우선 검색
        files = [f for f in os.listdir(USER_DATA_DIR) if f.startswith(f"linkedin_{USER_ID}_full_") and f.endswith(".json")]
        if not files:
            return None
        files.sort(reverse=True)
        return os.path.join(USER_DATA_DIR, files[0])

    def run(self):
        start_time_dt = datetime.now()
        print(f"🚀 링크드인 사용자 스크래퍼 시작: {USER_ID}")
        print(f"🔗 Target: {TARGET_URL}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[f"--window-position={WINDOW_X},{WINDOW_Y}", f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"])
            context_options = {"viewport": {"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}}
            if os.path.exists(AUTH_FILE):
                context_options["storage_state"] = AUTH_FILE
            
            context = browser.new_context(**context_options)
            page = context.new_page()
            page.on("response", self.handle_response)
            self.manage_login(page)
            
            print("📜 스크롤 및 데이터 수집 시작...")
            no_new_data_count = 0
            last_count = self.success_count + self.skip_count
            time.sleep(5)
            
            while not self.stopped_early:
                try:
                    # '결과 더보기' 버튼 탐지 (클래스 우선)
                    load_more_btn = page.locator('button.scaffold-finite-scroll__load-button')
                    
                    # 텍스트 기반 폴백 탐색
                    if load_more_btn.count() == 0:
                        load_more_btn = page.locator('button:has-text("결과 더보기"), button:has-text("Show more results")')

                    if load_more_btn.count() > 0 and load_more_btn.first.is_visible():
                        print("   🖱️ '결과 더보기' 버튼 클릭")
                        load_more_btn.first.click()
                        time.sleep(3)
                    else:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(3)
                except:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(3)
                
                current_total_count = self.success_count + self.skip_count
                if current_total_count == last_count:
                    no_new_data_count += 1
                else:
                    no_new_data_count = 0
                    last_count = current_total_count
                
                if no_new_data_count >= 5:
                    print("🛑 더 이상 새로운 데이터가 없습니다.")
                    break
                
                if TARGET_LIMIT > 0 and len(self.posts) >= TARGET_LIMIT:
                    break

            self.save_results()
            browser.close()

        end_time_dt = datetime.now()
        duration = end_time_dt - start_time_dt
        
        # 결과 요약 출력
        print("\n" + "="*50)
        print(f"📊 스크래핑 결과 요약 ({USER_ID})")
        print("-" * 50)
        print(f"⏱️  소요 시간: {str(duration).split('.')[0]}")
        print(f"✅ 성공 건수: {self.success_count}개")
        print(f"❌ 실패 건수: {self.fail_count}개")
        print(f"⏭️  범위 제외: {self.skip_count}개 (최신글 무시)")
        print(f"💾 중복 제외: {self.duplicate_count}개 (기존 데이터)")
        print(f"📦 최종 수집: {len(self.posts)}개")
        print("="*50 + "\n")

    def save_results(self):
        if not self.posts:
            print("ℹ️ 수집된 데이터가 없습니다.")
            return

        # 중복 제거 및 정렬
        new_posts = []
        for p in self.posts:
            if p["code"] not in self.existing_codes:
                new_posts.append(p)
        
        if not new_posts:
            print("ℹ️ 모두 이미 수집된 데이터입니다.")
            return

        # 업데이트 파일 저장 (임시 저장용이므로 수집 순서 유지 또는 code 정렬 선택 가능)
        # 여기서는 code 역순(최신순)으로 정렬하여 저장
        new_posts.sort(key=lambda x: int(x['code']), reverse=True)
        
        timestamp = CRAWL_START_TIME.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(UPDATE_DIR, f"linkedin_{USER_ID}_update_{timestamp}.json")
        save_json(update_file, [{"index": i+1, **p} for i, p in enumerate(new_posts)])
        print(f"💾 업데이트 저장: {update_file} ({len(new_posts)}개)")
        
        # 전체 데이터 병합 및 재정렬
        self.update_full_version()

    def update_full_version(self):
        old_posts = []
        existing_merge_history = []
        source_filename = None

        if self.full_file_path:
            source_filename = os.path.basename(self.full_file_path)
            old_data_obj = load_json(self.full_file_path)
            if isinstance(old_data_obj, dict):
                old_posts = old_data_obj.get("posts", [])
                existing_merge_history = old_data_obj.get("metadata", {}).get("merge_history", [])
            else:
                old_posts = old_data_obj

        # 1. 중복 제거 (Code 기준)
        # 수집된 self.posts 전체와 기존 old_posts를 합쳐서 중복을 제거함
        # self.posts에는 이미 new_posts 뿐만 아니라 수집 세션 동안의 모든 포스트가 있을 수 있음
        # 하지만 save_results에서 new_posts만 걸러냈으므로, 여기서는 명확하게 합침
        
        combined_map = {p["code"]: p for p in old_posts}
        new_items_count = 0
        
        for p in self.posts:
            if p["code"] not in combined_map:
                combined_map[p["code"]] = p
                new_items_count += 1
        
        final_posts = list(combined_map.values())

        # 2. 절대적 시간 순서 정렬 (Snowflake ID 기반)
        # Sequence ID 재할당을 위해 오름차순(과거->최신) 정렬 먼저 수행
        final_posts.sort(key=lambda x: int(x['code']))

        # 3. Sequence ID 재할당 (1부터 시작, 과거글이 1번)
        for i, post in enumerate(final_posts):
            post["sequence_id"] = i + 1
        
        self.max_sequence_id = len(final_posts)

        # 4. 최종 저장용 내림차순(최신->과거) 정렬
        final_posts.sort(key=lambda x: int(x['code']), reverse=True)

        merge_history = list(existing_merge_history)
        if new_items_count > 0:
            merge_history.append({
                "merged_at": datetime.now().isoformat(),
                "new_items_count": new_items_count,
                "duplicates_removed": len(self.posts) - new_items_count, # 이번 수집 내에서의 중복
                "source_file": source_filename,
                "user_id": USER_ID,
                "note": "Sorted by Snowflake ID (code)"
            })

        full_file = os.path.join(USER_DATA_DIR, f"linkedin_{USER_ID}_full_{CRAWL_START_TIME.strftime('%Y%m%d')}.json")
        
        full_data = {
            "metadata": {
                "version": "1.1", # 버전 업
                "user_id": USER_ID,
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "max_sequence_id": self.max_sequence_id,
                "limit": TARGET_LIMIT,
                "duration": DURATION_STR,
                "merge_history": merge_history
            },
            "posts": final_posts
        }
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 저장 (정렬 완료): {full_file} (총 {len(final_posts)}개)")
        
        # Markdown 자동 변환
        convert_json_to_md(full_file)

if __name__ == "__main__":
    scraper = LinkedinUserScraper()
    scraper.run()