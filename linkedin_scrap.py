from utils.common import load_json, save_json, clean_text, reorder_post, format_timestamp, parse_relative_time
import json
import time
import os
import glob
import re
import argparse
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from utils.json_to_md import convert_json_to_md

# --- 설정 ---
TARGET_URL = "https://www.linkedin.com/my-items/saved-posts/"
LOGIN_URL = "https://www.linkedin.com/login"
AUTH_FILE = "auth/auth_linkedin.json"
DATA_DIR = "output_linkedin/python"
UPDATE_DIR = os.path.join(DATA_DIR, "update")

# 스크랩 설정
TARGET_LIMIT = 0       # 0 = 무제한

# CLI 인자 파싱
CRAWL_MODE = "update only"  # 기본값 (__main__ 블록에서 CLI 인자로 덮어씀)
CRAWL_START_TIME = datetime.now()
INCLUDE_IMAGES = True # 이미지 크롤링 포함 여부

# 브라우저 UI 설정
WINDOW_X = 5000           # 화면 가로 위치 (모니터 왼쪽 기준 px)
WINDOW_Y = 200         # 화면 세로 위치 (모니터 위쪽 기준 px)
WINDOW_WIDTH = 900     # 브라우저 너비
WINDOW_HEIGHT = 500    # 브라우저 높이

# --- 헬퍼 함수 ---


# 로컬 clean_text 제거 (utils.common 사용)



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

class LinkedinScraper:
    def __init__(self):
        self.posts = [] # collected data
        self.new_posts_count = 0
        self.stopped_early = False
        self.collected_codes = set()
        
        # 기존 데이터 로드 (증분 업데이트용)
        self.existing_codes = set()
        self.existing_posts_map = {}
        self.max_sequence_id = 0
        
        # 전체 파일 경로 (가장 최근 날짜 파일 찾기)
        self.full_file_path = self.get_latest_full_file()
        
        self.stop_codes = []
            
        if self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            full_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj
            
            # 기준 게시물 (최신 5개) 추출 for Stop Condition
            if CRAWL_MODE == "update only":
                self.stop_codes = [p.get("platform_id") or p.get("code") for p in full_posts[:5] if (p.get("platform_id") or p.get("code"))]

            for p in full_posts:
                pid = p.get("platform_id") or p.get("code")
                if pid:
                    self.existing_codes.add(pid)
                    self.existing_posts_map[pid] = p
            
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

        included = json_data.get("included", [])
        # 참조 해결을 위한 URN 맵 생성
        self.urn_map = {item.get("entityUrn"): item for item in included if item.get("entityUrn")}

        for item in included:
            if item.get("$type") == "com.linkedin.voyager.dash.search.EntityResultViewModel":
                self.extract_post_from_view_model(item)

    # 게시물 미디어 URL 패턴 화이트리스트
    MEDIA_PATTERNS = [
        "feedshare-shrink_",               # 일반 이미지 게시글
        "image-shrink_",                    # 뉴스레터/기사 이미지
        "feedshare-document-cover-images_", # 슬라이드/PDF 커버
        "feedshare-document-images_",       # 슬라이드/PDF 이미지
        "videocover-",                      # 동영상 썸네일
    ]

    def _classify_content_type(self, images):
        """미디어 URL 패턴으로 콘텐츠 유형 분류"""
        if not images:
            return "text"
        for img in images:
            if "videocover-" in img:
                return "video"
            if "feedshare-document" in img:
                return "document"
        return "carousel" if len(images) > 1 else "image"

    def find_images_recursively(self, obj, found_urls=None):
        """객체 내에서 모든 이미지 URL을 재귀적으로 탐색"""
        if found_urls is None: found_urls = []
        if not obj or not isinstance(obj, (dict, list)): return found_urls

        if isinstance(obj, list):
            for item in obj: self.find_images_recursively(item, found_urls)
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
                self.find_images_recursively(v, found_urls)
        
        return list(set(found_urls))

    def extract_post_from_view_model(self, item):
        try:
            entity_urn = item.get("entityUrn", "")
            activity_id = extract_urn_id(entity_urn)
            
            if not activity_id or activity_id in self.collected_codes:
                return

            if activity_id in self.existing_codes:
                # 이미지가 없는 기존 데이터라면 업데이트를 위해 통과 (선택 사항)
                existing_post = self.existing_posts_map.get(activity_id, {})
                if existing_post.get("media"):
                    if CRAWL_MODE == "update only" and activity_id in self.stop_codes:
                        if not self.stopped_early: self.stopped_early = True
                    return

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

            # 3. 이미지 수집 (강화된 로직)
            images = []
            if INCLUDE_IMAGES:
                # 메인 아이템 내의 모든 이미지 경로 탐색
                images = self.find_images_recursively(item)
                
                # 추가로 entityEmbeddedObject 탐색
                embedded = item.get("entityEmbeddedObject")
                if embedded:
                    images.extend(self.find_images_recursively(embedded))
            
            # 화이트리스트 방식: 게시물 미디어 패턴만 수집
            final_images = []
            for img in set(images):
                if any(pattern in img for pattern in self.MEDIA_PATTERNS):
                    final_images.append(img)

            post_url = item.get("navigationUrl", "")
            time_text = item.get("secondarySubtitle", {}).get("text", "").replace(" • ", "").strip()

            post_data = reorder_post({
                "platform_id": activity_id,
                "sns_platform": "linkedin",
                "username": user_link.split("/in/")[-1].replace("/", "") if "/in/" in user_link else username,
                "display_name": username,
                "full_text": clean_text(text),
                "media": final_images,
                "url": post_url,
                "created_at": date_str,
                "date": date_str[:10] if date_str else None,
                "crawled_at": CRAWL_START_TIME.isoformat(timespec='milliseconds'),
                "source": "network",
                "local_images": [],
                "time_text": time_text,
                "profile_slogan": profile_slogan,
                "user_link": user_link,
                "content_type": self._classify_content_type(final_images),
                "sequence_id": 0
            })

            # 💡 [개선] 기존 메타데이터 보존 로직
            existing = self.existing_posts_map.get(activity_id)
            if existing:
                post_data['crawled_at'] = existing.get('crawled_at')
                post_data['sequence_id'] = existing.get('sequence_id')

            self.posts.append(post_data)
            self.collected_codes.add(activity_id)
            print(f"   ⚡ [Network] [{activity_id}] ({date_str}) {username}: {text[:20]}...")

        except Exception as e:
            # print(f"Error parsing item: {e}")
            pass

    def get_latest_full_file(self):
        if not os.path.exists(DATA_DIR):
            return None
        files = [f for f in os.listdir(DATA_DIR) if f.startswith("linkedin_py_full_") and f.endswith(".json")]
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
                # 1. 먼저 "결과 더보기" 버튼 찾기
                try:
                    show_more_btn = page.locator('button:has-text("결과 더보기"), button:has-text("Show more results")')
                    if show_more_btn.count() > 0:
                        show_more_btn.first.click()
                        print(f"   🔘 '결과 더보기' 버튼 클릭 (현재 {len(self.posts)}개)")
                        time.sleep(3)
                    else:
                        # 2. 버튼이 없으면 스크롤
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        print(f"   ⬇️ 스크롤 다운... (현재 {len(self.posts)}개)")
                        time.sleep(3)
                except Exception as e:
                    # 버튼 찾기 실패 시 기본 스크롤
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    print(f"   ⬇️ 스크롤 다운... (현재 {len(self.posts)}개)")
                    time.sleep(3)
                
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

        # 1. 시퀀스 ID 부여 (신규 게시물만)
        # crawled_at 기준 오름차순(과거->최신)으로 정렬하여 ID 순차 부여
        new_posts = sorted([p for p in self.posts if p.get("sequence_id", 0) == 0], key=lambda x: x['crawled_at'])
        for post in new_posts:
            self.max_sequence_id += 1
            post["sequence_id"] = self.max_sequence_id

        # 2. 업데이트 파일 저장 (타임스탬프 적용: YYYYMMDD_HHMMSS)
        timestamp = CRAWL_START_TIME.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(UPDATE_DIR, f"linkedin_python_update_{timestamp}.json")
        
        # 신규 수집된 것들만 저장 (index 부여)
        recent_collected_posts = [p for p in self.posts if p.get('crawled_at', '').startswith(CRAWL_START_TIME.isoformat()[:10])]
        final_indexed_posts = []
        for idx, post in enumerate(recent_collected_posts):
            final_indexed_posts.append({"index": idx + 1, **post})

        if final_indexed_posts:
            save_json(update_file, final_indexed_posts)
            print(f"💾 업데이트 데이터 저장 완료: {update_file} ({len(final_indexed_posts)}개)")
        
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

        if CRAWL_MODE == "all":
            # ALL 모드일 때는 기존 데이터를 무시하고 새로 수집한 것으로 대체 (개행 등 변경사항 반영)
            final_posts = self.posts
            duplicate_count = 0
            new_items = self.posts
        else:
            # UPDATE 모드일 때는 기존에 없는 것만 추가
            existing_codes = {p.get("platform_id") or p.get("code") for p in old_posts}
            new_items = [p for p in self.posts if (p.get("platform_id") or p.get("code")) not in existing_codes]
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

        full_file = os.path.join(DATA_DIR, f"linkedin_py_full_{date_str}.json")
        
        # 메타데이터 구조 (JS 버전 참고)
        legacy_count = len([p for p in final_posts if "crawled_at" not in p])
        verified_count = len(final_posts) - legacy_count

        full_data = {
            "metadata": {
                "version": "1.0",
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "max_sequence_id": self.max_sequence_id,
                "first_code": (final_posts[0].get("platform_id") or final_posts[0].get("code")) if final_posts else None,
                "last_code": (final_posts[-1].get("platform_id") or final_posts[-1].get("code")) if final_posts else None,
                "crawl_mode": CRAWL_MODE,
                "legacy_data_count": legacy_count,
                "verified_data_count": verified_count,
                "merge_history": merge_history
            },
            "posts": final_posts
        }
        
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 파일 저장 완료: {full_file} (총 {len(final_posts)}개)")
        
        # Markdown 자동 변환
        convert_json_to_md(full_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='LinkedIn 스크래퍼')
    parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
    args = parser.parse_args()
    CRAWL_MODE = "update only" if args.mode == "update" else "all"
    scraper = LinkedinScraper()
    scraper.run()