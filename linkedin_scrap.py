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
AUTH_FILE = "auth/auth_linkedin.json"
DATA_DIR = "d:/Vibe_Coding/scrap_sns/output_linkedin/python"
UPDATE_DIR = os.path.join(DATA_DIR, "update")

# 스크랩 설정
TARGET_LIMIT = 0       # 0 = 무제한
CRAWL_MODE = "all"     # "all" or "update only"
# CRAWL_MODE = "update only"     # "all" or "update only"
CRAWL_START_TIME = datetime.now()
# INCLUDE_IMAGES = False # 이미지 크롤링 포함 여부
INCLUDE_IMAGES = True # 이미지 크롤링 포함 여부

# 브라우저 UI 설정
WINDOW_X = 0           # 화면 가로 위치 (모니터 왼쪽 기준 px)
WINDOW_Y = 520         # 화면 세로 위치 (모니터 위쪽 기준 px)
WINDOW_WIDTH = 900     # 브라우저 너비
WINDOW_HEIGHT = 500    # 브라우저 높이

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
        # LinkedIn Snowflake: 첫 41비트가 타임스탬프 (epoch ms)
        # 정확히는: id >> 22 (하위 22비트가 시퀀스/샤드정보)
        timestamp_ms = id_int >> 22
        # Epoch(1970) 기준 ms -> datetime
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return None

def parse_relative_time(relative_str, base_time):
    """
    "1주", "3일", "5시간" 등 상대적 시간을 절대 시간 문자열로 변환
    """
    if not relative_str:
        return None
        
    # 숫자와 단위 추출 (예: "1주", "10분", "2개월")
    match = re.search(r'(\d+)\s*(분|시간|일|주|개월|년)', relative_str)
    if not match:
        return None
        
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == "분":
        delta = timedelta(minutes=value)
    elif unit == "시간":
        delta = timedelta(hours=value)
    elif unit == "일":
        delta = timedelta(days=value)
    elif unit == "주":
        delta = timedelta(weeks=value)
    elif unit == "개월":
        delta = timedelta(days=value * 30) # 근사치
    elif unit == "년":
        delta = timedelta(days=value * 365) # 근사치
    else:
        return None
        
    target_time = base_time - delta
    return target_time.strftime('%Y-%m-%d %H:%M:%S')


# --- 메인 클래스 ---
class LinkedinScraper:
    def __init__(self):
        self.posts = [] # collected data
        self.new_posts_count = 0
        self.stopped_early = False
        self.collected_codes = set()
        
        # 기존 데이터 로드 (증분 업데이트용)
        self.existing_codes = set()
        self.max_sequence_id = 0
        
        # 전체 파일 경로 (가장 최근 날짜 파일 찾기)
        self.full_file_path = self.get_latest_full_file()
        
        self.stop_codes = []
            
        if CRAWL_MODE == "update only" and self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            full_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj
            
            # 기준 게시물 (최신 5개) 추출 for Stop Condition
            self.stop_codes = [p.get("code") for p in full_posts[:5] if p.get("code")]

            for p in full_posts:
                if "code" in p:
                    self.existing_codes.add(p["code"])
            
            if isinstance(full_data_obj, dict):
                self.max_sequence_id = full_data_obj.get("metadata", {}).get("max_sequence_id", 0)
            
            print(f"📊 기존 데이터 {len(self.existing_codes)}개 로드됨. 현재 max_sequence_id: {self.max_sequence_id}")
            if self.stop_codes:
                print(f"🔄 UPDATE ONLY 모드: {self.stop_codes} 중 하나라도 발견 시 수집을 중단합니다.")

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
            if activity_id in self.existing_codes:
                # UPDATE ONLY 모드이고, stop_codes에 포함된 경우 조기 종료 트리거
                if CRAWL_MODE == "update only" and activity_id in self.stop_codes:
                     if not self.stopped_early:
                        print(f"   🛑 기준 게시물 발견 ({activity_id}) - 조기 종료 예정")
                        self.stopped_early = True
                return

            # 1. 텍스트 (summary.text)
            text_obj = item.get("summary", {})
            text = text_obj.get("text", "")
            
            # 2. 작성자 및 링크
            # actorNavigationUrl: https://www.linkedin.com/in/abcd...?
            actor_url_full = item.get("actorNavigationUrl", "")
            user_link = actor_url_full.split("?")[0]
            
            # title: 이름 (예: "Hong GilDong")
            title_obj = item.get("title", {})
            username = title_obj.get("text", "")

            # primarySubtitle: 프로필 슬로건/헤드라인
            subtitle_obj = item.get("primarySubtitle", {})
            profile_slogan = subtitle_obj.get("text", "")
            
            # 3. 날짜 (Activity ID 기반)
            date_str = get_date_from_snowflake_id(activity_id)

            # 4. 이미지
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
                            # 가장 큰 이미지 찾기
                            if artifacts:
                                sorted_artifacts = sorted(artifacts, key=lambda x: x.get("width", 0), reverse=True)
                                best_artifact = sorted_artifacts[0]
                                path_segment = best_artifact.get("fileIdentifyingUrlPathSegment", "")
                                full_img_url = root_url + path_segment
                                images.append(full_img_url)
                        
                        # Strategy 2: imageUrl.url (Fallback)
                        image_url_obj = detail.get("imageUrl", {})
                        if image_url_obj and image_url_obj.get("url"):
                            images.append(image_url_obj.get("url"))


            # 5. 게시물 링크
            # navigationUrl
            post_url = item.get("navigationUrl", "")
            
            # 4. 상대적 시간 (UI 표시용)
            time_text = item.get("secondarySubtitle", {}).get("text", "").replace(" • ", "").strip()

            post_data = {
                "code": activity_id,
                "username": username,
                "created_at": date_str,
                "time_text": time_text,
                "full_text": clean_text(text),
                "post_url": post_url,
                "profile_slogan": profile_slogan,
                "images": list(set(images)),
                "user_link": user_link,

                "crawled_at": CRAWL_START_TIME.isoformat(),
                "content_type": "carousel" if len(images) > 1 else ("image" if images else "text"),
                "source": "network"
            }
            
            self.posts.append(post_data)
            self.collected_codes.add(activity_id)
            print(f"   ⚡ [Network] [{activity_id}] ({date_str}) {username}: {text[:20]}...")

        except Exception as e:
            # print(f"Error parsing item: {e}")
            pass

    def get_latest_full_file(self):
        if not os.path.exists(DATA_DIR):
            return None
        files = [f for f in os.listdir(DATA_DIR) if f.startswith("linkedin_python_full_") and f.endswith(".json")]
        if not files:
            return None
        # 날짜순 정렬 (파일명에 YYYYMMDD가 포함되어 있으므로 문자열 정렬 가능)
        files.sort(reverse=True)
        return os.path.join(DATA_DIR, files[0])

    def run(self):
        start_time_dt = datetime.now()
        print("🚀 링크드인 스크래퍼 시작 (Network 모드)")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    f"--window-position={WINDOW_X},{WINDOW_Y}",
                    f"--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}"
                ]
            )
            
            # viewport를 None으로 설정하면 브라우저 창 크기에 따라 자동으로 조절됨 (또는 고정값 사용 가능)
            # 여기서는 창 크기와 비례하도록 설정하거나 특정 해상도 고정
            context_options = {"viewport": {"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}}
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
            
            while TARGET_LIMIT == 0 or len(self.posts) < TARGET_LIMIT:
                # 스크롤 다운
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                print(f"   ⬇️ 스크롤 다운... (현재 {len(self.posts)}개)")
                time.sleep(3) # 네트워크 요청 대기
                
                if self.stopped_early:
                    print("🛑 기준 게시물을 모두 확인하여 수집을 종료합니다.")
                    break
                
                if len(self.posts) == last_count:
                    no_new_data_count += 1
                else:
                    no_new_data_count = 0
                    last_count = len(self.posts)
                
                if no_new_data_count >= 5:
                    print("🛑 더 이상 새로운 데이터가 없습니다.")
                    break
                
                if TARGET_LIMIT > 0 and len(self.posts) >= TARGET_LIMIT:
                    break

            self.save_results()
            browser.close()

        end_time_dt = datetime.now()
        duration = end_time_dt - start_time_dt
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        print("\n" + "="*40)
        print(f"시작시간 : {start_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"종료시간 : {end_time_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"소요시간: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print("="*40)

    def save_results(self):
        if not self.posts:
            print("ℹ️ 수집된 새로운 데이터가 없습니다.")
            return

        # 1. 시퀀스 ID 부여
        # JS 방식: maxExistingSeq + newItems.length - i
        # Python에서도 동일한 규칙 적용
        new_posts = sorted(self.posts, key=lambda x: x['code']) # Snowflake ID 기준 시간순
        for i, post in enumerate(new_posts):
            self.max_sequence_id += 1
            post["sequence_id"] = self.max_sequence_id

        # 2. 업데이트 파일 저장 (타임스탬프 적용: YYYYMMDD_HHMMSS)
        timestamp = CRAWL_START_TIME.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(UPDATE_DIR, f"linkedin_python_update_{timestamp}.json")
        
        # JS 방식과 유사하게 index 추가
        final_indexed_posts = []
        for idx, post in enumerate(self.posts):
            final_indexed_posts.append({"index": idx + 1, **post})

        save_json(update_file, final_indexed_posts)
        print(f"💾 업데이트 데이터 저장 완료: {update_file} ({len(self.posts)}개)")
        
        # 3. 전체 데이터 병합 및 저장
        date_str = CRAWL_START_TIME.strftime("%Y%m%d")
        self.update_full_version(date_str)

    def update_full_version(self, date_str):
        print("🔄 전체 데이터 병합 중...")
        
        # 기존 전체 데이터 로드
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

        # 중복 제거 및 신규 추가
        # JS 방식: newItems는 기존에 없는 것들만, 신규를 앞에 배치
        existing_codes = {p["code"] for p in old_posts}
        new_items = [p for p in self.posts if p["code"] not in existing_codes]
        duplicate_count = len(self.posts) - len(new_items)
        
        final_posts = new_items + old_posts
        
        # sequence_id 기준으로 내림차순 정렬 (최신순)
        final_posts.sort(key=lambda x: x.get("sequence_id", 0), reverse=True)

        # merge_history 업데이트
        merge_history = list(existing_merge_history)
        if new_items:
            merge_history.append({
                "merged_at": datetime.now().isoformat(),
                "new_items_count": len(new_items),
                "duplicates_removed": duplicate_count,
                "source_file": source_filename,
                "crawl_mode": CRAWL_MODE
            })

        full_file = os.path.join(DATA_DIR, f"linkedin_python_full_{date_str}.json")
        
        # 메타데이터 구조 (JS 버전 참고)
        legacy_count = len([p for p in final_posts if "collected_at" not in p])
        verified_count = len(final_posts) - legacy_count

        full_data = {
            "metadata": {
                "version": "1.0",
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "max_sequence_id": self.max_sequence_id,
                "first_code": final_posts[0]["code"] if final_posts else None,
                "last_code": final_posts[-1]["code"] if final_posts else None,
                "crawl_mode": CRAWL_MODE,
                "legacy_data_count": legacy_count,
                "verified_data_count": verified_count,
                "merge_history": merge_history
            },
            "posts": final_posts
        }
        
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 파일 저장 완료: {full_file} (총 {len(final_posts)}개)")

if __name__ == "__main__":
    scraper = LinkedinScraper()
    scraper.run()