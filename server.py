import os
import sys
import glob
import json
import re
import logging
import subprocess
from flask import Flask, jsonify, send_from_directory, request, abort
from flask_cors import CORS

# Define project root explicitly
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
WEB_VIEWER_DIR = os.path.join(PROJECT_ROOT, 'web_viewer')
INDEX_HTML_PATH = os.path.join(PROJECT_ROOT, 'index.html')
PUBLIC_ROOT_FILES = {'favicon.ico', 'favicon.png'}

app = Flask(__name__, static_folder=None)
CORS(app)

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
        files = [
            path
            for path in glob.glob(pattern)
            if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
        ]
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


def _read_latest_metadata():
    """최신 total_full_*.json의 metadata를 읽는다. 파일이 없으면 None."""
    pattern = os.path.join(OUTPUT_TOTAL_DIR, "total_full_*.json")
    files = [
        path
        for path in glob.glob(pattern)
        if re.fullmatch(r"total_full_\d{8}\.json", os.path.basename(path))
    ]
    if not files:
        return None
    files.sort(reverse=True)
    with open(files[0], 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    return data.get('metadata')


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
        before_meta = _read_latest_metadata()
        before_counts = {
            'total': (before_meta or {}).get('total_count', 0),
            'threads': (before_meta or {}).get('threads_count', 0),
            'linkedin': (before_meta or {}).get('linkedin_count', 0),
            'twitter': (before_meta or {}).get('twitter_count', 0),
        }
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
        after_meta = _read_latest_metadata()
        after_counts = {
            'total': (after_meta or {}).get('total_count', 0),
            'threads': (after_meta or {}).get('threads_count', 0),
            'linkedin': (after_meta or {}).get('linkedin_count', 0),
            'twitter': (after_meta or {}).get('twitter_count', 0),
        }
        stats = {
            'total': after_counts['total'] - before_counts['total'],
            'threads': after_counts['threads'] - before_counts['threads'],
            'linkedin': after_counts['linkedin'] - before_counts['linkedin'],
            'twitter': after_counts['twitter'] - before_counts['twitter'],
            'total_count': after_counts['total'],
            'threads_count': after_counts['threads'],
            'linkedin_count': after_counts['linkedin'],
            'twitter_count': after_counts['twitter'],
        }
        return jsonify({
            "status": "success",
            "message": "Scraping finished",
            "output": stdout_val,
            "stats": stats
        })
    except Exception as e:
        logging.exception("Failed to run scraping")
        return jsonify({"status": "error", "message": "Scraping failed"}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"status": "running", "message": "Flask server is active"})


def _send_root_index():
    return send_from_directory(PROJECT_ROOT, 'index.html')


def _send_web_viewer_asset(path):
    rel_path = path[len('web_viewer/'):]
    requested = os.path.realpath(os.path.join(WEB_VIEWER_DIR, rel_path))
    web_viewer_real = os.path.realpath(WEB_VIEWER_DIR)

    if not requested.startswith(web_viewer_real + os.sep) and requested != web_viewer_real:
        abort(403)

    if os.path.exists(requested) and os.path.isfile(requested):
        return send_from_directory(WEB_VIEWER_DIR, rel_path)

    abort(404)


def _has_path_traversal(path):
    normalized = path.replace('\\', '/')
    return any(part == '..' for part in normalized.split('/'))


@app.route('/')
def index():
    if os.path.exists(INDEX_HTML_PATH):
        return _send_root_index()
    return "index.html not found", 404


@app.route('/<path:path>')
def static_proxy(path):
    if _has_path_traversal(path):
        abort(403)

    if path in PUBLIC_ROOT_FILES:
        return send_from_directory(PROJECT_ROOT, path)

    if path.startswith('web_viewer/'):
        return _send_web_viewer_asset(path)

    if '.' in os.path.basename(path):
        abort(404)

    if os.path.exists(INDEX_HTML_PATH):
        return _send_root_index()

    abort(404)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    print(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False)
