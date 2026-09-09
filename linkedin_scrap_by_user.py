import json
import shutil
import sys
import time
import os
import re
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from utils.auth_paths import linkedin_storage
from utils.auth_status import (
    AUTH_REQUIRED_EXIT_CODE,
    AuthRequiredError,
    is_orchestrated_run,
    raise_auth_required,
)
from utils.benchmark_store import atomic_save_json
from utils.json_to_md import convert_json_to_md

# 창 정책·엔진 플래그는 이 파일이 정하지 않는다. 스킬 공용 정본이 정한다.
# 설계 근거: _docs/20260908_02 (W2-4), 정본 설계: skills/_docs/20260831_01
SKILLS_ROOT = Path.home() / ".claude" / "skills"
if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))
# 🔴 정본을 못 찾으면 조용히 다른 정책으로 돌지 않는다. 조용한 정책 분기가
#    이 변경이 없애려는 문제 그 자체다 — 여기서 명확히 멈춘다.
from _shared.browser_launch import decide as decide_browser_policy  # noqa: E402

# --- 설정 ---
LOGIN_URL = "https://www.linkedin.com/login"
# 인증 정본은 사용자 config auth runtime 이다. repo-local `auth/` 를 하드코딩하지 않는다
# (utils/AGENTS.md 금지 조항). 저장글 수집기(linkedin_scrap.py)와 같은 함수를 쓴다.
AUTH_FILE = str(linkedin_storage())
AUTH_BACKUP_FILE = AUTH_FILE + ".bak"
# 로그인 세션 + 창 없음으로 계정 활동목록이 정상 수집됨을 실측한 결과다.
# 이 문자열이 `LAUNCH:` 줄의 reason= 칸에 실려 로그에 남는다.
HEADLESS_MEASURED_REASON = (
    "2026-09-08 실측: 로그인 세션 + headless 로 활동목록 13건·866KB 정상"
)
BASE_DATA_DIR = "output_linkedin_user"

# 🔴 여기서 argparse 를 실행하지 않는다. 모듈 최상단에서 parse_args() 를 부르면
#    다른 파일이 이 모듈을 import 하는 순간 그 파일의 명령줄 인자를 읽고 죽는다.
#    그래서 벤치마킹 러너가 계정마다 별도 프로세스를 띄울 수밖에 없었다(계정 5개 =
#    브라우저 5개). 인자 파싱은 main() 안으로 내렸고, 값은 생성자 인자로 넘어간다.
#    같은 수정 선례: CHANGELOG `fix(scraper): argparse 전역 실행 제거`
#    계획: _docs/20260909_01 (W6 T6-b, T6-c)

INCLUDE_IMAGES = True

# 브라우저 UI 설정.
# 🔴 창 위치(WINDOW_X/Y)는 여기서 정하지 않는다 — `_shared/browser_launch.decide()` 가
#    정한다. 아래 두 값은 페이지 렌더 크기(viewport)일 뿐 창 배치와 무관하다.
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
        with open(filepath, "r", encoding="utf-8-sig") as f:
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

# --- 브라우저 기동 ---
def launch_linkedin_browser(playwright, *, needs_human_login=False):
    """창을 띄울지·어디에 띄울지는 여기서 정하지 않는다. 공용 정본이 정한다.

    호출부가 여럿이라(단독 실행 · 벤치마킹 러너) 함수로 뺐다. 여기서 찍는
    `LAUNCH:` 한 줄이 로그에 남고, 그 줄 수가 곧 브라우저 기동 횟수다 -
    통합 효과(6회 → 2회)를 그 숫자로 잰다. 계획: _docs/20260909_01 (W6 T6-h, W6-1)
    """
    policy = decide_browser_policy(
        human_operates=needs_human_login,
        headless_reason=None if needs_human_login else HEADLESS_MEASURED_REASON,
    )
    print(policy.echo(), flush=True)
    return playwright.chromium.launch(
        headless=policy.headless,
        args=list(policy.args),
        ignore_default_args=list(policy.ignore_default_args),
    )


def new_linkedin_context(browser):
    """로그인 세션을 실은 컨텍스트를 연다. 계정이 여럿이어도 이것 하나를 공유한다."""
    context_options: dict = {
        "viewport": {"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT}
    }
    if os.path.exists(AUTH_FILE):
        context_options["storage_state"] = AUTH_FILE
    return browser.new_context(**context_options)


# --- 메인 클래스 ---
class LinkedinUserScraper:
    """계정 하나의 활동 목록을 긁는다.

    종전에는 모듈 전역 8개(사용자 id·대상 URL·수집 상한·기간·시작지점·데이터 폴더·
    업데이트 폴더·창 필요 여부)를 파일 전체 18곳에서 읽었다. 그래서 한 프로세스에서
    계정 둘을 돌릴 수 없었다 - 두 번째 계정이 첫 번째의 전역을 그대로 쓴다.
    전부 생성자 인자로 옮겨 인스턴스마다 독립시켰다.
    계획: _docs/20260909_01 (W6 T6-c)
    """

    def __init__(
        self,
        user_id,
        *,
        limit=0,
        duration=None,
        after=None,
        needs_human_login=False,
    ):
        self.user_id = user_id
        self.target_limit = limit or 0
        self.duration_str = duration
        self.after_str = after
        # 사람이 조작할 창이 필요한가. 공용 정본의 human_operates 로 넘어간다.
        self.needs_human_login = needs_human_login

        self.user_data_dir = os.path.join(BASE_DATA_DIR, user_id)
        self.update_dir = os.path.join(self.user_data_dir, "update")
        self.target_url = f"https://www.linkedin.com/in/{user_id}/recent-activity/all/"
        self.crawl_start_time = datetime.now()

        # 마이그레이션 실행
        migrate_old_data(self.user_id)

        self.posts = []
        self.collected_codes = set()
        self.social_counts = {}
        self.stopped_early = False
        self.max_sequence_id = 0
        
        # 결과 요약용 카운터
        self.success_count = 0
        self.fail_count = 0
        self.skip_count = 0
        self.duplicate_count = 0 # 기존 데이터 중복에 의한 스킵
        
        # 기간 제한 설정
        self.stop_duration = parse_duration(self.duration_str)
        self.stop_date = self.crawl_start_time - self.stop_duration if self.stop_duration else None
        
        # 시작 지점 설정 (after)
        self.after_duration = parse_duration(self.after_str)
        self.after_date = self.crawl_start_time - self.after_duration if self.after_duration else None
        
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
                page.goto(self.target_url)
                time.sleep(3)
            except Exception as e:
                print(f"⚠️ 페이지 이동 중 에러: {e}")
            
            if "login" in page.url or "signup" in page.url:
                print("⚠️ 세션 만료됨. 다시 로그인 필요.")
            else:
                return

        print(f"🚨 로그인이 필요합니다! URL: {page.url}")

        # 🔴 자동 실행에는 키보드 입력 통로가 없다. 아래 input() 은 사람을 기다리는 것이
        #    아니라 즉시 EOFError 로 죽으면서 오류 추적만 남긴다(2026-09-08 실측: 0.0초).
        #    total_scrap 이 부르는 경로는 여기서 인증 필요 신호로 끝낸다 —
        #    저장글 수집기(linkedin_scrap.py:257)가 이미 쓰는 방식과 같다.
        #    🔴 sys.exit 이 아니라 예외로 던진다. 벤치마킹 러너가 이 수집기를 한
        #       프로세스 안에서 계정마다 부르므로, 여기서 프로세스를 죽이면 앞선
        #       계정에서 모은 결과와 누적 저장이 통째로 날아간다. 종료코드 86 은
        #       러너가 잡아서 낸다(linkedin_scrap_benchmark.py).
        #       계획: _docs/20260909_01 (W6 T6-f)
        if is_orchestrated_run():
            raise_auth_required(
                "linkedin",
                reason="login_required",
                current_url=page.url,
                auth_file=AUTH_FILE,
            )

        page.goto(LOGIN_URL)
        input(">>> 로그인을 완료하고 엔터키를 눌러주세요: ")
        self._save_storage_state(page)
        page.goto(self.target_url)
        time.sleep(3)

    def _save_storage_state(self, page):
        """새 세션을 공용 인증 파일에 안전하게 쓴다.

        이 파일은 저장글 수집기도 함께 보는 **공용 자산**이고 레포 밖에 있어
        git 으로 되돌릴 수 없다. 그래서 세 겹으로 막는다.
          1. 받은 세션에 `li_at` 이 없으면 **기존 파일을 건드리지 않는다** (실질적 롤백)
          2. 덮어쓰기 전 `.bak` 사본을 남긴다
          3. 쓰기는 임시 파일 교체(원자적)로 한다 — 도중 실패해도 원본이 잘리지 않는다
        """
        state = page.context.storage_state()
        cookies = state.get("cookies") or []
        if not any(c.get("name") == "li_at" for c in cookies):
            print("❌ 받은 세션에 li_at 쿠키가 없다 — 기존 인증 파일을 그대로 둔다.")
            raise_auth_required(
                "linkedin",
                reason="invalid_session",
                current_url=page.url,
                auth_file=AUTH_FILE,
            )

        if os.path.exists(AUTH_FILE):
            try:
                shutil.copy2(AUTH_FILE, AUTH_BACKUP_FILE)
            except OSError as error:
                print(f"⚠️ 인증 백업 실패(진행은 계속한다): {error}")

        if not atomic_save_json(AUTH_FILE, state):
            print("❌ 인증 파일 저장 실패 — 기존 파일은 그대로다.")
            sys.exit(1)
        print("💾 새 세션 저장됨.")

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

        # 먼저 지표(SocialActivityCounts)를 전부 모은다 — 게시물 생성 시점에
        # self.social_counts가 채워져 있어야 병합할 수 있다(배열 내 순서 비보장).
        for item in included:
            item_type = item.get("$type")
            if item_type and item_type.endswith("SocialActivityCounts"):
                self.extract_social_activity_counts(item)

        for item in included:
            item_type = item.get("$type")
            if item_type == "com.linkedin.voyager.dash.search.EntityResultViewModel":
                self.extract_post_from_view_model(item)
            elif item_type and "feed.Update" in item_type:
                # 사용자의 활동 페이지에서는 feed.Update 타입일 가능성이 높음
                self.extract_post_from_feed_update(item)

    def extract_social_activity_counts(self, item):
        urn = item.get("urn", "")
        activity_id_match = re.search(r'activity:(\d+)', urn)
        activity_id = activity_id_match.group(1) if activity_id_match else None
        if not activity_id:
            return
        self.social_counts[activity_id] = {
            "like_count": item.get("numLikes"),
            "comment_count": item.get("numComments"),
            "share_count": item.get("numShares"),
        }

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

            if self.target_limit > 0 and len(self.posts) >= self.target_limit:
                print(f"   🛑 개수 제한 도달 ({self.target_limit}개) - 수집 중단 예정")
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
            counts = self.social_counts.get(activity_id, {})

            post_data = {
                "code": activity_id,
                "username": username,
                "created_at": post_date.strftime('%Y-%m-%d %H:%M:%S') if post_date else None,
                "time_text": time_text,
                "full_text": clean_text(text),
                "post_url": post_url,
                "profile_slogan": profile_slogan,
                "images": list(set(images)),
                "user_link": f"https://www.linkedin.com/in/{self.user_id}",
                "like_count": counts.get("like_count"),
                "comment_count": counts.get("comment_count"),
                "share_count": counts.get("share_count"),

                "crawled_at": self.crawl_start_time.isoformat(),
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
            if self.target_limit > 0 and len(self.posts) >= self.target_limit:
                print(f"   🛑 개수 제한 도달 ({self.target_limit}개) - 수집 중단 예정")
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
            counts = self.social_counts.get(activity_id, {})

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
                "like_count": counts.get("like_count"),
                "comment_count": counts.get("comment_count"),
                "share_count": counts.get("share_count"),
                "crawled_at": self.crawl_start_time.isoformat(),
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
        if not os.path.exists(self.user_data_dir):
            return None
        # 새 규칙 우선 검색
        files = [f for f in os.listdir(self.user_data_dir) if f.startswith(f"linkedin_{self.user_id}_full_") and f.endswith(".json")]
        if not files:
            return None
        files.sort(reverse=True)
        return os.path.join(self.user_data_dir, files[0])

    def run(self):
        """브라우저를 스스로 열고 수집한다. 단독 실행(CLI) 경로다."""
        with sync_playwright() as p:
            browser = launch_linkedin_browser(p, needs_human_login=self.needs_human_login)
            try:
                context = new_linkedin_context(browser)
                page = context.new_page()
                try:
                    self.run_with_page(page)
                finally:
                    page.close()
            finally:
                browser.close()

    def run_with_page(self, page):
        """이미 열린 page 로 수집한다.

        벤치마킹 러너가 브라우저 하나·컨텍스트 하나를 열고 계정마다 이 함수를
        부른다. page 를 계정 간에 재사용하지 않는 이유: 아래 `page.on("response", ...)`
        가 인스턴스에 묶여 있어, 같은 page 에 두 인스턴스가 붙으면 앞 계정의
        핸들러가 뒤 계정 응답까지 먹는다. 계획: _docs/20260909_01 (W6 T6-d·T6-e)
        """
        start_time_dt = datetime.now()
        print(f"🚀 링크드인 사용자 스크래퍼 시작: {self.user_id}")
        print(f"🔗 Target: {self.target_url}")

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
            
            if self.target_limit > 0 and len(self.posts) >= self.target_limit:
                break

        self.save_results()

        end_time_dt = datetime.now()
        duration = end_time_dt - start_time_dt
        
        # 결과 요약 출력
        print("\n" + "="*50)
        print(f"📊 스크래핑 결과 요약 ({self.user_id})")
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
        
        timestamp = self.crawl_start_time.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(self.update_dir, f"linkedin_{self.user_id}_update_{timestamp}.json")
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
                "user_id": self.user_id,
                "note": "Sorted by Snowflake ID (code)"
            })

        full_file = os.path.join(self.user_data_dir, f"linkedin_{self.user_id}_full_{self.crawl_start_time.strftime('%Y%m%d')}.json")
        
        full_data = {
            "metadata": {
                "version": "1.1", # 버전 업
                "user_id": self.user_id,
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "max_sequence_id": self.max_sequence_id,
                "limit": self.target_limit,
                "duration": self.duration_str,
                "merge_history": merge_history
            },
            "posts": final_posts
        }
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 저장 (정렬 완료): {full_file} (총 {len(final_posts)}개)")
        
        # Markdown 자동 변환
        convert_json_to_md(full_file)

def main(argv=None):
    """단독 실행 진입점.

    인자 파싱이 여기 있는 이유: 모듈 최상단에서 하면 이 파일을 import 하는 다른
    파일의 명령줄을 읽고 죽는다. 계획: _docs/20260909_01 (W6 T6-b)
    """
    parser = argparse.ArgumentParser(description='LinkedIn User Activity Scraper')
    parser.add_argument('--user', required=True, help='LinkedIn User ID (slug)')
    parser.add_argument('--limit', type=int, default=0, help='Maximum number of posts to scrap (0 for unlimited)')
    parser.add_argument('--duration', type=str, help='Scrap range (e.g., 3d, 1m, 1y). Default unit is day if only number is given.')
    parser.add_argument('--after', type=str, help='Skip posts newer than this duration (e.g., 1m). Useful for picking up where you left off.')
    parser.add_argument('--no-headless', dest='no_headless', action='store_true',
                        help='창을 띄운다. 세션이 만료돼 사람이 직접 로그인해야 할 때만 쓴다')
    args = parser.parse_args(argv)

    scraper = LinkedinUserScraper(
        args.user,
        limit=args.limit,
        duration=args.duration,
        after=args.after,
        needs_human_login=args.no_headless,
    )
    try:
        scraper.run()
    except AuthRequiredError:
        # 단독 실행에서는 종전과 같이 종료코드 86 으로 끝난다. 신호 줄은 이미
        # raise_auth_required() 가 찍었다. 계획: _docs/20260909_01 (W6 T6-f)
        return AUTH_REQUIRED_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())