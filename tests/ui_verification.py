import sys
import os
import subprocess
import time
import requests
from playwright.sync_api import sync_playwright

def test_ui():
    port = 5001
    url = f"http://localhost:{port}"
    
    # 1. Start Flask server in background
    print(f"Starting Flask server on port {port}...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PORT"] = str(port)
    
    server_process = subprocess.Popen(
        [sys.executable, "-u", "server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    # Wait for server to be ready
    ready = False
    server_output = []
    
    def check_server():
        try:
            resp = requests.get(f"{url}/api/status", timeout=2)
            if resp.status_code == 200:
                print(f"Server is up! Response: {resp.json()}")
                return True
        except:
            pass
        return False

    for i in range(15):
        if check_server():
            ready = True
            break
        # Read available output from server
        while True:
            # Non-blocking read would be better, but let's try this
            line = server_process.stdout.readline() if not server_process.poll() else None
            if line:
                server_output.append(line.strip())
                print(f"Server: {line.strip()}")
            else:
                break
        time.sleep(1)
    
    if not ready:
        print("Server failed to start or is not responding correctly.")
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
            response = page.goto(url)
            print(f"Page response status: {response.status if response else 'No Response'}")
            
            # Check Title
            title = page.title()
            print(f"Page title: {title}")
            
            # If title is 404, let's see the content
            if "404" in title:
                print(f"Body content: {page.inner_text('body')}")
            
            # Check if totalPostsCount is not "Loading..." after some time
            page.wait_for_selector("#totalPostsCount", timeout=10000)
            
            # Wait for data to load
            print("Waiting for data to load...")
            for i in range(10):
                count_text = page.inner_text("#totalPostsCount")
                if "Loading" not in count_text:
                    print(f"Posts count text: {count_text}")
                    break
                time.sleep(1)
            
            # Check for cards
            try:
                page.wait_for_selector(".glass-card", timeout=5000)
                print("Glass cards found in UI!")
                success = True
            except:
                print("No glass-cards found.")
                
            browser.close()
    except Exception as e:
        print(f"Error during test: {e}")
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
        print("\nUI Test PASSED")
        sys.exit(0)
    else:
        print("\nUI Test FAILED")
        sys.exit(1)
