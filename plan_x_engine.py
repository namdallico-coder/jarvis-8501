# /home/ubuntu/jarvis-field/8501/plan_x_engine.py
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import traceback
from datetime import datetime, timedelta
from statistics import mean, pstdev

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from plan_x_logic import JarvisPlenX

BASE_DIR = "/home/ubuntu/jarvis-field/8501"
SIGNALS_FILE = os.path.join(BASE_DIR, "signals.json")
STATE_FILE = os.path.join(BASE_DIR, "collector_state.json")
DASHBOARD_FILE = os.path.join(BASE_DIR, "dashboard.json")
LAST_STATUS_FILE = os.path.join(BASE_DIR, "last_status.json")
PREDICTION_LOG_FILE = os.path.join(BASE_DIR, "prediction_log.json")
XSCORE_HISTORY_FILE = os.path.join(BASE_DIR, "xscore_history.json")

CHROMEDRIVER_PATH = "/snap/bin/chromium.chromedriver"
CHROMIUM_BINARY = "/usr/bin/chromium-browser"

PLENX_LOGIN_URL = os.getenv("PLENX_LOGIN_URL", "https://v2.plenx.io/login")
PLENX_DASHBOARD_URL = os.getenv("PLENX_DASHBOARD_URL", "https://v2.plenx.io/dashboard/binance")
PLENX_EMAIL = os.getenv("PLENX_EMAIL", "westside3500@naver.com")
PLENX_PASSWORD = os.getenv("PLENX_PASSWORD", "@@ww23456")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8746898502:AAHqiBZEcec5guPwFTeJG6xZOq9J87KUP58")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8462590648")

COLLECT_INTERVAL = 30
WAIT_TIMEOUT = 20
PAIR_LIMIT = 24
HEADLESS = True
MAX_LOG_ROWS = 5000
MAX_HISTORY_PER_PAIR = 240

jarvis = JarvisPlenX()


def now_kst():
    return datetime.utcnow() + timedelta(hours=9)


def now_kst_str():
    return now_kst().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"{now_kst_str()} {msg}", flush=True)


def ensure_dir():
    os.makedirs(BASE_DIR, exist_ok=True)


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def send_system_alert(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"[PLAN-X 8501]\n{msg}"
            },
            timeout=10
        )
    except Exception:
        pass


def clamp(value, low, high):
    return max(low, min(high, value))


def calc_quality(tier, x_score):
    score = 40 if tier == "1" else (28 if tier == "2" else 18)
    if 20 <= x_score <= 28 or 72 <= x_score <= 80:
        score += 35
    elif 28 < x_score <= 35 or 65 <= x_score < 72:
        score += 18
    else:
        score += 5
    return round(min(score, 100), 2)


def calc_recommended_amount(tier, quality):
    return "높음" if tier == "1" and quality >= 85 else ("중간" if quality >= 70 else "낮음")


def calc_winrate(quality):
    return round(max(45, min(75, 45 + (quality * 0.25))), 2)


def calc_roi(x_score, quality):
    return round((abs(x_score - 50) / 2.5) * (quality / 100) * 10, 2)


def calc_safe(quality):
    return round(max(100, min(170, 100 + (quality * 0.7))), 2)


def load_xscore_history():
    return load_json(XSCORE_HISTORY_FILE, {})


def update_xscore_history(items):
    history = load_xscore_history()
    current_time = now_kst_str()

    for item in items:
        pair = item["pair"]
        x_score = float(item["x_score"])

        pair_hist = history.get(pair, [])
        pair_hist.append({
            "time": current_time,
            "x_score": x_score
        })

        if len(pair_hist) > MAX_HISTORY_PER_PAIR:
            pair_hist = pair_hist[-MAX_HISTORY_PER_PAIR:]

        history[pair] = pair_hist

    write_json(XSCORE_HISTORY_FILE, history)
    return history


def get_xscore_stats(pair, history):
    pair_hist = history.get(pair, [])
    values = [float(x["x_score"]) for x in pair_hist if "x_score" in x]

    if len(values) < 3:
        return {
            "slope_5": 0.0,
            "volatility_20": 0.0
        }

    recent_5 = values[-5:] if len(values) >= 5 else values
    slope_5 = recent_5[-1] - recent_5[0]

    recent_20 = values[-20:] if len(values) >= 20 else values
    volatility_20 = pstdev(recent_20) if len(recent_20) >= 2 else 0.0

    return {
        "slope_5": round(slope_5, 4),
        "volatility_20": round(volatility_20, 4)
    }


def moving_toward_center(x_score, slope):
    if x_score < 50:
        return slope > 0
    if x_score > 50:
        return slope < 0
    return False


def calc_status_from_xscore(x_score, slope, volatility):
    """
    플렌X 실제 X-Score 기준 상태 판단
    - 낮은 점수 = LONG 쪽
    - 높은 점수 = SHORT 쪽
    """
    if volatility > 12:
        return "WAIT"

    # LONG
    if x_score <= 28:
        if moving_toward_center(x_score, slope):
            return "LONG_ENTRY"
        return "LONG_READY"

    # SHORT
    if x_score >= 72:
        if moving_toward_center(x_score, slope):
            return "SHORT_ENTRY"
        return "SHORT_READY"

    if 45 <= x_score <= 55:
        return "WAIT"

    return "WAIT"


def calc_gpt_direction(status):
    if status in ["LONG_ENTRY", "LONG_READY"]:
        return "LONG"
    if status in ["SHORT_ENTRY", "SHORT_READY"]:
        return "SHORT"
    if status == "SKIP":
        return "SKIP"
    return "WAIT"


def calc_gpt_xscore_range(x_score, status, slope, volatility):
    x = float(x_score)

    # 변동성 높으면 범위를 넓힌다
    width_bonus = 0
    if volatility >= 8:
        width_bonus = 3
    elif volatility >= 5:
        width_bonus = 1

    # LONG
    if status == "LONG_ENTRY":
        start_x = clamp(round(x - (6 + width_bonus)), 5, 28)
        end_x = clamp(round(x + (12 + width_bonus)), 18, 45)
        if start_x >= end_x:
            start_x = max(5, end_x - 6)
        return start_x, end_x

    if status == "LONG_READY":
        start_x = clamp(round(x - (4 + width_bonus)), 8, 32)
        end_x = clamp(round(x + (8 + width_bonus)), 18, 45)
        if start_x >= end_x:
            start_x = max(5, end_x - 5)
        return start_x, end_x

    # SHORT
    if status == "SHORT_ENTRY":
        start_x = clamp(round(x - (12 + width_bonus)), 55, 82)
        end_x = clamp(round(x + (6 + width_bonus)), 72, 95)
        if start_x >= end_x:
            start_x = max(55, end_x - 6)
        return start_x, end_x

    if status == "SHORT_READY":
        start_x = clamp(round(x - (8 + width_bonus)), 55, 85)
        end_x = clamp(round(x + (4 + width_bonus)), 68, 92)
        if start_x >= end_x:
            start_x = max(55, end_x - 5)
        return start_x, end_x

    return "-", "-"


def normalize_jarvis_result(result):
    jarvis_status = str(result.get("jarvis_status", "WAIT")).upper()
    jarvis_reason = str(result.get("jarvis_reason", "")).strip() or "JARVIS_REASON_EMPTY"
    jarvis_start = result.get("jarvis_start", "-")
    jarvis_end = result.get("jarvis_end", "-")

    if "SHORT" in jarvis_status:
        direction = "SHORT"
        confidence = 78
    elif "LONG" in jarvis_status:
        direction = "LONG"
        confidence = 78
    elif "SKIP" in jarvis_status:
        direction = "SKIP"
        confidence = 35
    else:
        direction = "WAIT"
        confidence = 45

    return {
        "jarvis_direction": direction,
        "jarvis_confidence": confidence,
        "jarvis_reason": jarvis_reason,
        "jarvis_status_text": jarvis_status,
        "jarvis_start": jarvis_start,
        "jarvis_end": jarvis_end
    }


def compare_gpt_vs_jarvis(gpt_direction, jarvis_direction, jarvis_confidence):
    if gpt_direction in ["LONG", "SHORT"] and jarvis_direction == gpt_direction:
        return {
            "comparison_result": "AGREE",
            "comparison_reason": "GPT와 JARVIS 방향 일치",
            "manual_trade_bias": "AGREE_HIGH" if jarvis_confidence >= 70 else "AGREE_LOW"
        }

    if gpt_direction in ["LONG", "SHORT"] and jarvis_direction in ["LONG", "SHORT"] and gpt_direction != jarvis_direction:
        return {
            "comparison_result": "CONFLICT",
            "comparison_reason": "GPT와 JARVIS 방향 충돌",
            "manual_trade_bias": "CAUTION"
        }

    if jarvis_direction in ["WAIT", "SKIP"] and gpt_direction in ["LONG", "SHORT"]:
        return {
            "comparison_result": "WEAK_GPT_ONLY",
            "comparison_reason": "GPT 신호는 있으나 JARVIS가 보수적",
            "manual_trade_bias": "GPT_ONLY"
        }

    if gpt_direction in ["WAIT", "SKIP"] and jarvis_direction in ["LONG", "SHORT"]:
        return {
            "comparison_result": "WEAK_JARVIS_ONLY",
            "comparison_reason": "JARVIS 신호는 있으나 GPT가 보수적",
            "manual_trade_bias": "JARVIS_ONLY"
        }

    return {
        "comparison_result": "NO_TRADE",
        "comparison_reason": "양측 모두 진입 신호 아님",
        "manual_trade_bias": "NO_TRADE"
    }


def choose_final_range(gpt_start, gpt_end, jarvis_start, jarvis_end):
    if isinstance(gpt_start, int) and isinstance(gpt_end, int) and isinstance(jarvis_start, int) and isinstance(jarvis_end, int):
        start_x = max(min(gpt_start, gpt_end), min(jarvis_start, jarvis_end))
        end_x = min(max(gpt_start, gpt_end), max(jarvis_start, jarvis_end))

        if start_x < end_x:
            return start_x, end_x

        return min(gpt_start, jarvis_start), max(gpt_end, jarvis_end)

    if isinstance(gpt_start, int) and isinstance(gpt_end, int):
        return gpt_start, gpt_end

    if isinstance(jarvis_start, int) and isinstance(jarvis_end, int):
        return jarvis_start, jarvis_end

    return "-", "-"


def decide_final(gpt_direction, gpt_start, gpt_end, jarvis_direction, jarvis_start, jarvis_end, comparison):
    result = comparison["comparison_result"]
    bias = comparison["manual_trade_bias"]

    if result == "AGREE":
        final_start, final_end = choose_final_range(gpt_start, gpt_end, jarvis_start, jarvis_end)
        return gpt_direction, "GPT+JARVIS", final_start, final_end

    # 너무 보수적으로 비우지 말고 단독 후보도 최종값 허용
    if bias == "GPT_ONLY" and gpt_direction in ["LONG", "SHORT"]:
        return gpt_direction, "GPT_ONLY", gpt_start, gpt_end

    if bias == "JARVIS_ONLY" and jarvis_direction in ["LONG", "SHORT"]:
        return jarvis_direction, "JARVIS_ONLY", jarvis_start, jarvis_end

    if bias == "CAUTION":
        return "WAIT", "SYSTEM", "-", "-"

    if gpt_direction == "SKIP":
        return "SKIP", "GPT", "-", "-"

    return "WAIT", "SYSTEM", "-", "-"


def build_row(item, history):
    pair = item["pair"].strip().upper()
    tier = str(item.get("tier", "1"))
    actual_x_score = round(float(item.get("x_score", 0.0)), 2)

    stats = get_xscore_stats(pair, history)
    slope_5 = stats["slope_5"]
    volatility_20 = stats["volatility_20"]

    estimated = jarvis.estimate_planx_xscore(pair)
    estimated_xscore = estimated.get("estimated_xscore")
    estimated_method = estimated.get("method", "-")

    quality = calc_quality(tier, actual_x_score)
    status = calc_status_from_xscore(actual_x_score, slope_5, volatility_20)
    decision = "진입강력" if "ENTRY" in status else ("주의관찰" if "READY" in status else "대기")

    gpt_direction = calc_gpt_direction(status)
    gpt_start, gpt_end = calc_gpt_xscore_range(actual_x_score, status, slope_5, volatility_20)

    if gpt_direction == "LONG":
        gpt_status = "GPT_LONG"
        gpt_reason = "플렌X 실제 X-Score 기반 LONG 구간 계산"
    elif gpt_direction == "SHORT":
        gpt_status = "GPT_SHORT"
        gpt_reason = "플렌X 실제 X-Score 기반 SHORT 구간 계산"
    else:
        gpt_status = "GPT_WAIT"
        gpt_reason = "중립 또는 대기"

    jarvis_raw = jarvis.self_analyze({
        "pair": pair,
        "x_score": actual_x_score,
        "status": status,
        "quality": quality,
        "decision": decision
    })

    jarvis_norm = normalize_jarvis_result(jarvis_raw)
    jarvis_direction = jarvis_norm["jarvis_direction"]
    jarvis_confidence = jarvis_norm["jarvis_confidence"]
    jarvis_reason = jarvis_norm["jarvis_reason"]
    jarvis_status_text = jarvis_norm["jarvis_status_text"]
    jarvis_start = jarvis_norm["jarvis_start"]
    jarvis_end = jarvis_norm["jarvis_end"]

    comparison = compare_gpt_vs_jarvis(gpt_direction, jarvis_direction, jarvis_confidence)

    final_direction, final_source, final_start, final_end = decide_final(
        gpt_direction, gpt_start, gpt_end,
        jarvis_direction, jarvis_start, jarvis_end,
        comparison
    )

    merged_reason = (
        f"actual_x={actual_x_score}, slope_5={slope_5}, vol_20={volatility_20}\n"
        f"GPT: {gpt_reason}\n"
        f"JARVIS: {jarvis_reason}\n"
        f"비교: {comparison['comparison_reason']}\n"
        f"FINAL: {final_direction} ({final_source})"
    )

    return {
        "pair": pair,
        "tier": tier,
        "x_score": actual_x_score,
        "estimated_x_score": estimated_xscore,
        "estimated_method": estimated_method,
        "estimated_z_score": estimated.get("z_score"),
        "xscore_gap": round(actual_x_score - estimated_xscore, 2) if isinstance(estimated_xscore, (int, float)) else "-",

        "status": status,
        "quality": quality,
        "decision": decision,
        "slope_5": slope_5,
        "volatility_20": volatility_20,

        "jarvis_status": f"{gpt_status} | {jarvis_status_text} | FINAL_{final_direction}",
        "jarvis_reason": merged_reason,
        "jarvis_start": jarvis_start,
        "jarvis_end": jarvis_end,

        "recommended_amount": calc_recommended_amount(tier, quality),
        "winrate": calc_winrate(quality),
        "roi": calc_roi(actual_x_score, quality),
        "safe": calc_safe(quality),
        "updated_at": now_kst_str(),

        "gpt_direction": gpt_direction,
        "gpt_status": gpt_status,
        "gpt_reason": gpt_reason,
        "gpt_start": gpt_start,
        "gpt_end": gpt_end,

        "jarvis_direction": jarvis_direction,
        "jarvis_confidence": jarvis_confidence,
        "jarvis_reason_only": jarvis_reason,
        "jarvis_status_text": jarvis_status_text,

        "comparison_result": comparison["comparison_result"],
        "comparison_reason": comparison["comparison_reason"],
        "manual_trade_bias": comparison["manual_trade_bias"],

        "final_direction": final_direction,
        "final_status": final_direction,
        "final_source": final_source,
        "final_start": final_start,
        "final_end": final_end
    }


def safe_build_row(item, history):
    try:
        return build_row(item, history)
    except Exception as e:
        pair = str(item.get("pair", "UNKNOWN")).strip().upper()
        return {
            "pair": pair,
            "tier": str(item.get("tier", "1")),
            "x_score": round(float(item.get("x_score", 0.0)), 2),
            "estimated_x_score": "-",
            "estimated_method": "error",
            "estimated_z_score": "-",
            "xscore_gap": "-",

            "status": "ERROR",
            "quality": 0,
            "decision": "오류",
            "slope_5": 0,
            "volatility_20": 0,

            "jarvis_status": "ROW_ERROR",
            "jarvis_reason": f"ROW_ERROR: {str(e)[:120]}",
            "jarvis_start": "-",
            "jarvis_end": "-",

            "recommended_amount": "낮음",
            "winrate": 0,
            "roi": 0,
            "safe": 0,
            "updated_at": now_kst_str(),

            "gpt_direction": "WAIT",
            "gpt_status": "GPT_WAIT",
            "gpt_reason": "오류",
            "gpt_start": "-",
            "gpt_end": "-",

            "jarvis_direction": "WAIT",
            "jarvis_confidence": 0,
            "jarvis_reason_only": "ROW_ERROR",
            "jarvis_status_text": "ROW_ERROR",

            "comparison_result": "ERROR",
            "comparison_reason": "ROW_BUILD_ERROR",
            "manual_trade_bias": "NO_TRADE",

            "final_direction": "WAIT",
            "final_status": "WAIT",
            "final_source": "ERROR",
            "final_start": "-",
            "final_end": "-"
        }


def append_prediction_logs(rows):
    logs = load_json(PREDICTION_LOG_FILE, [])
    current_time = now_kst_str()
    new_logs = []

    for r in rows:
        new_logs.append({
            "logged_at": current_time,
            "pair": r.get("pair", ""),
            "x_score": r.get("x_score", 0),
            "estimated_x_score": r.get("estimated_x_score", "-"),
            "xscore_gap": r.get("xscore_gap", "-"),
            "status": r.get("status", ""),

            "gpt_direction": r.get("gpt_direction", ""),
            "gpt_start": r.get("gpt_start", "-"),
            "gpt_end": r.get("gpt_end", "-"),

            "jarvis_direction": r.get("jarvis_direction", ""),
            "jarvis_confidence": r.get("jarvis_confidence", 0),
            "jarvis_start": r.get("jarvis_start", "-"),
            "jarvis_end": r.get("jarvis_end", "-"),

            "comparison_result": r.get("comparison_result", ""),
            "manual_trade_bias": r.get("manual_trade_bias", ""),

            "final_direction": r.get("final_direction", ""),
            "final_source": r.get("final_source", ""),
            "final_start": r.get("final_start", "-"),
            "final_end": r.get("final_end", "-")
        })

    logs.extend(new_logs)

    if len(logs) > MAX_LOG_ROWS:
        logs = logs[-MAX_LOG_ROWS:]

    write_json(PREDICTION_LOG_FILE, logs)


def build_driver():
    options = Options()
    options.binary_location = CHROMIUM_BINARY

    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,2400")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--single-process")
    options.add_argument("--no-zygote")

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(40)
    return driver


def first_visible(driver, selectors, timeout=WAIT_TIMEOUT):
    end_at = time.time() + timeout
    while time.time() < end_at:
        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        return el
            except Exception:
                pass
        time.sleep(0.5)
    return None


def plenx_login(driver):
    log("[BOOT] login start")
    driver.get(PLENX_LOGIN_URL)
    time.sleep(5)

    email_selectors = [
        "input[type='email']",
        "input[name='email']",
        "input[placeholder*='Email']",
        "input[placeholder*='email']",
        "input[type='text']",
    ]

    pw_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='Password']",
        "input[placeholder*='password']",
    ]

    email_el = first_visible(driver, email_selectors, timeout=15)
    pw_el = first_visible(driver, pw_selectors, timeout=15)

    if not email_el or not pw_el:
        raise RuntimeError("로그인 입력창을 찾지 못했습니다.")

    email_el.clear()
    email_el.send_keys(PLENX_EMAIL)
    time.sleep(1)

    pw_el.clear()
    pw_el.send_keys(PLENX_PASSWORD)
    time.sleep(1)

    clicked = False
    button_candidates = driver.find_elements(By.CSS_SELECTOR, "button, input[type='submit'], div[role='button']")
    for btn in button_candidates:
        try:
            txt = ((btn.text or "") + " " + str(btn.get_attribute("value") or "")).strip().lower()
            if any(x in txt for x in ["login", "log in", "sign in", "signin", "continue"]):
                driver.execute_script("arguments[0].click();", btn)
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        pw_el.send_keys(Keys.ENTER)

    time.sleep(8)
    log("[BOOT] login success")


def collect_pairs(driver):
    driver.get(PLENX_DASHBOARD_URL)
    time.sleep(12)

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(2)
    except Exception:
        pass

    body_text = driver.execute_script("return document.body ? document.body.innerText : ''")
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]

    results = []
    seen = set()

    i = 0
    while i < len(lines) - 3:
        coin1 = lines[i].upper()
        coin2 = lines[i + 1].upper()
        marker = lines[i + 2]
        value_line = lines[i + 3]

        if (
            re.fullmatch(r"[A-Z0-9]{2,10}", coin1)
            and re.fullmatch(r"[A-Z0-9]{2,10}", coin2)
            and (
                "X-Score" in marker
                or "X점수" in marker
                or "X-점수" in marker
                or "X-SCORE" in marker.upper()
            )
        ):
            nums = re.findall(r"[-+]?\d+(?:\.\d+)?", value_line)
            if nums:
                x_score = float(nums[0])
                pair = f"{coin1}/{coin2}"

                if pair not in seen:
                    seen.add(pair)
                    results.append({
                        "pair": pair,
                        "tier": "1",
                        "x_score": x_score
                    })

        if len(results) >= PAIR_LIMIT:
            break

        i += 1

    log(f"[PLENX] parsed rows: {len(results)}")
    return results


def detect_entry_change(rows):
    prev = load_json(LAST_STATUS_FILE, {})
    alerts = []

    for r in rows:
        pair = r["pair"]
        current = str(r.get("status", "")).strip().upper()
        prev_status = str(prev.get(pair, "")).strip().upper()

        if prev_status in ["WAIT", "SKIP"] and current in ["LONG_ENTRY", "SHORT_ENTRY"]:
            alerts.append(
                f"🚨 ENTRY 전환 발생\n"
                f"{pair}\n"
                f"{prev_status} → {current}\n"
                f"플렌X={r.get('x_score', '-')}\n"
                f"GPT={r.get('gpt_start', '-')}/{r.get('gpt_end', '-')}\n"
                f"JARVIS={r.get('jarvis_start', '-')}/{r.get('jarvis_end', '-')}\n"
                f"FINAL={r.get('final_direction', '-')}\n"
                f"FINAL_X={r.get('final_start', '-')}/{r.get('final_end', '-')}"
            )

    new_state = {r["pair"]: r["status"] for r in rows}
    write_json(LAST_STATUS_FILE, new_state)

    return alerts


def process_cycle(driver, state):
    items = collect_pairs(driver)
    history = update_xscore_history(items)
    rows = [safe_build_row(item, history) for item in items]

    payload = {
        "updated_at": now_kst_str(),
        "count": len(rows),
        "entry_signals": len([r for r in rows if "ENTRY" in r["status"]]),
        "rows": rows
    }

    write_json(SIGNALS_FILE, payload)
    write_json(DASHBOARD_FILE, payload)
    append_prediction_logs(rows)

    basic_alerts = detect_entry_change(rows)
    for msg in basic_alerts:
        send_system_alert(msg)

    log(f"Cycle Complete: {len(rows)} rows saved.")


def main():
    ensure_dir()
    state = load_json(STATE_FILE, {})
    driver = None
    last_heartbeat = 0

    while True:
        try:
            if driver is None:
                driver = build_driver()
                plenx_login(driver)

            process_cycle(driver, state)

            if time.time() - last_heartbeat > 3600:
                send_system_alert("✅ SYSTEM OK - 정상 동작 중")
                last_heartbeat = time.time()

        except Exception as e:
            log(f"Error: {e}")
            traceback.print_exc()

            send_system_alert(f"🚨 CRITICAL ERROR\n{str(e)}")

            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            driver = None

        time.sleep(COLLECT_INTERVAL)


if __name__ == "__main__":
    main()
