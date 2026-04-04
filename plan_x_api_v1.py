# /home/ubuntu/jarvis-field/8501/plan_x_api_v1.py
# -*- coding: utf-8 -*-

import json
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
    "gpt": [
        "plan_x_engine.py"
    ],
    "jarvis": [
        "plan_x_logic.py"
    ],
    "web": [
        "plan_x_dashboard.py",
        "templates/plan_x_index.html"
    ]
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


def write_update_result(data):
    try:
        with open(UPDATE_RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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


def get_git_version(ref="HEAD"):
    result = run_cmd(["git", "rev-parse", "--short", ref])
    return result["stdout"] if result["ok"] else "UNKNOWN"


def get_last_update_time():
    result = run_cmd(["git", "log", "-1", "--format=%cd", "--date=iso"])
    return result["stdout"] if result["ok"] else "UNKNOWN"


def fetch_origin_main():
    return run_cmd(["git", "fetch", "origin", "main"], timeout=120)


def full_update():
    before = get_git_version("HEAD")
    origin_version = get_git_version("origin/main")

    fetch_result = fetch_origin_main()
    if not fetch_result["ok"]:
        return {
            "mode": "all",
            "status": "ERROR",
            "before": before,
            "target": origin_version,
            "output": fetch_result["stdout"],
            "error": fetch_result["stderr"] or "git fetch failed",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    pull_result = run_cmd(["git", "pull", "origin", "main"], timeout=120)
    after = get_git_version("HEAD")

    if pull_result["ok"]:
        return {
            "mode": "all",
            "status": "SUCCESS",
            "before": before,
            "after": after,
            "target": origin_version,
            "output": pull_result["stdout"] or "Already up to date.",
            "error": pull_result["stderr"],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    return {
        "mode": "all",
        "status": "ERROR",
        "before": before,
        "after": after,
        "target": origin_version,
        "output": pull_result["stdout"],
        "error": pull_result["stderr"] or "git pull failed",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def partial_update(target_name):
    files = FILE_GROUPS.get(target_name, [])
    head_before = get_git_version("HEAD")
    origin_version = get_git_version("origin/main")

    fetch_result = fetch_origin_main()
    if not fetch_result["ok"]:
        return {
            "mode": target_name,
            "status": "ERROR",
            "before": head_before,
            "target": origin_version,
            "updated_files": [],
            "output": fetch_result["stdout"],
            "error": fetch_result["stderr"] or "git fetch failed",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    checkout_cmd = ["git", "checkout", "origin/main", "--"] + files
    checkout_result = run_cmd(checkout_cmd, timeout=120)

    if not checkout_result["ok"]:
        return {
            "mode": target_name,
            "status": "ERROR",
            "before": head_before,
            "target": origin_version,
            "updated_files": files,
            "output": checkout_result["stdout"],
            "error": checkout_result["stderr"] or "partial checkout failed",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    return {
        "mode": target_name,
        "status": "SUCCESS",
        "before": head_before,
        "after": head_before,
        "target": origin_version,
        "updated_files": files,
        "output": "Selected files updated from origin/main",
        "error": "",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def build_restart_result(target_name, update_status):
    if update_status != "SUCCESS":
        return {
            "engine_restart": {"service": ENGINE_SERVICE, "status": "SKIPPED", "error": ""},
            "web_restart": {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""}
        }

    if target_name == "all":
        return {
            "engine_restart": schedule_restart(ENGINE_SERVICE),
            "web_restart": schedule_restart(WEB_SERVICE)
        }

    if target_name == "gpt":
        return {
            "engine_restart": schedule_restart(ENGINE_SERVICE),
            "web_restart": {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""}
        }

    if target_name == "jarvis":
        return {
            "engine_restart": schedule_restart(ENGINE_SERVICE),
            "web_restart": {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""}
        }

    if target_name == "web":
        return {
            "engine_restart": {"service": ENGINE_SERVICE, "status": "SKIPPED", "error": ""},
            "web_restart": schedule_restart(WEB_SERVICE)
        }

    return {
        "engine_restart": {"service": ENGINE_SERVICE, "status": "SKIPPED", "error": ""},
        "web_restart": {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""}
    }


def finalize_result(target_name, update_result):
    restart_result = build_restart_result(target_name, update_result["status"])

    final_result = {
        "update": update_result,
        "api": {
            "service": API_SERVICE,
            "status": "RUNNING",
            "version": get_git_version("HEAD"),
            "last_update": get_last_update_time()
        },
        "engine_restart": restart_result["engine_restart"],
        "web_restart": restart_result["web_restart"]
    }

    write_update_result(final_result)

    if update_result["status"] == "SUCCESS":
        send_telegram(
            f"✅ {target_name.upper()} 업데이트 완료\n"
            f"before={update_result.get('before', '-')}\n"
            f"target={update_result.get('target', '-')}\n"
            f"after={update_result.get('after', '-')}\n"
            f"{update_result.get('output', '')}"
        )
    else:
        send_telegram(
            f"❌ {target_name.upper()} 업데이트 실패\n"
            f"{update_result.get('error', '')}"
        )

    return final_result


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
    update_result = full_update()
    return finalize_result("all", update_result)


@app.get("/update_gpt")
def update_gpt():
    update_result = partial_update("gpt")
    return finalize_result("gpt", update_result)


@app.get("/update_jarvis")
def update_jarvis():
    update_result = partial_update("jarvis")
    return finalize_result("jarvis", update_result)


@app.get("/update_web")
def update_web():
    update_result = partial_update("web")
    return finalize_result("web", update_result)
