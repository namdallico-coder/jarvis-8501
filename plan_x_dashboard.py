# /home/ubuntu/jarvis-field/8501/plan_x_dashboard.py
# -*- coding: utf-8 -*-

import os
import json
import requests
from flask import Flask, render_template, redirect, url_for, request

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard.json")
UPDATE_RESULT_FILE = os.path.join(BASE_DIR, "update_result.json")

API_HEALTH_URL = "http://127.0.0.1:8505/health"
API_UPDATE_ALL_URL = "http://127.0.0.1:8505/update"
API_UPDATE_GPT_URL = "http://127.0.0.1:8505/update_gpt"
API_UPDATE_JARVIS_URL = "http://127.0.0.1:8505/update_jarvis"
API_UPDATE_WEB_URL = "http://127.0.0.1:8505/update_web"

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


def load_update_result():
    if not os.path.exists(UPDATE_RESULT_FILE):
        return None

    try:
        with open(UPDATE_RESULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {
            "update": {
                "mode": "unknown",
                "status": "ERROR",
                "before": "-",
                "after": "-",
                "target": "-",
                "updated_files": [],
                "output": "",
                "error": str(e),
                "time": "-"
            },
            "api": {
                "service": "jarvis-8501-api.service",
                "status": "ERROR",
                "version": "-",
                "origin_main": "-",
                "last_update": "-"
            },
            "engine_restart": {
                "service": "jarvis-8501.service",
                "status": "ERROR",
                "error": str(e)
            },
            "web_restart": {
                "service": "jarvis-8501-web.service",
                "status": "ERROR",
                "error": str(e)
            }
        }


def get_api_health():
    try:
        res = requests.get(API_HEALTH_URL, timeout=5)
        return res.json()
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e)
        }


@app.route("/")
def home():
    data = load_dashboard()
    api_health = get_api_health()
    update_result = load_update_result()

    q = request.args.get("q", "").strip().upper()
    rows = data.get("rows", [])

    if q:
        rows = [r for r in rows if q in str(r.get("pair", "")).upper()]

    data["rows"] = rows

    current_version = "-"
    if update_result and update_result.get("api", {}).get("version"):
        current_version = update_result["api"]["version"]
    elif api_health.get("version"):
        current_version = api_health.get("version")

    return render_template(
        "plan_x_index.html",
        data=data,
        api_health=api_health,
        update_result=update_result,
        current_version=current_version,
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501)
