from flask import Flask, jsonify
from flask_cors import CORS
import subprocess
import os
import sys

# Flask 앱 설정
app = Flask(__name__)
# CORS 허용 (로컬 index.html에서 요청 가능하도록)
CORS(app)

@app.route('/api/run-scrap', methods=['POST'])
def run_scrap():
    try:
        # total_scrap.py 경로 확인
        script_path = os.path.join(os.getcwd(), 'total_scrap.py')
        
        if not os.path.exists(script_path):
            return jsonify({
                "status": "error",
                "message": f"Script not found: {script_path}"
            }), 404

        # 스크립트 실행 (비동기적으로 실행하고 싶으면 Popen을 사용)
        # 여기서는 완료될 때까지 기다렸다가 결과를 응답함 (단, 시간이 오래 걸리면 타임아웃 발생 가능)
        # 실시간 진행 상황을 보려면 로그를 파일로 저장하거나 다른 방식이 필요할 수 있음
        
        print(f"🚀 UI 요청으로 {script_path} 실행 중...")
        
        # subprocess.run을 사용하여 실행 결과 대기
        # Windows 환경의 인코딩 문제를 방지하기 위해 env 설정 및 errors='replace' 추가
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        process = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )

        stdout_val = process.stdout[-1000:] if process.stdout else ""
        stderr_val = process.stderr[-1000:] if process.stderr else ""

        if process.returncode == 0:
            print("✅ 스크래핑 성공적으로 완료.")
            return jsonify({
                "status": "success",
                "message": "Scraping completed successfully.",
                "output": stdout_val
            })
        else:
            print(f"❌ 스크래핑 실패 (코드: {process.returncode})")
            if stderr_val:
                print(f"--- Error Details ---\n{stderr_val}\n--------------------")
            return jsonify({
                "status": "error",
                "message": f"Scraping failed with exit code {process.returncode}",
                "error": stderr_val
            }), 500

    except Exception as e:
        print(f"⚠️ 서버 에러 발생: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "message": "Flask server is active"})

if __name__ == '__main__':
    # 5000 포트에서 실행
    print("✨ Flask Backend Server running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
