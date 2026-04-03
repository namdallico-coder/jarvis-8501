# /home/ubuntu/jarvis-field/8501/plan_x_dashboard.py
# -*- coding: utf-8 -*-

import os
import json
import requests
from flask import Flask, render_template, redirect, url_for

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
DASHBOARD_JSON = os.path.join(BASE_DIR, "dashboard.json")
UPDATE_RESULT_FILE = os.path.join(BASE_DIR, "update_result.json")
API_HEALTH_URL = "http://127.0.0.1:8505/health"
API_UPDATE_URL = "http://127.0.0.1:8505/update"

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))


def load_dashboard():
    data = {
        "updated_at": "-",
        "count": 0,
        "rows": [],
        "entry_signals": 0,
        "summary": {
            "gpt_long": 0,
            "gpt_short": 0,
            "jarvis_long": 0,
            "jarvis_short": 0,
            "agree": 0,
            "conflict": 0,
            "watch": 0,
            "no_trade": 0
        }
    }

    try:
        if os.path.exists(DASHBOARD_JSON):
            with open(DASHBOARD_JSON, "r", encoding="utf-8") as f:
                raw = json.load(f)

            rows = raw.get("rows", [])

            summary = {
                "gpt_long": len([r for r in rows if r.get("gpt_direction") == "LONG"]),
                "gpt_short": len([r for r in rows if r.get("gpt_direction") == "SHORT"]),
                "jarvis_long": len([r for r in rows if r.get("jarvis_direction") == "LONG"]),
                "jarvis_short": len([r for r in rows if r.get("jarvis_direction") == "SHORT"]),
                "agree": len([r for r in rows if r.get("comparison_result") == "AGREE"]),
                "conflict": len([r for r in rows if r.get("comparison_result") == "CONFLICT"]),
                "watch": len([r for r in rows if r.get("final_direction") == "WATCH"]),
                "no_trade": len([r for r in rows if r.get("manual_trade_bias") == "NO_TRADE"]),
            }

            def row_rank(r):
                final_dir = str(r.get("final_direction", ""))
                bias = str(r.get("manual_trade_bias", ""))
                comp = str(r.get("comparison_result", ""))

                if final_dir in ["LONG", "SHORT"]:
                    return 0
                if final_dir == "WATCH":
                    return 1
                if comp == "AGREE":
                    return 2
                if bias == "CAUTION":
                    return 3
                if bias == "NO_TRADE":
                    return 5
                return 4

            rows = sorted(rows, key=row_rank)

            data = {
                "updated_at": raw.get("updated_at", "-"),
                "count": raw.get("count", 0),
                "rows": rows,
                "entry_signals": raw.get("entry_signals", 0),
                "summary": summary
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
        return {"status": "ERROR", "error": str(e)}


def get_api_health():
    try:
        res = requests.get(API_HEALTH_URL, timeout=5)
        return res.json()
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


@app.route("/")
def home():
    data = load_dashboard()
    api_health = get_api_health()
    update_result = load_update_result()

    return render_template(
        "plan_x_index.html",
        data=data,
        api_health=api_health,
        update_result=update_result
    )


@app.route("/update", methods=["POST"])
def update():
    try:
        requests.get(API_UPDATE_URL, timeout=20)
    except Exception as e:
        print(f"Update API Call Error: {e}")

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8501)
