# /home/ubuntu/jarvis-field/8501/plan_x_api_v1.py
# -*- coding: utf-8 -*-

import json
import os
import shutil
import subprocess
from datetime import datetime

import requests
from fastapi import FastAPI, Query

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
PROJECT_ROOT = "/home/ubuntu/jarvis-field"
BACKUP_DIR = "/home/ubuntu/backups"

UPDATE_RESULT_FILE = f"{BASE_DIR}/update_result.json"
BACKUP_RESULT_FILE = f"{BASE_DIR}/backup_result.json"

ENGINE_SERVICE = "jarvis-8501.service"
WEB_SERVICE = "jarvis-8501-web.service"
API_SERVICE = "jarvis-8501-api.service"

TELEGRAM_TOKEN = "여기에_텔레그램_토큰"
TELEGRAM_CHAT_ID = "여기에_텔레그램_채팅ID"

app = FastAPI(title="JARVIS 8501 API")

FILE_GROUPS = {
    "gpt": ["plan_x_engine.py"],
    "jarvis": ["plan_x_logic.py"],
    "web": ["plan_x_dashboard.py", "templates/plan_x_index.html"]
}


def run_cmd(cmd, timeout=60, cwd=None):
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or BASE_DIR,
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


def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


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


def read_backup_result():
    if not os.path.exists(BACKUP_RESULT_FILE):
        return {
            "last_backup": {
                "status": "",
                "filename": "-",
                "time": "-",
                "error": ""
            },
            "last_restore": {
                "status": "",
                "filename": "-",
                "time": "-",
                "error": ""
            }
        }

    try:
        with open(BACKUP_RESULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "last_backup": {
                "status": "ERROR",
                "filename": "-",
                "time": "-",
                "error": "backup_result.json read error"
            },
            "last_restore": {
                "status": "ERROR",
                "filename": "-",
                "time": "-",
                "error": "backup_result.json read error"
            }
        }


def write_backup_result(data):
    with open(BACKUP_RESULT_FILE, "w", encoding="utf-8") as f:
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


def finalize_update(result):
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


def list_backups():
    ensure_backup_dir()

    files = []
    for name in os.listdir(BACKUP_DIR):
        if not name.endswith(".tar.gz"):
            continue

        full_path = os.path.join(BACKUP_DIR, name)
        try:
            stat = os.stat(full_path)
            files.append({
                "filename": name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception:
            continue

    files.sort(key=lambda x: x["filename"], reverse=True)
    return files


def create_backup():
    ensure_backup_dir()

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jarvis_backup_{now_str}.tar.gz"
    full_path = os.path.join(BACKUP_DIR, filename)

    cmd = [
        "tar",
        "-czf",
        full_path,
        "jarvis-field"
    ]

    result = run_cmd(cmd, timeout=300, cwd="/home/ubuntu")

    backup_state = read_backup_result()

    if result["ok"]:
        backup_state["last_backup"] = {
            "status": "SUCCESS",
            "filename": filename,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": ""
        }
        write_backup_result(backup_state)

        send_telegram(f"✅ 백업 생성 완료\n{filename}")

        return {
            "status": "SUCCESS",
            "filename": filename,
            "time": backup_state["last_backup"]["time"],
            "output": result["stdout"] or "backup created",
            "error": ""
        }

    backup_state["last_backup"] = {
        "status": "ERROR",
        "filename": filename,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": result["stderr"] or "backup failed"
    }
    write_backup_result(backup_state)

    send_telegram(f"❌ 백업 생성 실패\n{filename}\n{backup_state['last_backup']['error']}")

    return {
        "status": "ERROR",
        "filename": filename,
        "time": backup_state["last_backup"]["time"],
        "output": result["stdout"],
        "error": backup_state["last_backup"]["error"]
    }


def restore_backup(filename):
    ensure_backup_dir()

    safe_name = os.path.basename(filename)
    full_path = os.path.join(BACKUP_DIR, safe_name)

    backup_state = read_backup_result()

    if not os.path.exists(full_path):
        backup_state["last_restore"] = {
            "status": "ERROR",
            "filename": safe_name,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "backup file not found"
        }
        write_backup_result(backup_state)

        return {
            "status": "ERROR",
            "filename": safe_name,
            "time": backup_state["last_restore"]["time"],
            "output": "",
            "error": "backup file not found",
            "engine_restart": {"service": ENGINE_SERVICE, "status": "SKIPPED", "error": ""},
            "web_restart": {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""},
            "api_restart": {"service": API_SERVICE, "status": "SKIPPED", "error": ""}
        }

    cmd = [
        "tar",
        "-xzf",
        full_path,
        "-C",
        "/home/ubuntu"
    ]

    result = run_cmd(cmd, timeout=300, cwd="/home/ubuntu")

    engine_restart = {"service": ENGINE_SERVICE, "status": "SKIPPED", "error": ""}
    web_restart = {"service": WEB_SERVICE, "status": "SKIPPED", "error": ""}
    api_restart = {"service": API_SERVICE, "status": "SKIPPED", "error": ""}

    if result["ok"]:
        engine_restart = schedule_restart(ENGINE_SERVICE)
        web_restart = schedule_restart(WEB_SERVICE)
        api_restart = schedule_restart(API_SERVICE)

        backup_state["last_restore"] = {
            "status": "SUCCESS",
            "filename": safe_name,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": ""
        }
        write_backup_result(backup_state)

        send_telegram(f"✅ 롤백 완료\n{safe_name}")

        return {
            "status": "SUCCESS",
            "filename": safe_name,
            "time": backup_state["last_restore"]["time"],
            "output": result["stdout"] or "restore complete",
            "error": "",
            "engine_restart": engine_restart,
            "web_restart": web_restart,
            "api_restart": api_restart
        }

    backup_state["last_restore"] = {
        "status": "ERROR",
        "filename": safe_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": result["stderr"] or "restore failed"
    }
    write_backup_result(backup_state)

    send_telegram(f"❌ 롤백 실패\n{safe_name}\n{backup_state['last_restore']['error']}")

    return {
        "status": "ERROR",
        "filename": safe_name,
        "time": backup_state["last_restore"]["time"],
        "output": result["stdout"],
        "error": backup_state["last_restore"]["error"],
        "engine_restart": engine_restart,
        "web_restart": web_restart,
        "api_restart": api_restart
    }


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
    return finalize_update(full_update())


@app.get("/update_gpt")
def update_gpt():
    return finalize_update(partial_update("gpt"))


@app.get("/update_jarvis")
def update_jarvis():
    return finalize_update(partial_update("jarvis"))


@app.get("/update_web")
def update_web():
    return finalize_update(partial_update("web"))


@app.get("/backups")
def backups():
    return {
        "status": "SUCCESS",
        "items": list_backups(),
        "last_state": read_backup_result()
    }


@app.get("/create_backup")
def create_backup_api():
    return create_backup()


@app.get("/restore_backup")
def restore_backup_api(filename: str = Query(...)):
    return restore_backup(filename)
