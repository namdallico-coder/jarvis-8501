# /home/ubuntu/jarvis-field/8501/plan_x_logic.py
# -*- coding: utf-8 -*-

import requests


class JarvisPlenX:
    def __init__(self):
        self.ticker_url = "https://fapi.binance.com/fapi/v1/ticker/price"
        self.depth_url = "https://fapi.binance.com/fapi/v1/depth"
        self.klines_url = "https://fapi.binance.com/fapi/v1/klines"
        self.timeout = 3

    def _symbol(self, coin_name):
        return coin_name.strip().upper() + "USDT"

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default

    def get_price(self, symbol):
        res = requests.get(self.ticker_url, params={"symbol": symbol}, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        return self._safe_float(data.get("price"))

    def get_pressure(self, symbol):
        res = requests.get(self.depth_url, params={"symbol": symbol, "limit": 20}, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        bid_vol = sum(self._safe_float(b[1]) for b in bids[:10])
        ask_vol = sum(self._safe_float(a[1]) for a in asks[:10])

        if bid_vol <= 0:
            return 1.0, bid_vol, ask_vol

        pressure = ask_vol / bid_vol
        return pressure, bid_vol, ask_vol

    def get_trend(self, symbol, interval="5m", limit=12):
        res = requests.get(
            self.klines_url,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=self.timeout
        )
        res.raise_for_status()
        data = res.json()

        if not data or len(data) < 2:
            return 0.0, 0.0, 0.0

        first_open = self._safe_float(data[0][1])
        last_close = self._safe_float(data[-1][4])

        highs = [self._safe_float(x[2]) for x in data]
        lows = [self._safe_float(x[3]) for x in data]
        volumes = [self._safe_float(x[5]) for x in data]

        trend_pct = ((last_close - first_open) / first_open * 100.0) if first_open > 0 else 0.0
        volatility_pct = ((max(highs) - min(lows)) / first_open * 100.0) if first_open > 0 else 0.0
        avg_volume = sum(volumes) / len(volumes) if volumes else 0.0

        return trend_pct, volatility_pct, avg_volume

    def get_coin_snapshot(self, coin_name):
        symbol = self._symbol(coin_name)

        price = self.get_price(symbol)
        pressure, bid_vol, ask_vol = self.get_pressure(symbol)

        trend_5m, vol_5m, avg_vol_5m = self.get_trend(symbol, "5m", 12)
        trend_15m, vol_15m, avg_vol_15m = self.get_trend(symbol, "15m", 12)
        trend_1h, vol_1h, avg_vol_1h = self.get_trend(symbol, "1h", 12)

        return {
            "symbol": symbol,
            "price": price,
            "pressure": pressure,
            "bid_vol": bid_vol,
            "ask_vol": ask_vol,
            "trend_5m": trend_5m,
            "trend_15m": trend_15m,
            "trend_1h": trend_1h,
            "volatility_5m": vol_5m,
            "volatility_15m": vol_15m,
            "volatility_1h": vol_1h,
            "avg_volume_5m": avg_vol_5m,
            "avg_volume_15m": avg_vol_15m,
            "avg_volume_1h": avg_vol_1h
        }

    def get_pair_market_data(self, pair_name):
        try:
            if "/" not in pair_name:
                return None

            left_coin, right_coin = pair_name.split("/")
            left_coin = left_coin.strip().upper()
            right_coin = right_coin.strip().upper()

            left = self.get_coin_snapshot(left_coin)
            right = self.get_coin_snapshot(right_coin)

            return {
                "left_coin": left_coin,
                "right_coin": right_coin,
                "left": left,
                "right": right
            }
        except Exception as e:
            return {
                "error": str(e)
            }

    def score_direction(self, market):
        left = market["left"]
        right = market["right"]

        left_score = 0
        right_score = 0

        if left["trend_5m"] > right["trend_5m"]:
            left_score += 1
        else:
            right_score += 1

        if left["trend_15m"] > right["trend_15m"]:
            left_score += 1
        else:
            right_score += 1

        if left["trend_1h"] > right["trend_1h"]:
            left_score += 1
        else:
            right_score += 1

        if left["pressure"] < right["pressure"]:
            left_score += 1
        else:
            right_score += 1

        return left_score, right_score

    def build_reason(self, market, left_score, right_score):
        left = market["left"]
        right = market["right"]

        return (
            f"{market['left_coin']} 점수={left_score}, "
            f"5m={left['trend_5m']:.2f}%, 15m={left['trend_15m']:.2f}%, 1h={left['trend_1h']:.2f}%, "
            f"pressure={left['pressure']:.2f} | "
            f"{market['right_coin']} 점수={right_score}, "
            f"5m={right['trend_5m']:.2f}%, 15m={right['trend_15m']:.2f}%, 1h={right['trend_1h']:.2f}%, "
            f"pressure={right['pressure']:.2f}"
        )

    def self_analyze(self, row):
        pair_name = str(row.get("pair", "")).strip().upper()
        x_score = self._safe_float(row.get("x_score", 50))
        status = str(row.get("status", "WAIT")).strip().upper()

        market = self.get_pair_market_data(pair_name)

        if not market or market.get("error"):
            return {
                "jarvis_status": "⚠️ 대기",
                "jarvis_reason": f"BINANCE_ERROR: {market.get('error', 'DATA_EMPTY') if market else 'DATA_EMPTY'}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        left = market["left"]
        right = market["right"]

        left_score, right_score = self.score_direction(market)
        reason = self.build_reason(market, left_score, right_score)

        if left["volatility_5m"] > 8 or right["volatility_5m"] > 8:
            return {
                "jarvis_status": "💤 진입지연",
                "jarvis_reason": f"단기 변동성 과도 | {reason}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        if x_score <= 28 and status in ["LONG_ENTRY", "LONG_READY", "WAIT", "SKIP"]:
            if left_score >= 3 and left["pressure"] < 1.0 and left["trend_5m"] >= 0:
                entry = round(left["price"] * 1.001, 4)
                target = round(left["price"] * 1.015, 4)
                return {
                    "jarvis_status": "💎 강력승인(LONG)",
                    "jarvis_reason": f"좌측 코인 강세 확인 | {reason}",
                    "jarvis_start": entry,
                    "jarvis_end": target
                }
            return {
                "jarvis_status": "💤 진입지연",
                "jarvis_reason": f"LONG 조건 미충족 | {reason}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        if x_score >= 72 and status in ["SHORT_ENTRY", "SHORT_READY", "WAIT", "SKIP"]:
            if right_score >= 3 and left["pressure"] > 1.0 and left["trend_5m"] <= 0:
                entry = round(left["price"] * 0.999, 4)
                target = round(left["price"] * 0.985, 4)
                return {
                    "jarvis_status": "🔥 강력승인(SHORT)",
                    "jarvis_reason": f"좌측 코인 약세 확인 | {reason}",
                    "jarvis_start": entry,
                    "jarvis_end": target
                }
            return {
                "jarvis_status": "💤 진입지연",
                "jarvis_reason": f"SHORT 조건 미충족 | {reason}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        return {
            "jarvis_status": "🚫 패스",
            "jarvis_reason": f"중립 구간 / 조건 미충족 | {reason}",
            "jarvis_start": "-",
            "jarvis_end": "-"
        }
