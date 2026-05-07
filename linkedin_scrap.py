from utils.common import load_json, save_json, clean_text, reorder_post, format_timestamp, parse_relative_time
import json
import sys
import time
import os
import glob
import re
import argparse
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from utils.json_to_md import convert_json_to_md
from utils.linkedin_parser import parse_linkedin_post, extract_urn_id
from utils.auth_paths import linkedin_storage
from utils.auth_status import exit_auth_required, is_orchestrated_run

# --- 설정 ---
TARGET_URL = "https://www.linkedin.com/my-items/saved-posts/"
LOGIN_URL = "https://www.linkedin.com/login"
AUTH_FILE = str(linkedin_storage())
DATA_DIR = "output_linkedin/python"
UPDATE_DIR = os.path.join(DATA_DIR, "update")
SAVED_POSTS_SELECTOR = ".entity-result__content-container"
AUTH_RESOLUTION_TIMEOUT_MS = 20000
AUTH_POLL_INTERVAL_MS = 500
LINKEDIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# 스크랩 설정
TARGET_LIMIT = 0       # 0 = 무제한
CONSECUTIVE_EXISTING_LIMIT = 20  # update 모드에서 기수집 글이 연속 N건이면 중단

# CLI 인자 파싱
CRAWL_MODE = "update only"  # 기본값 (__main__ 블록에서 CLI 인자로 덮어씀)
CRAWL_START_TIME = datetime.now()
INCLUDE_IMAGES = True # 이미지 크롤링 포함 여부

# 브라우저 UI 설정
WINDOW_X = 5000           # 화면 가로 위치 (모니터 왼쪽 기준 px)
WINDOW_Y = 200         # 화면 세로 위치 (모니터 위쪽 기준 px)
# viewport는 갱신기(scripts/auth_runtime/renew.py)와 sns_insight_update LinkedIn 수집기와
# 동일하게 1280x1000으로 정렬한다. 본 세션 PoC(v3/v4/v5)가 이 viewport로 saved-posts 통과를
# 확정했고, 갱신·수집 fingerprint 일관성을 유지하기 위함이다.
WINDOW_WIDTH = 1280    # 브라우저 너비
WINDOW_HEIGHT = 1000   # 브라우저 높이

# --- 헬퍼 함수 ---


# 로컬 clean_text 제거 (utils.common 사용)

def is_linkedin_auth_url(url):
    normalized = (url or "").lower()
    return any(
        marker in normalized
        for marker in (
            "linkedin.com/login",
            "linkedin.com/uas/login",
            "linkedin.com/signup",
            "authwall",
            "/checkpoint/",
            "/guest/",
        )
    )


def has_saved_posts_content(page):
    try:
        return page.locator(SAVED_POSTS_SELECTOR).count() > 0
    except Exception:
        return False


def wait_for_saved_posts_ready(page, timeout_ms=AUTH_RESOLUTION_TIMEOUT_MS):
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_url = page.url

    while time.monotonic() <= deadline:
        last_url = page.url
        if has_saved_posts_content(page):
            return True, last_url
        if "my-items/saved-posts" in last_url and not is_linkedin_auth_url(last_url):
            return True, last_url
        try:
            page.wait_for_timeout(AUTH_POLL_INTERVAL_MS)
        except Exception:
            time.sleep(AUTH_POLL_INTERVAL_MS / 1000)

    return False, last_url

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
        self.consecutive_existing_count = 0
        
        # 전체 파일 경로 (가장 최근 날짜 파일 찾기)
        self.full_file_path = self.get_latest_full_file()
            
        if self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            full_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj

            for p in full_posts:
                pid = p.get("platform_id") or p.get("code")
                if pid:
                    self.existing_codes.add(pid)
                    self.existing_posts_map[pid] = p
            
            if isinstance(full_data_obj, dict):
                self.max_sequence_id = full_data_obj.get("metadata", {}).get("max_sequence_id", 0)
            
            print(f"📊 기존 데이터 {len(self.existing_codes)}개 로드됨. 현재 max_sequence_id: {self.max_sequence_id}")
            if CRAWL_MODE == "update only":
                print(
                    f"🔄 UPDATE ONLY 모드: 기존 {len(self.existing_codes)}건과 대조, "
                    f"기수집 {CONSECUTIVE_EXISTING_LIMIT}건 연속 시 수집을 중단합니다."
                )

    def manage_login(self, page):
        """로그인 처리 및 세션 관리"""
        if os.path.exists(AUTH_FILE):
            print(f"📂 세션 파일 로드: {AUTH_FILE}")
            try:
                page.goto(TARGET_URL)
            except Exception as e:
                print(f"⚠️ 페이지 이동 중 에러 (무시): {e}")

            is_ready, current_url = wait_for_saved_posts_ready(page)
            if is_ready:
                print(f"✅ 세션 유효함 (URL: {current_url})")
                return

            if is_linkedin_auth_url(current_url):
                print("⚠️ 세션 만료됨. 다시 로그인 필요.")
            elif "about:blank" in current_url:
                print("⚠️ 페이지가 로드되지 않았습니다 (about:blank). 재시도 중...")
                page.goto(TARGET_URL)
                is_ready, current_url = wait_for_saved_posts_ready(page)
                if is_ready:
                    print(f"✅ 세션 유효함 (URL: {current_url})")
                    return
                if "about:blank" in page.url:
                     print("❌ 페이지 로드 실패.")
            else:
                print(f"⚠️ 저장된 게시물 페이지가 준비되지 않았습니다. (URL: {current_url})")

        if is_linkedin_auth_url(page.url) or "about:blank" in page.url:
            print("🚨 로그인이 필요하거나 페이지 로드에 실패했습니다! (수동 개입 필요)")
            print(f"   현재 URL: {page.url}")
            page.goto(LOGIN_URL)
            print("   로그인을 완료하고 '저장된 게시물' 목록이 보이면 엔터키를 눌러주세요.")
            if is_orchestrated_run():
                exit_auth_required(
                    "linkedin",
                    reason="login_required",
                    current_url=page.url,
                    auth_file=AUTH_FILE,
                )
            if not sys.stdin.isatty():
                print("❌ 비대화형 환경에서는 로그인을 완료할 수 없습니다. 대화형 터미널에서 실행하세요.")
                sys.exit(1)
            input(">>> 로그인 완료 후 Enter: ")
            
            page.context.storage_state(path=AUTH_FILE)
            print("💾 새 세션 저장됨.")
            
            if page.url != TARGET_URL:
                page.goto(TARGET_URL)
                wait_for_saved_posts_ready(page)

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
                
                try:
                    from utils.common import save_debug_snapshot
                    save_debug_snapshot(resp_json, "linkedin", "json")
                except Exception: pass

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

    def extract_post_from_view_model(self, item):
        try:
            if self.stopped_early:
                return

            entity_urn = item.get("entityUrn", "")
            activity_id = extract_urn_id(entity_urn)
            
            if not activity_id or activity_id in self.collected_codes:
                return

            if activity_id in self.existing_codes:
                if CRAWL_MODE == "update only":
                    self.consecutive_existing_count += 1
                    if self.consecutive_existing_count >= CONSECUTIVE_EXISTING_LIMIT:
                        self.stopped_early = True
                    return

                # 이미지가 없는 기존 데이터라면 업데이트를 위해 통과 (선택 사항)
                existing_post = self.existing_posts_map.get(activity_id, {})
                if existing_post.get("media"):
                    return

            post_data = parse_linkedin_post(item, INCLUDE_IMAGES, CRAWL_START_TIME)
            if not post_data:
                return

            # 💡 [개선] 기존 메타데이터 보존 로직
            existing = self.existing_posts_map.get(activity_id)
            if existing:
                post_data['crawled_at'] = existing.get('crawled_at')
                post_data['sequence_id'] = existing.get('sequence_id')

            self.posts.append(post_data)
            self.collected_codes.add(activity_id)
            self.consecutive_existing_count = 0
            print(f"   ⚡ [Network] [{activity_id}] ({post_data['date']}) {post_data['username']}: {post_data['full_text'][:20]}...")

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

            try:
                # viewport를 None으로 설정하면 브라우저 창 크기에 따라 자동으로 조절됨 (또는 고정값 사용 가능)
                # 여기서는 창 크기와 비례하도록 설정하거나 특정 해상도 고정
                context_options = {
                    "viewport": {"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT},
                    "user_agent": LINKEDIN_USER_AGENT,
                    "locale": "ko-KR",
                }
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
                        print(f"🛑 기수집 {CONSECUTIVE_EXISTING_LIMIT}건 연속 확인하여 수집을 종료합니다.")
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
            finally:
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
