from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
import subprocess
import os
import sys
import glob
import json

# Flask ? ??
app = Flask(__name__)
# CORS ?? (?? index.html?? ?? ?????)
CORS(app)

OUTPUT_TOTAL_DIR = "output_total"

@app.route('/api/get-tags', methods=['GET'])
def get_tags():
    """web_viewer/sns_tags.json ??? ??? ?????."""
    try:
        export_path = os.path.join("web_viewer", "sns_tags.json")
        if not os.path.exists(export_path):
            return jsonify({}) # ??? ??? ? ?? ??
            
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        print(f"?? ?? ???? ? ?? ??: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/save-tags', methods=['POST'])
def save_tags():
    """???????? ?? ?? ???? docs/sns_tags_export.json ??? ?????."""
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
            
        print(f"?? ?? ???? {export_path}? ???????.")
        return jsonify({"status": "success", "message": f"Saved to {export_path}"})
    except Exception as e:
        print(f"?? ?? ?? ? ?? ??: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/latest-data', methods=['GET'])
def get_latest_data():
    """?? ??? total_full_*.json ??? ?? ?????."""
    try:
        # 1. output_total ?? total_full_*.json ?? ??
        pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
        files = glob.glob(pattern)
        
        if not files:
            return jsonify({"error": "??? ??? ?? ? ????."}), 404
            
        # 2. ??? ???? ?? (??? ???? ???? ??? ?? ??)
        files.sort(reverse=True)
        latest_file = files[0]
        
        # 3. ?? ?? ? ??
        with open(latest_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
            
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/run-scrap', methods=['POST'])
def run_scrap():
    try:
        # total_scrap.py ?? ??
        script_path = os.path.join(os.getcwd(), 'total_scrap.py')
        
        if not os.path.exists(script_path):
            return jsonify({
                "status": "error",
                "message": f"Script not found: {script_path}"
            }), 404

        # ???? ?? (?????? ???? ??? Popen? ??)
        # ???? ??? ??? ????? ??? ??? (?, ??? ?? ??? ???? ?? ??)
        # ??? ?? ??? ??? ??? ??? ????? ?? ??? ??? ? ??
        
        # ???? mode ???? ???? (???: update)
        data = request.json or {}
        mode = data.get('mode', 'update')
        
        print(f"?? UI ???? {script_path} ?? ?... (??: {mode})")
        
        # subprocess.Popen? ???? ??? ?? ?? ??
        # -u ??? ???? ??? ?? ?? ????? ?
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        process = subprocess.Popen(
            [sys.executable, "-u", script_path, "--mode", mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )

        full_output = []
        # ????? ??? ??? ?? ???? ??
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                print(line, end="", flush=True)
                full_output.append(line)
        
        process.wait()
        stdout_val = "".join(full_output[-20:]) # ??? ??? ??? ??

        if process.returncode == 0:
            print("\n? ???? ????? ??.")
            
            # ?? ????? ????
            stats = {"total": 0, "threads": 0, "linkedin": 0}
            try:
                pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
                files = glob.glob(pattern)
                if files:
                    files.sort(reverse=True)
                    with open(files[0], 'r', encoding='utf-8') as f:
                        latest_data = json.load(f)
                        meta = latest_data.get('metadata', {})
                        stats["total"] = meta.get('total_count', 0)
                        stats["threads"] = meta.get('threads_count', 0)
                        stats["linkedin"] = meta.get('linkedin_count', 0)
            except Exception as e:
                print(f"?? ?? ??? ?? ? ??: {str(e)}")

            return jsonify({
                "status": "success",
                "message": "Scraping completed successfully.",
                "stats": stats,
                "output": stdout_val
            })
        else:
            print(f"? ???? ?? (??: {process.returncode})")
            if stdout_val:
                print(f"--- Error Details ---\n{stdout_val}\n--------------------")
            return jsonify({
                "status": "error",
                "message": f"Scraping failed with exit code {process.returncode}",
                "error": stdout_val
            }), 500

    except Exception as e:
        print(f"?? ?? ?? ??: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "message": "Flask server is active"})

    # 5000 ???? ??
@app.route('/')
def index():
    return send_from_directory('web_viewer', 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    if os.path.exists(os.path.join('web_viewer', path)):
        return send_from_directory('web_viewer', path)
    return send_from_directory('web_viewer', 'index.html')

if __name__ == '__main__':
    # 5000 포트에서 실행
    print("✨ Flask Backend Server running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
