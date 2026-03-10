import sys
import os
import subprocess
import time
import requests
from playwright.sync_api import sync_playwright

def test_ui():
    port = 5002
    url = f"http://localhost:{port}"
    
    # 1. Start Flask server
    print(f"Starting Flask server on port {port}...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PORT"] = str(port)
    
    # We want to catch server logs if it fails
    server_process = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # Wait for server ready
    ready = False
    for i in range(15):
        try:
            resp = requests.get(f"{url}/api/status", timeout=2)
            if resp.status_code == 200:
                print(f"Server is up! Response: {resp.json()}")
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)
    
    if not ready:
        print("Server failed to respond to /api/status")
        server_process.terminate()
        return False

    success = False
    try:
        # 2. Playwright test
        with sync_playwright() as p:
            print("Launching browser...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            print(f"Navigating to {url}...")
            # Use 'domcontentloaded' to avoid waiting for slow fonts/icons
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            title = page.title()
            print(f"Page title: {title}")
            
            if "SNS Feed Viewer" in title:
                # Wait for totalPostsCount
                print("Checking for #totalPostsCount...")
                try:
                    page.wait_for_selector("#totalPostsCount", state="visible", timeout=10000)
                    count_text = page.inner_text("#totalPostsCount")
                    print(f"Count text found: {count_text}")
                    
                    # Wait for cards if any
                    print("Checking for cards...")
                    try:
                        page.wait_for_selector(".glass-card", state="visible", timeout=5000)
                        print("Glass card(s) detected! UI Load Success.")
                        success = True
                    except:
                        # If count is 0, no cards is OK
                        if any(char.isdigit() for char in count_text) and "0" in count_text:
                            print("No cards, but count is 0. UI structure is OK.")
                            success = True
                        else:
                            print("No cards found, but count suggests there should be.")
                            success = False
                except:
                    print("Could not find #totalPostsCount")
                    success = False
            else:
                print("Failed to load correctly (Title mismatch)")
                success = False
                
            browser.close()
    except Exception as e:
        print(f"Error during playwright: {e}")
    finally:
        print("Stopping server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except:
            server_process.kill()
        
    return success

if __name__ == "__main__":
    if test_ui():
        print("\nUI Test Result: PASSED ✅")
        sys.exit(0)
    else:
        print("\nUI Test Result: FAILED ❌")
        sys.exit(1)
