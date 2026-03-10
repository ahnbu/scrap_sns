from playwright.sync_api import sync_playwright
import os
import time

def renew_twitter_session():
    # twitter_scrap.py와 동일한 경로 사용
    USER_DATA_DIR = os.path.join(os.getcwd(), "auth", "x_user_data")
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    
    print(f"🚀 [Twitter(X)] 세션 갱신을 시작합니다.")
    print(f"📂 경로: {USER_DATA_DIR}")
    print(f"⚠️  중요: 기존에 켜져 있는 모든 Chrome 브라우저 창을 닫고 실행해주세요.")
    
    with sync_playwright() as p:
        # docs/twitter_saved/login_issue.md의 권장 설정 적용
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                channel="chrome",  # [핵심] Chromium 대신 실제 Chrome 사용
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 800},
                user_agent=user_agent
            )
            
            page = context.pages[0]
            page.goto("https://x.com/i/flow/login")
            
            print("\n>>> 브라우저에서 직접 로그인을 진행하세요.")
            print(">>> 로그인이 완료되고 피드가 보이면, 여기서 'y'를 입력하세요.")
            
            while True:
                user_input = input("👉 로그인을 완료하셨나요? (y/n): ").lower()
                if user_input == 'y':
                    print("✅ 세션이 유지된 상태로 브라우저를 닫습니다.")
                    break
                elif user_input == 'n':
                    print("⚠️  취소되었습니다.")
                    break
            
            context.close()
        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            print("💡 만약 'Executable doesn't exist' 에러가 나면 Chrome이 설치되어 있는지 확인하거나 channel을 제거하고 시도하세요.")

if __name__ == "__main__":
    renew_twitter_session()
