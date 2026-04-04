# /home/ubuntu/jarvis-field/8501/plan_x_dashboard.py
# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime

import requests
from flask import Flask, render_template, redirect, url_for, request, send_from_directory

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
BACKUP_DIR = "/home/ubuntu/jarvis-field/8501/backups"

DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard.json")
UPDATE_RESULT_FILE = os.path.join(BASE_DIR, "update_result.json")
BACKUP_RESULT_FILE = os.path.join(BASE_DIR, "backup_result.json")

API_HEALTH_URL = "http://127.0.0.1:8505/health"
API_UPDATE_ALL_URL = "http://127.0.0.1:8505/update"
API_UPDATE_GPT_URL = "http://127.0.0.1:8505/update_gpt"
API_UPDATE_JARVIS_URL = "http://127.0.0.1:8505/update_jarvis"
API_UPDATE_WEB_URL = "http://127.0.0.1:8505/update_web"
API_RESTORE_BACKUP_URL = "http://127.0.0.1:8505/restore_backup"
API_CREATE_BACKUP_URL = "http://127.0.0.1:8505/create_backup"

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))


def load_dashboard():
    data = {
        "updated_at": "-",
        "count": 0,
        "rows": [],
        "entry_signals": 0
    }

    try:
        if os.path.exists(DASHBOARD_JSON):
            with open(DASHBOARD_JSON, "r", encoding="utf-8") as f:
                raw = json.load(f)

            rows = raw.get("rows", [])

            def row_rank(r):
                final_dir = str(r.get("final_direction", ""))
                status = str(r.get("status", ""))

                if final_dir in ["LONG", "SHORT"]:
                    return 0
                if status in ["LONG_ENTRY", "SHORT_ENTRY"]:
                    return 1
                if status in ["LONG_READY", "SHORT_READY"]:
                    return 2
                if final_dir == "WATCH":
                    return 3
                return 4

            rows = sorted(rows, key=row_rank)

            data = {
                "updated_at": raw.get("updated_at", "-"),
                "count": raw.get("count", 0),
                "rows": rows,
                "entry_signals": raw.get("entry_signals", 0)
            }

    except Exception as e:
        print(f"Data Load Error: {e}")

    return data


def default_update_statuses():
    return {
        "all": {"time": "-", "after": "-", "status": ""},
        "gpt": {"time": "-", "after": "-", "status": ""},
        "jarvis": {"time": "-", "after": "-", "status": ""},
        "web": {"time": "-", "after": "-", "status": ""}
    }


def load_update_result():
    if not os.path.exists(UPDATE_RESULT_FILE):
        return None

    try:
        with open(UPDATE_RESULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def default_backup_state():
    return {
        "last_backup": {"status": "", "filename": "-", "time": "-", "error": ""},
        "last_restore": {"status": "", "filename": "-", "time": "-", "error": ""}
    }


def load_backup_result():
    if not os.path.exists(BACKUP_RESULT_FILE):
        return default_backup_state()

    try:
        with open(BACKUP_RESULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_backup_state()


def get_api_health():
    try:
        res = requests.get(API_HEALTH_URL, timeout=5)
        return res.json()
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def get_backup_items():
    items = []
    try:
        for name in os.listdir(BACKUP_DIR):
            if name.endswith(".tar.gz"):
                full_path = os.path.join(BACKUP_DIR, name)
                stat = os.stat(full_path)
                items.append({
                    "filename": name,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
    except Exception as e:
        print("Backup read error:", e)

    return sorted(items, key=lambda x: x["filename"], reverse=True)


@app.route("/")
def home():
    data = load_dashboard()
    api_health = get_api_health()
    update_result = load_update_result()
    backup_state = load_backup_result()
    backup_items = get_backup_items()

    q = request.args.get("q", "").strip().upper()
    rows = data.get("rows", [])
    if q:
        rows = [r for r in rows if q in str(r.get("pair", "")).upper()]
    data["rows"] = rows

    current_version = "-"
    update_statuses = default_update_statuses()

    if update_result:
        if update_result.get("api", {}).get("version"):
            current_version = update_result["api"]["version"]
        elif api_health.get("version"):
            current_version = api_health.get("version")

        if update_result.get("statuses"):
            update_statuses = update_result["statuses"]

    return render_template(
        "plan_x_index.html",
        data=data,
        api_health=api_health,
        current_version=current_version,
        update_statuses=update_statuses,
        backup_state=backup_state,
        backup_items=backup_items,
        search_query=q
    )


@app.route("/update_all", methods=["POST"])
def update_all():
    try:
        requests.get(API_UPDATE_ALL_URL, timeout=60)
    except Exception as e:
        print(f"Update ALL API Call Error: {e}")
    return redirect(url_for("home"))


@app.route("/update_gpt", methods=["POST"])
def update_gpt():
    try:
        requests.get(API_UPDATE_GPT_URL, timeout=60)
    except Exception as e:
        print(f"Update GPT API Call Error: {e}")
    return redirect(url_for("home"))


@app.route("/update_jarvis", methods=["POST"])
def update_jarvis():
    try:
        requests.get(API_UPDATE_JARVIS_URL, timeout=60)
    except Exception as e:
        print(f"Update JARVIS API Call Error: {e}")
    return redirect(url_for("home"))


@app.route("/update_web", methods=["POST"])
def update_web():
    try:
        requests.get(API_UPDATE_WEB_URL, timeout=60)
    except Exception as e:
        print(f"Update WEB API Call Error: {e}")
    return redirect(url_for("home"))


@app.route("/create_backup", methods=["POST"])
def create_backup():
    try:
        requests.get(API_CREATE_BACKUP_URL, timeout=300)
    except Exception as e:
        print(f"Create Backup API Call Error: {e}")
    return redirect(url_for("home"))


@app.route("/restore_backup", methods=["POST"])
def restore_backup():
    filename = request.form.get("filename", "").strip()
    mode = request.form.get("mode", "all").strip()

    if not filename:
        return redirect(url_for("home"))

    try:
        requests.get(API_RESTORE_BACKUP_URL, params={"filename": filename, "mode": mode}, timeout=300)
    except Exception as e:
        print(f"Restore Backup API Call Error: {e}")
    return redirect(url_for("home"))


@app.route("/download_backup/<path:filename>")
def download_backup(filename):
    safe_name = os.path.basename(filename)
    return send_from_directory(BACKUP_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501)
