import json
import os
from playwright.sync_api import sync_playwright
import time

# 로그 파일 경로
LOG_FILE = "linkedin_network_log.txt"
AUTH_FILE = "auth_linkedin.json"

def run():
    print("🕵️ 링크드인 네트워크 트래픽 진단 도구 시작...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        
        # 이전 세션이 있으면 로드
        if os.path.exists(AUTH_FILE):
             context = browser.new_context(storage_state=AUTH_FILE, viewport={"width": 1280, "height": 1000})
             print(f"📂 기존 세션 로드: {AUTH_FILE}")
        
        page = context.new_page()

        # 로그 파일 초기화
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write("=== LinkedIn Network Log ===\n")

        # 네트워크 핸들러 정의
        def handle_response(response):
            try:
                # 관련성 높은 키워드 필터링
                url = response.url
                if "voyager" in url or "graphql" in url or "api" in url:
                    if response.status == 200 and response.request.resource_type in ["xhr", "fetch"]:
                        try:
                            json_data = response.json()
                            # 파일에 기록
                            with open(LOG_FILE, "a", encoding="utf-8") as f:
                                f.write(f"\n[URL]: {url}\n")
                                f.write(f"[TYPE]: {response.request.resource_type}\n")
                                # 내용이 너무 길면 자름
                                str_data = json.dumps(json_data, ensure_ascii=False)
                                if len(str_data) > 1000:
                                    f.write(f"[BODY]: {str_data[:1000]}... (truncated)\n")
                                else:
                                    f.write(f"[BODY]: {str_data}\n")
                                f.write("-" * 50 + "\n")
                            
                            print(f"✅ 데이터 포착: {url[:60]}...")
                        except:
                            pass # JSON이 아닌 경우 무시
            except Exception as e:
                pass

        page.on("response", handle_response)

        # 페이지 이동
        print("🌐 링크드인 '저장된 게시물' 페이지로 이동 중...")
        page.goto("https://www.linkedin.com/my-items/saved-posts/")
        
        # 로그인 확인
        if "login" in page.url or "signup" in page.url:
            print("\n🛑 로그인이 필요합니다! 브라우저에서 직접 로그인해주세요.")
            print("   로그인이 완료되고 '저장된 게시물' 목록이 보이면 엔터키를 눌러주세요.")
            input(">>> 로그인 완료 후 Enter: ")
            
            # 세션 저장
            context.storage_state(path=AUTH_FILE)
            print("💾 세션 저장됨.")
            
            # 다시 이동 (혹시 리다이렉트 안됐을 경우)
            if "my-items" not in page.url:
                page.goto("https://www.linkedin.com/my-items/saved-posts/")

        print("\n📜 스크롤을 3회 수행하여 추가 데이터를 로드합니다...")
        for i in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
        
        print(f"\n✅ 진단 완료! 로그 파일: {LOG_FILE}")
        print("   브라우저를 닫습니다.")
        browser.close()

if __name__ == "__main__":
    run()
