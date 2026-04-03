# /home/ubuntu/jarvis-field/8501/plan_x_api_v1.py
# -*- coding: utf-8 -*-

import json
import subprocess
from datetime import datetime

from fastapi import FastAPI

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
UPDATE_RESULT_FILE = f"{BASE_DIR}/update_result.json"

WEB_SERVICE = "jarvis-8501-web.service"
API_SERVICE = "jarvis-8501-api.service"

app = FastAPI(title="JARVIS 8501 API")


# -----------------------
# 공통
# -----------------------

def run_cmd(cmd, timeout=30):
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
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "code": result.returncode
        }
    except Exception as e:
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(e),
            "code": -1
        }


def write_update_result(data):
    try:
        with open(UPDATE_RESULT_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def schedule_web_restart():
    subprocess.Popen(
        [
            "bash",
            "-lc",
            f"sleep 2 && sudo systemctl restart {WEB_SERVICE}"
        ]
    )


# -----------------------
# API
# -----------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "jarvis-8501-api"
    }


@app.get("/update")
def update():

    fetch = run_cmd(["git", "fetch", "origin", "main"], timeout=60)

    if not fetch["ok"]:
        result = {
            "status": "ERROR",
            "error": fetch["stderr"]
        }
        write_update_result(result)
        return result

    pull = run_cmd(["git", "pull", "origin", "main"], timeout=60)

    if pull["ok"]:
        result = {
            "status": "SUCCESS",
            "output": pull["stdout"],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        schedule_web_restart()

    else:
        result = {
            "status": "ERROR",
            "error": pull["stderr"]
        }

    write_update_result(result)
    return result
