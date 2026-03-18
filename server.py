import os
import sys
import glob
import json
import logging
import subprocess
from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS

# Define project root explicitly
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
WEB_VIEWER_DIR = os.path.join(PROJECT_ROOT, 'web_viewer')

app = Flask(__name__, static_folder=WEB_VIEWER_DIR, static_url_path='')
CORS(app, origins=os.environ.get('CORS_ORIGINS', 'http://localhost:*,http://127.0.0.1:*').split(','))

OUTPUT_TOTAL_DIR = os.path.join(PROJECT_ROOT, "output_total")

@app.route('/api/get-tags', methods=['GET'])
def get_tags():
    try:
        export_path = os.path.join(WEB_VIEWER_DIR, "sns_tags.json")
        if not os.path.exists(export_path):
            return jsonify({})
        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        logging.exception("Failed to get tags")
        return jsonify({"error": "Failed to load tags"}), 500

@app.route('/api/save-tags', methods=['POST'])
def save_tags():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid data format: expected JSON object"}), 400
        if not os.path.exists(WEB_VIEWER_DIR):
            os.makedirs(WEB_VIEWER_DIR)
        export_path = os.path.join(WEB_VIEWER_DIR, "sns_tags.json")
        with open(export_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return jsonify({"status": "success", "message": "Tags saved successfully"})
    except Exception as e:
        logging.exception("Failed to save tags")
        return jsonify({"status": "error", "message": "Failed to save tags"}), 500

@app.route('/api/latest-data', methods=['GET'])
def get_latest_data():
    try:
        pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
        files = glob.glob(pattern)
        if not files:
            return jsonify({"error": "Data file not found"}), 404
        files.sort(reverse=True)
        latest_file = files[0]
        # Some files might have BOM
        with open(latest_file, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        logging.exception("Failed to load latest data")
        return jsonify({"error": "Failed to load data"}), 500

ALLOWED_SCRAP_MODES = {'update', 'all'}

@app.route('/api/run-scrap', methods=['POST'])
def run_scrap():
    try:
        script_path = os.path.join(PROJECT_ROOT, 'total_scrap.py')
        if not os.path.exists(script_path):
            return jsonify({"status": "error", "message": "Script not found"}), 404
        data = request.json or {}
        mode = data.get('mode', 'update')
        if mode not in ALLOWED_SCRAP_MODES:
            return jsonify({"status": "error", "message": f"Invalid mode. Allowed: {', '.join(sorted(ALLOWED_SCRAP_MODES))}"}), 400
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
        logging.exception("Failed to run scraping")
        return jsonify({"status": "error", "message": "Scraping failed"}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "message": "Flask server is active"})

@app.route('/')
def index():
    index_path = os.path.join(WEB_VIEWER_DIR, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(WEB_VIEWER_DIR, 'index.html')
    return "index.html not found", 404

@app.route('/<path:path>')
def static_proxy(path):
    # Prevent path traversal: resolve and verify within web_viewer
    requested = os.path.realpath(os.path.join(WEB_VIEWER_DIR, path))
    web_viewer_real = os.path.realpath(WEB_VIEWER_DIR)
    if not requested.startswith(web_viewer_real + os.sep) and requested != web_viewer_real:
        abort(403)

    if os.path.exists(requested) and os.path.isfile(requested):
        return send_from_directory(WEB_VIEWER_DIR, path)

    # Fallback to index.html for SPA-style routing
    index_path = os.path.join(WEB_VIEWER_DIR, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(WEB_VIEWER_DIR, 'index.html')
    abort(404)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    print(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False)
