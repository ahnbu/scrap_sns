from utils.common import load_json, save_json, clean_text, reorder_post, format_timestamp, parse_relative_time
import json
import time
import re
import os
import glob
import argparse
import sys
import io
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs, urlencode, quote
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
from utils.auth_paths import x_user_data
from utils.auth_status import exit_auth_required, is_orchestrated_run
from utils.x_time import format_kst, parse_api_date, parse_iso_date, warn_on_snowflake_drift

# 환경 변수 로드
load_dotenv('.env.local')

def configure_stdout():
    if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ===========================
# ⚙️ 설정
# ===========================
WINDOW_X = 5000           # 화면 밖으로 보내서 사용자 방해 최소화
WINDOW_Y = 0
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 600

OUTPUT_DIR = "output_twitter/python"
OUTPUT_FILE_PATTERN = "twitter_py_simple_{date}.json"

# ✨ 테스트용 제한 개수 (0: 무제한)
TARGET_LIMIT = 0 

# 커서 페이지네이션 설정
# /i/bookmarks 가 /i/history 로 리다이렉트된 뒤로 스크롤은 북마크 목록을 굴리지 못한다.
# 페이지가 보낸 Bookmarks 요청을 잡아 cursor 만 바꿔 재발행하는 방식으로 대체한다.
MAX_BOOKMARK_PAGES = 120      # 무한 루프 최종 방어 (1페이지 20건 기준 2,400건)
BOOKMARK_PAGE_DELAY = 1.5     # 커서 재발행 간 지연(초)
RATE_LIMIT_FLOOR = 20         # 잔여 호출이 이 아래면 진행분을 보존하고 중단
REPLAY_HEADER_KEYS = {
    'authorization',
    'x-csrf-token',
    'content-type',
    'x-twitter-active-user',
    'x-twitter-auth-type',
    'x-twitter-client-language',
}

# 로컬 clean_text 제거 (utils.common 사용)



TRANSIENT_X_BROWSER_ERRORS = (
    "Browser window not found",
    "Target page, context or browser has been closed",
)


def is_transient_x_browser_error(error: Exception) -> bool:
    message = str(error)
    return any(pattern in message for pattern in TRANSIENT_X_BROWSER_ERRORS)


def parse_twitter_date(date_str):
    """X API created_at → (KST 전체시각, KST 날짜).

    다른 플랫폼과 같은 KST 기준으로 맞춘다 — 근거는 utils/x_time.py 모듈 주석.
    """
    dt = parse_api_date(date_str)
    if dt is None:
        return None, None
    return format_kst(dt)


def classify_x_auth_state(
    *,
    current_url: str,
    has_tweet_article: bool,
    bookmark_response_seen: bool,
    parsed_bookmark_count: int,
) -> tuple[bool, str]:
    url = (current_url or "").lower()
    if "login" in url or "signup" in url or "challenge" in url:
        return False, "login_required"
    if parsed_bookmark_count > 0:
        return True, "bookmark_response"
    if bookmark_response_seen or has_tweet_article:
        return True, "bookmarks_loaded"
    return False, "no_bookmark_signal"


def should_require_x_auth(
    *,
    current_url: str,
    has_tweet_article: bool,
    bookmark_response_seen: bool,
    parsed_bookmark_count: int,
) -> bool:
    _ready, reason = classify_x_auth_state(
        current_url=current_url,
        has_tweet_article=has_tweet_article,
        bookmark_response_seen=bookmark_response_seen,
        parsed_bookmark_count=parsed_bookmark_count,
    )
    return reason == "login_required"


def launch_x_producer_context(playwright, user_data_dir: str, headless: bool = True):
    """X 수집용 브라우저 컨텍스트.

    headless 기본값은 True다 - 대량 재수집 중 창이 뜨면 사용자 포커스를 빼앗는다.
    수동 로그인이 필요할 때만 --no-headless로 창을 띄운다.
    """
    last_error = None
    for attempt in range(3):
        try:
            return playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="chrome",
                headless=headless,
                args=[
                    f"--window-position={WINDOW_X},{WINDOW_Y}",
                    "--disable-blink-features=AutomationControlled",
                ],
                viewport={"width": WINDOW_WIDTH, "height": WINDOW_HEIGHT},
            )
        except Exception as error:
            last_error = error
            if not is_transient_x_browser_error(error) or attempt == 2:
                raise
            time.sleep(1)
    raise last_error

def get_user_info(tweet_results):
    user_res = tweet_results.get('core', {}).get('user_results', {}).get('result', {})
    if not user_res:
        user_res = tweet_results.get('tweet', {}).get('core', {}).get('user_results', {}).get('result', {})
    
    username = None
    display_name = "Unknown"

    if user_res:
        u_core = user_res.get('core', {})
        username = u_core.get('screen_name')
        display_name = u_core.get('name')
        if not username:
            u_legacy = user_res.get('legacy', {})
            username = u_legacy.get('screen_name')
            display_name = u_legacy.get('name')
            
    return username, display_name

def extract_bottom_cursor(json_data):
    """Bookmarks 응답에서 다음 페이지 커서(Bottom)를 꺼낸다. 없으면 None."""
    try:
        timeline = json_data.get('data', {}).get('bookmark_timeline_v2', {}).get('timeline', {})
        for inst in timeline.get('instructions', []):
            for entry in inst.get('entries', []) or []:
                content = entry.get('content', {}) or {}
                if content.get('cursorType') == 'Bottom':
                    return content.get('value')
    except Exception:
        pass
    return None


def extract_from_json(json_data):
    posts = []
    try:
        instructions = json_data.get('data', {}).get('bookmark_timeline_v2', {}).get('timeline', {}).get('instructions', [])
        entries = []
        for inst in instructions:
            if inst.get('type') == 'TimelineAddEntries':
                entries = inst.get('entries', [])
                break
        
        for entry in entries:
            content = entry.get('content', {})
            item_content = content.get('itemContent', {})
            if item_content.get('itemType') != 'TimelineTweet': continue
                
            tweet_results = item_content.get('tweet_results', {}).get('result', {})
            if not tweet_results: continue
            
            legacy = tweet_results.get('legacy', {})
            if not legacy and 'tweet' in tweet_results:
                legacy = tweet_results['tweet'].get('legacy', {})

            username, display_name = get_user_info(tweet_results)
            
            # 💡 [개선] 본문 추출 우선순위: NoteTweet(긴 트윗) > Legacy Full Text
            # NoteTweet 결과가 있으면 그걸 먼저 사용 (인용된 트윗의 본문이 아닌 현재 트윗의 본문임을 확인)
            body = ""
            note_tweet_res = tweet_results.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {})
            if note_tweet_res:
                body = note_tweet_res.get('text', "")
            
            if not body:
                body = legacy.get('full_text', "")
            
            # 💡 [추가] 인용 트윗 주소 제거 (Twitter API는 인용 트윗의 URL을 본문 끝에 붙임)
            # 수집 데이터의 순수성을 위해 마지막의 t.co 링크가 인용 링크라면 제거 고려 가능
            # 여기서는 일단 그대로 두되, 본문이 중복되는 원인이 인용 본문 오인식인지 확인용 로그 강화
            
            media = [f"https://wsrv.nl/?url={m.get('media_url_https')}" for m in (legacy.get('extended_entities', {}).get('media', []) or legacy.get('entities', {}).get('media', [])) if m.get('media_url_https')]
            ts_full, ts_short = parse_twitter_date(legacy.get('created_at'))
            post_id = tweet_results.get('rest_id')
            warn_on_snowflake_drift(parse_api_date(legacy.get('created_at')), post_id)

            views_obj = tweet_results.get('views') or legacy.get('views') or {}

            if post_id:
                posts.append(reorder_post({
                    "platform_id": post_id,
                    "username": username or "Unknown",
                    "display_name": display_name,
                    "full_text": body,
                    "media": media,
                    "created_at": ts_full,
                    "date": ts_short,
                    "like_count": legacy.get("favorite_count"),
                    "comment_count": legacy.get("reply_count"),
                    "share_count": legacy.get("retweet_count"),
                    "quote_count": legacy.get("quote_count"),
                    "bookmark_count": legacy.get("bookmark_count"),
                    "view_count": views_obj.get("count"),
                    "url": f"https://x.com/{username}/status/{post_id}" if username else f"https://x.com/i/status/{post_id}",
                    "sns_platform": "x",
                    "source": "network",
                    "is_detail_collected": False
                }))
    except Exception: pass
    return posts

def extract_from_html(html_content, source_label="initial_dom"):
    posts = []
    if not BeautifulSoup: return posts
    soup = BeautifulSoup(html_content, 'html.parser')
    articles = soup.find_all('article', {'data-testid': 'tweet'})
    
    for article in articles:
        try:
            time_tag = article.find('time')
            if not time_tag: continue
            link_tag = time_tag.find_parent('a')
            if not link_tag: continue
            match = re.search(r'/([^/]+)/status/(\d+)', link_tag.get('href', ''))
            if not match: continue
            
            username, post_id = match.group(1), match.group(2)
            
            # 💡 [개선] 인용 트윗 본문을 제외하고 메인 본문만 추출
            # data-testid="tweetText" 중 인용 컨테이너(quoted_status 등) 내부에 있지 않은 것 탐색
            all_text_divs = article.find_all('div', {'data-testid': 'tweetText'})
            body = ""
            for t_div in all_text_divs:
                # 부모 중에 인용 트윗임을 나타내는 요소가 있는지 확인
                is_quoted = False
                parent = t_div.parent
                while parent and parent.name != 'article':
                    # Twitter의 인용 트윗 컨테이너 특징 (테두리가 있는 div 등)
                    if parent.get('role') == 'link' or (parent.name == 'div' and 'border' in parent.get('class', [])):
                        # 인용 트윗 내부의 본문임
                        is_quoted = True
                        break
                    parent = parent.parent
                
                if not is_quoted:
                    body = t_div.get_text('\n')
                    break
            
            # 위 로직으로 못 찾은 경우 첫 번째 것 시도 (폴백)
            if not body and all_text_divs:
                body = all_text_divs[0].get_text('\n')
            
            dt_str = time_tag.get('datetime')
            ts_full, ts_short = (None, None)
            dt = parse_iso_date(dt_str)
            if dt:
                ts_full, ts_short = format_kst(dt)
                warn_on_snowflake_drift(dt, post_id)
            
            name_div = article.find('div', {'data-testid': 'User-Name'})
            display_name = name_div.find('span').get_text() if name_div and name_div.find('span') else ""

            posts.append(reorder_post({
                "platform_id": post_id,
                "username": username,
                "display_name": display_name,
                "full_text": body,
                "media": [f"https://wsrv.nl/?url={img.get('src')}" for img in article.find_all('img') if 'media' in img.get('src', '')],
                "created_at": ts_full,
                "date": ts_short,
                "url": f"https://x.com/{username}/status/{post_id}",
                "sns_platform": "x",
                "source": source_label,
                "is_detail_collected": False
            }))
        except Exception: pass
    return posts

def main(args):
    start_time = datetime.now()
    all_posts_map = {}
    stop_ids = set()
    initial_count = 0
    new_count = 0
    max_sequence_id = 0

    print(f"🚀 X(Twitter) 목록 수집기 시작 (Mode: {args.mode})", flush=True)

    # 1. 기존 데이터 로드
    full_files = glob.glob(os.path.join(OUTPUT_DIR, "twitter_py_simple_*.json"))
    if full_files:
        latest_full = sorted(full_files, reverse=True)[0]
        with open(latest_full, 'r', encoding='utf-8-sig') as f:
            try:
                data = json.load(f)
                old_posts = data.get('posts', [])
                metadata = data.get('metadata', {})
                max_sequence_id = metadata.get('max_sequence_id', 0)
                
                # 메타데이터에 없으면 수동 계산 (레거시 지원)
                if max_sequence_id == 0 and old_posts:
                    max_sequence_id = max((p.get('sequence_id', 0) for p in old_posts), default=0)

                for p in old_posts:
                    # 💡 [보정] crawled_at이 없는 레거시 데이터 보정
                    if not p.get('crawled_at'):
                        p['crawled_at'] = p.get('created_at') or datetime.now().isoformat()
                    
                    pid = p.get('platform_id') or p.get('id')
                    stop_ids.add(pid)
                    all_posts_map[pid] = p
                
                # 중단점은 최신 20개로 제한 유지
                stop_ids = set(list(all_posts_map.keys())[:20])
                
                initial_count = len(old_posts)
                print(f"📡 기존 데이터 {initial_count}개 로드됨. (max_sequence_id: {max_sequence_id}, 중단점: {len(stop_ids)}개 설정)", flush=True)
            except Exception: pass

    USER_DATA_DIR = str(x_user_data())
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    with sync_playwright() as p:
        context = launch_x_producer_context(
            p, USER_DATA_DIR, headless=getattr(args, "headless", True)
        )
        page = context.pages[0]

        bookmark_response_seen = False
        parsed_bookmark_count = 0

        seen_this_run = set()
        last_bottom_cursor = {"value": None}
        captured_request = {}

        def ingest_bookmark_payload(payload):
            """Bookmarks 응답 본문 1건을 수집 맵에 반영하고 파싱된 platform_id 목록을 돌려준다."""
            nonlocal new_count, parsed_bookmark_count
            cursor = extract_bottom_cursor(payload)
            if cursor:
                last_bottom_cursor["value"] = cursor
            try:
                new_posts = extract_from_json(payload)
            except Exception:
                return []

            parsed_bookmark_count += len(new_posts)
            page_ids = []
            for post in new_posts:
                pid = post['platform_id']
                page_ids.append(pid)
                seen_this_run.add(pid)
                # 💡 [개선] 기존 수집 상태 및 메타데이터 보존
                existing = all_posts_map.get(pid)
                was_collected = existing.get('is_detail_collected', False) if existing else False

                has_new_metrics = existing is not None and existing.get('like_count') is None and post.get('like_count') is not None
                if pid not in all_posts_map or len(post['full_text']) > len(all_posts_map[pid].get('full_text', '')) or has_new_metrics:
                    if pid not in all_posts_map:
                        new_count += 1
                        post['crawled_at'] = datetime.now().isoformat(timespec='milliseconds')
                    else:
                        # 기존 메타데이터 보존
                        post['crawled_at'] = existing.get('crawled_at')
                        post['sequence_id'] = existing.get('sequence_id')

                    all_posts_map[pid] = post
                    all_posts_map[pid]['is_detail_collected'] = was_collected

                    if not was_collected:
                        msg = clean_text(post['full_text'])[:30]
                        print(f"   + [Net] @{post['username']} | {msg}... ({len(all_posts_map)}개)", flush=True)
            return page_ids

        def handle_response(response):
            nonlocal bookmark_response_seen
            if "Bookmarks?variables=" not in response.url:
                return
            bookmark_response_seen = True
            if response.status != 200:
                return
            try:
                payload = response.json()
            except Exception:
                return
            ingest_bookmark_payload(payload)

        def handle_request(request):
            """첫 Bookmarks 요청의 URL·헤더를 잡아둔다. 커서 재발행에 그대로 쓴다."""
            if "Bookmarks?variables=" in request.url and "url" not in captured_request:
                captured_request["url"] = request.url
                captured_request["headers"] = dict(request.headers)

        def goto_bookmarks_and_wait(page) -> None:
            """북마크 페이지로 이동하며 첫 Bookmarks 응답을 결정적으로 기다린다.

            expect_response 는 컨텍스트매니저라 응답을 유발하는 goto 자체를 감싸야 한다.
            goto 가 끝난 뒤 대기를 시작하면 응답이 이미 도착해 매번 타임아웃으로 떨어진다
            (동기 API 에는 wait_for_response 가 없어 기존 코드는 항상 5초 blind wait 였다).
            """
            try:
                with page.expect_response(
                    lambda item: "Bookmarks?variables=" in item.url,
                    timeout=10000,
                ) as response_info:
                    page.goto("https://x.com/i/bookmarks", wait_until="domcontentloaded")
                handle_response(response_info.value)
            except Exception:
                page.wait_for_timeout(5000)

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("\n🔍 [1단계] 북마크 페이지 접속 중...", flush=True)
        goto_bookmarks_and_wait(page)

        has_tweet_article = page.query_selector('article[data-testid="tweet"]') is not None
        _is_ready, auth_reason = classify_x_auth_state(
            current_url=page.url,
            has_tweet_article=has_tweet_article,
            bookmark_response_seen=bookmark_response_seen,
            parsed_bookmark_count=parsed_bookmark_count,
        )
        if auth_reason == "login_required":
            print("💡 로그인이 필요합니다. 브라우저에서 진행해주세요...", flush=True)
            if is_orchestrated_run():
                context.close()
                exit_auth_required(
                    "x",
                    reason="login_required",
                    current_url=page.url,
                    auth_file=USER_DATA_DIR,
                )
            page.wait_for_selector('article[data-testid="tweet"]', timeout=0)
        elif auth_reason == "no_bookmark_signal":
            print(
                "⚠️ X 북마크 로딩 신호를 아직 확인하지 못했습니다. 인증 만료로 처리하지 않고 수집을 계속합니다.",
                flush=True,
            )

        print("")
        print("[2단계] 커서 페이지네이션 수집 시작", flush=True)
        api_pages = 0
        stop_reason = "not_started"
        cursor = last_bottom_cursor.get("value")

        if not captured_request.get("url"):
            stop_reason = "request_not_captured"
            print("   Bookmarks 요청을 캡처하지 못했습니다. 페이지네이션을 건너뜁니다.", flush=True)
        elif not cursor:
            stop_reason = "cursor_absent"
            print("   첫 응답에 다음 페이지 커서가 없습니다. 1페이지로 종료합니다.", flush=True)
        else:
            parsed_request = urlparse(captured_request["url"])
            query_params = parse_qs(parsed_request.query)
            base_url = f"{parsed_request.scheme}://{parsed_request.netloc}{parsed_request.path}"
            replay_headers = {
                key: value
                for key, value in captured_request["headers"].items()
                if key.lower() in REPLAY_HEADER_KEYS
            }

            for page_no in range(1, MAX_BOOKMARK_PAGES + 1):
                variables = json.loads(query_params["variables"][0])
                variables["cursor"] = cursor
                replay_query = {"variables": json.dumps(variables, separators=(",", ":"))}
                for key in ("features", "fieldToggles"):
                    if key in query_params:
                        replay_query[key] = query_params[key][0]
                request_url = base_url + "?" + urlencode(replay_query, quote_via=quote)

                time.sleep(BOOKMARK_PAGE_DELAY)
                try:
                    result = page.evaluate(
                        """async ([url, headers]) => {
                            const res = await fetch(url, { headers, credentials: 'include' });
                            return {
                                status: res.status,
                                rateRemaining: res.headers.get('x-rate-limit-remaining'),
                                body: await res.text(),
                            };
                        }""",
                        [request_url, replay_headers],
                    )
                except Exception as error:
                    stop_reason = "fetch_failed"
                    print(f"   요청 실패로 중단합니다: {error}", flush=True)
                    break

                if result.get("status") != 200:
                    stop_reason = f"http_{result.get('status')}"
                    print(f"   HTTP {result.get('status')} 응답으로 중단합니다. 진행분은 보존됩니다.", flush=True)
                    break

                try:
                    payload = json.loads(result.get("body") or "")
                except Exception:
                    stop_reason = "invalid_json"
                    print("   응답 본문을 해석하지 못해 중단합니다. 진행분은 보존됩니다.", flush=True)
                    break

                before_seen = len(seen_this_run)
                page_ids = ingest_bookmark_payload(payload)
                fresh_in_run = len(seen_this_run) - before_seen
                api_pages += 1
                rate_remaining = result.get("rateRemaining")
                print(
                    f"   {page_no}페이지: {len(page_ids)}건 수신 (누계 {len(seen_this_run)}건, 잔여호출 {rate_remaining})",
                    flush=True,
                )

                next_cursor = last_bottom_cursor.get("value")
                if not page_ids:
                    stop_reason = "empty_entries"
                    break
                if fresh_in_run == 0:
                    stop_reason = "no_fresh_in_run"
                    break
                if not next_cursor:
                    stop_reason = "cursor_absent"
                    break
                if next_cursor == cursor:
                    stop_reason = "cursor_repeat"
                    break
                if TARGET_LIMIT > 0 and len(all_posts_map) >= TARGET_LIMIT:
                    stop_reason = "target_limit"
                    break
                if rate_remaining is not None and str(rate_remaining).isdigit() and int(rate_remaining) < RATE_LIMIT_FLOOR:
                    stop_reason = "rate_limit_floor"
                    print(f"   잔여 호출 {rate_remaining}회로 중단합니다. 진행분은 보존됩니다.", flush=True)
                    break

                cursor = next_cursor
            else:
                stop_reason = "max_pages"

        # API 경로가 한 장도 못 가져온 경우에만 DOM 을 보조로 쓴다.
        # 리다이렉트된 /i/history 화면의 article 은 북마크가 아닐 수 있어 상시 사용하지 않는다.
        if api_pages == 0:
            print("   API 수집분이 없어 DOM 스캔으로 보조 수집합니다.", flush=True)
            for post in extract_from_html(page.content(), "initial_dom"):
                pid = post['platform_id']
                if args.mode == 'update' and pid in stop_ids:
                    break
                if pid not in all_posts_map:
                    post['crawled_at'] = datetime.now().isoformat(timespec='milliseconds')
                    post['is_detail_collected'] = False
                    all_posts_map[pid] = post
                    new_count += 1

        print("")
        print(
            f"수집 종료 (사유: {stop_reason}, API {api_pages}페이지, 누계 {len(all_posts_map)}건)",
            flush=True,
        )


        # 결과 저장
        # 💡 [개선] 신규 게시물에 sequence_id 부여
        # crawled_at 기준 오름차순(과거->최신)으로 정렬하여 ID 순차 부여
        new_posts_to_id = [p for p in all_posts_map.values() if p.get('sequence_id') is None]
        new_posts_to_id.sort(key=lambda x: x.get('crawled_at') or '')
        
        for p in new_posts_to_id:
            max_sequence_id += 1
            p['sequence_id'] = max_sequence_id

        # 💡 [추가] 본문 중복 체크 (Deduplication Check)
        text_map = {}
        duplicates_found = 0
        for p in all_posts_map.values():
            txt = p.get('full_text', '')
            if len(txt) > 20: # 짧은 텍스트는 제외
                if txt in text_map:
                    text_map[txt].append(p.get('platform_id'))
                    duplicates_found += 1
                else:
                    text_map[txt] = [p.get('platform_id')]
        
        if duplicates_found > 0:
            print(f"\n⚠️ 주의: 본문 내용이 완전히 동일한 항목이 {duplicates_found}개 발견되었습니다.")
            for txt, ids in text_map.items():
                if len(ids) > 1:
                    print(f"   - 중복 텍스트 ({len(ids)}회): {txt[:50]}... | IDs: {ids}")

        final_posts = sorted(all_posts_map.values(), key=lambda x: x.get('sequence_id', 0), reverse=True)
        if final_posts:
            today = datetime.now().strftime('%Y%m%d')
            full_file = os.path.join(OUTPUT_DIR, OUTPUT_FILE_PATTERN.format(date=today))
            os.makedirs(os.path.dirname(full_file), exist_ok=True)
            
            with open(full_file, 'w', encoding='utf-8-sig') as f:
                json.dump({
                    "metadata": {
                        "updated_at": datetime.now().isoformat(),
                        "total_count": len(final_posts),
                        "max_sequence_id": max_sequence_id,
                        "duplicates_found": duplicates_found,
                        "platform": "x"
                    },
                    "posts": final_posts
                }, f, ensure_ascii=False, indent=4)
            
            # 💡 [추가] Simple Update 파일 생성
            if new_count > 0:
                update_dir = os.path.join(OUTPUT_DIR, "update")
                os.makedirs(update_dir, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                update_file = os.path.join(update_dir, f"twitter_py_simple_update_{timestamp}.json")
                
                # 이번 수집에서 새로 추가된 것만 필터링 (is_detail_collected가 False인 최신 데이터들)
                new_items = [p for p in final_posts if not p.get('is_detail_collected')][:new_count]
                
                with open(update_file, 'w', encoding='utf-8-sig') as f:
                    json.dump(new_items, f, ensure_ascii=False, indent=4)
                print(f"📂 목록 업데이트 저장: {update_file} ({new_count}개)")

            end_time = datetime.now()
            duration = end_time - start_time
            
            # Threads 스타일 최종 요약 통계
            print("\n" + "="*40, flush=True)
            print(f"시작시간 : {start_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            print(f"종료시간 : {end_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            print(f"소요시간 : {str(duration).split('.')[0]}", flush=True)
            print("="*40, flush=True)
            print(f"📊 최종 수집 결과 요약", flush=True)
            print(f"기존 게시물 : {initial_count}개", flush=True)
            print(f"신규 추가 : {new_count}개", flush=True)
            print(f"전체 목록 : {len(final_posts)}개", flush=True)
            print(f"저장 경로 : {full_file}", flush=True)
            print("="*40, flush=True)

        context.close()

if __name__ == "__main__":
    configure_stdout()
    parser = argparse.ArgumentParser(description='X(Twitter) 목록 수집기 (Producer) - Refined')
    parser.add_argument('--mode', choices=['all', 'update'], default='update', help='크롤링 모드')
    parser.add_argument(
        '--headless',
        dest='headless',
        action=argparse.BooleanOptionalAction,
        default=True,
        help='브라우저 창 없이 실행 (기본값). 수동 로그인이 필요하면 --no-headless',
    )
    args = parser.parse_args()
    main(args)
