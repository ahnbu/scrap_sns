from playwright.sync_api import sync_playwright
import time
import os

def renew_session(sns_name, url, target_file):
    print(f"\n🚀 [{sns_name}] 세션 갱신을 시작합니다.")
    print(f"🔗 접속 URL: {url}")
    print(f"💡 브라우저 창에서 로그인을 완료한 후, 터미널(여기)로 돌아와 'y'를 입력해주세요.")
    
    with sync_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        browser = p.chromium.launch(headless=False)
        
        # 기존 세션 로드 시도
        context_args = {"user_agent": user_agent}
        if os.path.exists(target_file) and os.path.getsize(target_file) > 10:
            context_args["storage_state"] = target_file
            
        context = browser.new_context(**context_args)
        page = context.new_page()
        page.goto(url)
        
        # 사용자 확인 대기
        while True:
            user_input = input(f"👉 [{sns_name}] 로그인을 완료하셨나요? (y/n): ").lower()
            if user_input == 'y':
                context.storage_state(path=target_file)
                print(f"✅ [{sns_name}] 세션이 저장되었습니다: {target_file}")
                break
            elif user_input == 'n':
                print(f"⚠️ [{sns_name}] 세션을 저장하지 않고 건너뜁니다.")
                break
        
        browser.close()

# 순차적으로 실행 (사용자가 하나씩 처리 가능)
sessions = [
    ("LinkedIn", "https://www.linkedin.com/login", "auth/auth_linkedin.json"),
    ("Threads", "https://www.threads.net/login", "auth/auth_threads.json"),
    ("Twitter(X)", "https://x.com/i/flow/login", "auth/auth_twitter.json")
]

for sns, url, path in sessions:
    try:
        renew_session(sns, url, path)
    except Exception as e:
        print(f"❌ {sns} 처리 중 에러 발생: {e}")

print("\n✨ 모든 세션 갱신 프로세스가 종료되었습니다.")
