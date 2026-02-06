from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
import subprocess
import os
import sys
import glob
import json

# Flask 앱 설정
app = Flask(__name__)
# CORS 허용 (로컬 index.html에서 요청 가능하도록)
CORS(app)

OUTPUT_TOTAL_DIR = "output_total"

@app.route('/api/get-tags', methods=['GET'])
def get_tags():
    """web_viewer/sns_tags.json 파일을 읽어서 반환합니다."""
    try:
        export_path = os.path.join("web_viewer", "sns_tags.json")
        if not os.path.exists(export_path):
            return jsonify({}) # 파일이 없으면 빈 객체 반환
            
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        print(f"⚠️ 태그 불러오기 중 에러 발생: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/save-tags', methods=['POST'])
def save_tags():
    """클라이언트로부터 받은 태그 데이터를 docs/sns_tags_export.json 파일로 저장합니다."""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        target_dir = "web_viewer"
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        export_path = os.path.join(target_dir, "sns_tags.json")
        
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        print(f"💾 태그 데이터가 {export_path}에 저장되었습니다.")
        return jsonify({"status": "success", "message": f"Saved to {export_path}"})
    except Exception as e:
        print(f"⚠️ 태그 저장 중 에러 발생: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/latest-data', methods=['GET'])
def get_latest_data():
    """가장 최신의 total_full_*.json 파일을 찾아 반환합니다."""
    try:
        # 1. output_total 내의 total_full_*.json 파일 검색
        pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
        files = glob.glob(pattern)
        
        if not files:
            return jsonify({"error": "데이터 파일을 찾을 수 없습니다."}), 404
            
        # 2. 파일명 기준으로 정렬 (날짜가 포함되어 있으므로 최신순 정렬 가능)
        files.sort(reverse=True)
        latest_file = files[0]
        
        # 3. 파일 읽기 및 반환
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        
        # 요청에서 mode 파라미터 가져오기 (기본값: update)
        data = request.json or {}
        mode = data.get('mode', 'update')
        
        print(f"🚀 UI 요청으로 {script_path} 실행 중... (모드: {mode})")
        
        # subprocess.run을 사용하여 실행 결과 대기
        # Windows 환경의 인코딩 문제를 방지하기 위해 env 설정 및 errors='replace' 추가
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        process = subprocess.run(
            [sys.executable, script_path, "--mode", mode],
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
