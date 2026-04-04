# /home/ubuntu/jarvis-field/8501/plan_x_api_v1.py
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import requests
from datetime import datetime
from fastapi import FastAPI

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
UPDATE_RESULT_FILE = f"{BASE_DIR}/update_result.json"

ENGINE_SERVICE = "jarvis-8501.service"
WEB_SERVICE = "jarvis-8501-web.service"
API_SERVICE = "jarvis-8501-api.service"

TELEGRAM_TOKEN = "8746898502:AAHqiBZEcec5guPwFTeJG6xZOq9J87KUP58"
TELEGRAM_CHAT_ID = "8462590648"

app = FastAPI(title="JARVIS 8501 API")

FILE_GROUPS = {
    "gpt": ["plan_x_engine.py"],
    "jarvis": ["plan_x_logic.py"],
    "web": ["plan_x_dashboard.py", "templates/plan_x_index.html"]
}


def run_cmd(cmd, timeout=60):
    try:
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "ok": result.returncode == 0,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
            "code": result.returncode
        }
    except Exception as e:
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(e),
            "code": -1
        }


def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"[JARVIS-8501]\n{msg}"
            },
            timeout=10
        )
    except Exception:
        pass


def get_git_version(ref="HEAD"):
    result = run_cmd(["git", "rev-parse", "--short", ref])
    return result["stdout"] if result["ok"] else "UNKNOWN"


def get_last_update_time():
    result = run_cmd(["git", "log", "-1", "--format=%cd", "--date=iso"])
    return result["stdout"] if result["ok"] else "UNKNOWN"


def schedule_restart(service_name):
    try:
        subprocess.Popen(
            [
                "bash",
                "-lc",
                f"sleep 2 && sudo /usr/bin/systemctl restart {service_name}"
            ],
            cwd=BASE_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return {
            "service": service_name,
            "status": "SCHEDULED",
            "error": ""
        }
    except Exception as e:
        return {
            "service": service_name,
            "status": "ERROR",
            "error": str(e)
        }


def fetch_origin_main():
    return run_cmd(["git", "fetch", "origin", "main"], timeout=120)


def default_statuses():
    return {
        "all": {"time": "-", "after": "-", "status": ""},
        "gpt": {"time": "-", "after": "-", "status": ""},
        "jarvis": {"time": "-", "after": "-", "status": ""},
        "web": {"time": "-", "after": "-", "status": ""}
    }


def read_update_result():
    if not os.path.exists(UPDATE_RESULT_FILE):
        return {
            "latest": {},
            "statuses": default_statuses(),
            "api": {}
        }

    try:
        with open(UPDATE_RESULT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "statuses" not in data:
            data["statuses"] = default_statuses()
        if "latest" not in data:
            data["latest"] = {}

        return data
    except Exception:
        return {
            "latest": {},
            "statuses": default_statuses(),
            "api": {}
        }


def write_update_result(latest_result):
    data = read_update_result()
    mode = latest_result.get("mode", "unknown")

    data["latest"] = latest_result

    if mode in data["statuses"]:
        data["statuses"][mode] = {
            "time": latest_result.get("time", "-"),
            "after": latest_result.get("after", "-"),
            "status": latest_result.get("status", "")
        }

    data["api"] = {
        "service": API_SERVICE,
        "status": "RUNNING",
        "version": get_git_version("HEAD"),
        "origin_main": get_git_version("origin/main"),
        "last_update": get_last_update_time()
    }

    with open(UPDATE_RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_base_result(mode):
    return {
        "mode": mode,
        "status": "ERROR",
        "before": get_git_version("HEAD"),
        "after": get_git_version("HEAD"),
        "target": get_git_version("origin/main"),
        "updated_files": [],
        "output": "",
        "error": "",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "engine_restart": {"service": ENGINE_SERVICE, "status": "SKIPPED", "error": ""},
        "web_restart": {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""}
    }


def full_update():
    result = build_base_result("all")
    result["updated_files"] = ["ALL"]

    fetch_result = fetch_origin_main()
    result["target"] = get_git_version("origin/main")

    if not fetch_result["ok"]:
        result["error"] = fetch_result["stderr"] or "git fetch failed"
        result["output"] = fetch_result["stdout"]
        return result

    pull_result = run_cmd(["git", "pull", "origin", "main"], timeout=120)
    result["after"] = get_git_version("HEAD")
    result["output"] = pull_result["stdout"] or "Already up to date."
    result["error"] = pull_result["stderr"]

    if pull_result["ok"]:
        result["status"] = "SUCCESS"
        result["engine_restart"] = schedule_restart(ENGINE_SERVICE)
        result["web_restart"] = schedule_restart(WEB_SERVICE)
    else:
        if not result["error"]:
            result["error"] = "git pull failed"

    return result


def partial_update(target_name):
    result = build_base_result(target_name)
    files = FILE_GROUPS.get(target_name, [])
    result["updated_files"] = files

    fetch_result = fetch_origin_main()
    result["target"] = get_git_version("origin/main")

    if not fetch_result["ok"]:
        result["error"] = fetch_result["stderr"] or "git fetch failed"
        result["output"] = fetch_result["stdout"]
        return result

    checkout_cmd = ["git", "checkout", "origin/main", "--"] + files
    checkout_result = run_cmd(checkout_cmd, timeout=120)

    result["after"] = get_git_version("HEAD")
    result["output"] = checkout_result["stdout"] or "Selected files updated from origin/main"
    result["error"] = checkout_result["stderr"]

    if checkout_result["ok"]:
        result["status"] = "SUCCESS"

        if target_name in ["gpt", "jarvis"]:
            result["engine_restart"] = schedule_restart(ENGINE_SERVICE)

        if target_name == "web":
            result["web_restart"] = schedule_restart(WEB_SERVICE)
    else:
        if not result["error"]:
            result["error"] = "partial checkout failed"

    return result


def finalize(result):
    write_update_result(result)

    if result["status"] == "SUCCESS":
        send_telegram(
            f"✅ {result['mode'].upper()} 업데이트 완료\n"
            f"time={result.get('time', '-')}\n"
            f"after={result.get('after', '-')}"
        )
    else:
        send_telegram(
            f"❌ {result['mode'].upper()} 업데이트 실패\n"
            f"time={result.get('time', '-')}\n"
            f"error={result.get('error', '-')}"
        )

    return result


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "jarvis-8501-api",
        "version": get_git_version("HEAD"),
        "origin_main": get_git_version("origin/main"),
        "last_update": get_last_update_time()
    }


@app.get("/update")
def update_all():
    return finalize(full_update())


@app.get("/update_gpt")
def update_gpt():
    return finalize(partial_update("gpt"))


@app.get("/update_jarvis")
def update_jarvis():
    return finalize(partial_update("jarvis"))


@app.get("/update_web")
def update_web():
    return finalize(partial_update("web"))
