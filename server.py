from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
import subprocess
import os
import sys
import glob
import json

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

OUTPUT_TOTAL_DIR = "output_total"

@app.route('/api/get-tags', methods=['GET'])
def get_tags():
    try:
        export_path = os.path.join("web_viewer", "sns_tags.json")
        if not os.path.exists(export_path):
            return jsonify({})
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/save-tags', methods=['POST'])
def save_tags():
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
        return jsonify({"status": "success", "message": f"Saved to {export_path}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/latest-data', methods=['GET'])
def get_latest_data():
    try:
        pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
        files = glob.glob(pattern)
        if not files:
            return jsonify({"error": "Data file not found"}), 404
        files.sort(reverse=True)
        latest_file = files[0]
        with open(latest_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/run-scrap', methods=['POST'])
def run_scrap():
    try:
        script_path = os.path.join(os.getcwd(), 'total_scrap.py')
        if not os.path.exists(script_path):
            return jsonify({"status": "error", "message": "Script not found"}), 404
        data = request.json or {}
        mode = data.get('mode', 'update')
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
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                full_output.append(line)
        process.wait()
        stdout_val = "".join(full_output[-20:])
        return jsonify({"status": "success", "message": "Scraping finished", "output": stdout_val})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "message": "Flask server is active"})

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    if os.path.exists(os.path.join('.', path)):
        return send_from_directory('.', path)
    if os.path.exists(os.path.join('web_viewer', path)):
        return send_from_directory('web_viewer', path)
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
