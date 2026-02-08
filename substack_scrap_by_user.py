import json
import time
import os
import re
import argparse
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from utils.json_to_md import convert_json_to_md

# --- 설정 ---
BASE_DATA_DIR = "output_substack"

# CLI 인자 파싱
parser = argparse.ArgumentParser(description='Substack User Archive Scraper')
parser.add_argument('--user', required=True, help='Substack User ID (e.g., edwardhan99)')
parser.add_argument('--limit', type=int, default=0, help='Maximum number of posts to scrap (0 for unlimited)')
args = parser.parse_args()

USER_ID = args.user
TARGET_LIMIT = args.limit

# 경로 설정
USER_DATA_DIR = os.path.join(BASE_DATA_DIR, USER_ID)
UPDATE_DIR = os.path.join(USER_DATA_DIR, "update")
ARCHIVE_URL = f"https://{USER_ID}.substack.com/archive"

CRAWL_START_TIME = datetime.now()

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
    lines = text.split('\n')
    cleaned_lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    return "\n".join(cleaned_lines).strip()

def clean_html_to_clean_text(html_content):
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 1. UI 요소 및 기능성 태그 제거
    selectors = ".header-anchor-parent, .image-link-expand, .post-ufi, button, script, style, iframe"
    for ui in soup.select(selectors):
        ui.decompose()

    # 2. <p> 및 블록 요소 뒤에 개행 추가 및 태그 제거
    for block in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "li", "br"]):
        block.insert_after("\n")
        block.unwrap()

    # 3. 텍스트만 추출
    text = soup.get_text()

    # 4. 남은 모든 HTML 태그 패턴 강제 제거 (정규식)
    text = re.sub(r'<[^>]+>', '', text)

    # 5. 공백 및 개행 정리 (단락 구분용 \n\n 적용)
    lines = [line.strip() for line in text.split('\n')]
    cleaned_text = ""
    last_line_empty = False
    for line in lines:
        if line:
            cleaned_text += line + "\n\n"
            last_line_empty = False
        elif not last_line_empty:
            last_line_empty = True
            
    return cleaned_text.strip()

# --- 메인 클래스 ---
class SubstackScraper:
    def __init__(self):
        self.posts = []
        self.collected_urls = set()
        self.max_sequence_id = 0
        
        # 결과 요약용 카운터
        self.success_count = 0
        self.fail_count = 0
        
        # 기존 데이터 로드
        self.full_file_path = self.get_latest_full_file()
        self.existing_posts = []
        self.existing_urls = set()
        
        if self.full_file_path:
            full_data_obj = load_json(self.full_file_path)
            self.existing_posts = full_data_obj.get("posts", []) if isinstance(full_data_obj, dict) else full_data_obj
            for p in self.existing_posts:
                if "post_url" in p:
                    self.existing_urls.add(p["post_url"])
            print(f"📊 기존 데이터 {len(self.existing_urls)}개 로드됨.")

    def get_latest_full_file(self):
        if not os.path.exists(USER_DATA_DIR):
            return None
        files = [f for f in os.listdir(USER_DATA_DIR) if f.startswith(f"substack_{USER_ID}_full_") and f.endswith(".json")]
        if not files:
            return None
        files.sort(reverse=True)
        return os.path.join(USER_DATA_DIR, files[0])

    def scrap_article_detail(self, page, url):
        try:
            print(f"   🔍 상세 페이지 수집 중: {url}")
            page.goto(url, wait_until="networkidle")
            time.sleep(2)
            
            # 본문 추출
            article = page.locator("article.post")
            if article.count() == 0:
                print(f"   ⚠️ 게시글 요소를 찾을 수 없음: {url}")
                return None

            title = article.locator("h1.post-title").inner_text() if article.locator("h1.post-title").count() > 0 else ""
            subtitle = article.locator("h3.subtitle").inner_text() if article.locator("h3.subtitle").count() > 0 else ""
            
            body_elem = article.locator(".body.markup")
            body_html = body_elem.inner_html() if body_elem.count() > 0 else ""
            
            # 작성일 추출 (datetime 속성 우선)
            time_elem = article.locator("time")
            created_at = time_elem.get_attribute("datetime") if time_elem.count() > 0 else ""
            
            # 고유 코드 생성 (URL 슬러그)
            code = url.split("/p/")[-1].split("?")[0] if "/p/" in url else url

            return {
                "code": code,
                "title": clean_text(title),
                "subtitle": clean_text(subtitle),
                "post_url": url,
                "created_at": created_at,
                "body_text": clean_html_to_clean_text(body_html),
                "crawled_at": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"   ❌ 상세 페이지 수집 에러 ({url}): {e}")
            return None

    def run(self):
        print(f"🚀 Substack 스크래퍼 시작: {USER_ID}")
        print(f"🔗 Target: {ARCHIVE_URL}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            
            # 1. 아카이브 목록 로드
            page.goto(ARCHIVE_URL, wait_until="networkidle")
            print("📜 목록 스크롤 중...")
            
            last_height = page.evaluate("document.body.scrollHeight")
            while True:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                
                # 중간에 목록 개수 체크하여 limit 넘으면 중단 가능
                if TARGET_LIMIT > 0:
                    links = page.locator('div[role="article"] a[data-testid="post-preview-title"]')
                    if links.count() >= TARGET_LIMIT:
                        break

            # 2. URL 및 날짜 목록 추출
            articles = page.locator('div[role="article"]')
            all_data = []
            for i in range(articles.count()):
                art = articles.nth(i)
                link_elem = art.locator('a[data-testid="post-preview-title"]')
                time_elem = art.locator('time')
                
                href = link_elem.get_attribute("href")
                dt = time_elem.get_attribute("datetime")
                
                if href:
                    full_url = href if href.startswith("http") else f"https://{USER_ID}.substack.com{href}"
                    url_clean = full_url.split("?")[0]
                    all_data.append({
                        "url": url_clean,
                        "date": dt
                    })
            
            # URL 중복 제거 (순서 유지)
            seen_urls = set()
            unique_data = []
            for item in all_data:
                if item["url"] not in seen_urls:
                    unique_data.append(item)
                    seen_urls.add(item["url"])
            
            print(f"✅ 총 {len(unique_data)}개의 게시글 링크 발견")

            # 3. 상세 수집 (새로운 링크만)
            target_items = [item for item in unique_data if item["url"] not in self.existing_urls]
            if TARGET_LIMIT > 0:
                target_items = target_items[:TARGET_LIMIT]
            
            print(f"🆕 수집 대상: {len(target_items)}개")

            for item in target_items:
                url = item["url"]
                detail = self.scrap_article_detail(page, url)
                if detail:
                    # 상세 페이지에서 날짜 추출 실패 시 목록 페이지의 날짜 사용
                    if not detail.get("created_at") and item["date"]:
                        detail["created_at"] = item["date"]
                    
                    self.posts.append(detail)
                    self.success_count += 1
                else:
                    self.fail_count += 1
                
                # 개별 수집 사이 간격
                time.sleep(1)

            self.save_results()
            browser.close()

        print(f"\n✨ 작업 완료! 성공: {self.success_count}, 실패: {self.fail_count}")

    def save_results(self):
        if not self.posts:
            print("ℹ️ 새로 수집된 데이터가 없습니다.")
            return

        # 업데이트 파일 저장
        timestamp = CRAWL_START_TIME.strftime("%Y%m%d_%H%M%S")
        update_file = os.path.join(UPDATE_DIR, f"substack_{USER_ID}_update_{timestamp}.json")
        save_json(update_file, self.posts)
        print(f"💾 업데이트 저장: {update_file} ({len(self.posts)}개)")
        
        # 전체 데이터 병합 및 재정렬
        self.update_full_version()

    def update_full_version(self):
        # 1. 중복 제거 및 병합
        combined_map = {p["post_url"]: p for p in self.existing_posts}
        for p in self.posts:
            combined_map[p["post_url"]] = p
        
        final_posts = list(combined_map.values())

        # 2. 시간 순서 정렬 (created_at 기준)
        # created_at이 없는 경우 code 기준 정렬 시도
        final_posts.sort(key=lambda x: x.get("created_at") or x.get("code") or "")

        # 3. Sequence ID 재할당
        for i, post in enumerate(final_posts):
            post["sequence_id"] = i + 1
        
        # 4. 최종 저장용 내림차순(최신순)
        final_posts.sort(key=lambda x: x.get("created_at") or x.get("code") or "", reverse=True)

        full_file = os.path.join(USER_DATA_DIR, f"substack_{USER_ID}_full_{CRAWL_START_TIME.strftime('%Y%m%d')}.json")
        
        full_data = {
            "metadata": {
                "version": "1.1", # HTML 정제 로직 반영
                "user_id": USER_ID,
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(final_posts),
                "limit": TARGET_LIMIT
            },
            "posts": final_posts
        }
        save_json(full_file, full_data)
        print(f"💾 전체 데이터 저장: {full_file} (총 {len(final_posts)}개)")
        
        # Markdown 자동 변환
        convert_json_to_md(full_file)

if __name__ == "__main__":
    scraper = SubstackScraper()
    scraper.run()
