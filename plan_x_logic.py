# /home/ubuntu/jarvis-field/8501/plan_x_logic.py
# -*- coding: utf-8 -*-

import math
import time
import requests
from statistics import mean, pstdev


class JarvisPlenX:
    def __init__(self):
        self.book_ticker_url = "https://fapi.binance.com/fapi/v1/ticker/bookTicker"
        self.klines_url = "https://fapi.binance.com/fapi/v1/klines"
        self.depth_url = "https://fapi.binance.com/fapi/v1/depth"
        self.timeout = 3

        self.price_cache = {}
        self.kline_cache = {}

        # 현재 확보된 파라미터 샘플
        self.pair_params = {
            "DOT/CHZ": {"alpha": 0.0357, "beta": 0.00087},
            "THETA/GALA": {"alpha": 0.00005, "beta": 0.0209},
            "FIL/ENJ": {"alpha": -0.0168, "beta": 0.0351},
        }

    def _safe_float(self, value, default=0.0):
        try:
            return float(value)
        except Exception:
            return default

    def _symbol(self, coin_name):
        return coin_name.strip().upper() + "USDT"

    def _clamp(self, value, low, high):
        return max(low, min(high, value))

    def _round_x(self, value):
        return int(round(value))

    def _cache_get(self, cache, key, ttl):
        item = cache.get(key)
        if not item:
            return None
        if time.time() - item["ts"] > ttl:
            return None
        return item["value"]

    def _cache_set(self, cache, key, value):
        cache[key] = {
            "ts": time.time(),
            "value": value
        }

    def get_mid_price(self, symbol):
        cache_key = f"mid:{symbol}"
        cached = self._cache_get(self.price_cache, cache_key, ttl=5)
        if cached is not None:
            return cached

        res = requests.get(
            self.book_ticker_url,
            params={"symbol": symbol},
            timeout=self.timeout
        )
        res.raise_for_status()
        data = res.json()

        bid = self._safe_float(data.get("bidPrice"))
        ask = self._safe_float(data.get("askPrice"))

        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2.0
        elif bid > 0:
            mid = bid
        else:
            mid = ask

        self._cache_set(self.price_cache, cache_key, mid)
        return mid

    def get_closes(self, symbol, interval="1m", limit=1440):
        cache_key = f"klines:{symbol}:{interval}:{limit}"
        cached = self._cache_get(self.kline_cache, cache_key, ttl=60)
        if cached is not None:
            return cached

        res = requests.get(
            self.klines_url,
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            },
            timeout=self.timeout
        )
        res.raise_for_status()
        data = res.json()

        closes = [self._safe_float(x[4]) for x in data if len(x) > 4]
        self._cache_set(self.kline_cache, cache_key, closes)
        return closes

    def get_pressure(self, symbol):
        res = requests.get(
            self.depth_url,
            params={"symbol": symbol, "limit": 20},
            timeout=self.timeout
        )
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
        closes = self.get_closes(symbol, interval=interval, limit=limit)

        if not closes or len(closes) < 2:
            return 0.0, 0.0

        first_price = self._safe_float(closes[0])
        last_price = self._safe_float(closes[-1])

        if first_price <= 0:
            return 0.0, 0.0

        trend_pct = ((last_price - first_price) / first_price) * 100.0

        returns = []
        for i in range(1, len(closes)):
            prev_price = self._safe_float(closes[i - 1])
            curr_price = self._safe_float(closes[i])
            if prev_price > 0:
                returns.append((curr_price - prev_price) / prev_price)

        volatility = pstdev(returns) if len(returns) >= 2 else 0.0
        return trend_pct, volatility

    def get_coin_snapshot(self, coin_name):
        symbol = self._symbol(coin_name)

        price = self.get_mid_price(symbol)
        pressure, bid_vol, ask_vol = self.get_pressure(symbol)

        trend_5m, vol_5m = self.get_trend(symbol, "5m", 12)
        trend_15m, vol_15m = self.get_trend(symbol, "15m", 12)
        trend_1h, vol_1h = self.get_trend(symbol, "1h", 12)

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
            "volatility_1h": vol_1h
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

    def estimate_planx_xscore(self, pair_name):
        """
        플렌X 추정 X-Score:
        score = 50 + (z_score * 15.05)
        50 아래 = LONG 쪽
        50 위 = SHORT 쪽
        """
        if "/" not in pair_name:
            return {
                "estimated_xscore": None,
                "z_score": None,
                "spread": None,
                "spread_std": None,
                "method": "invalid_pair"
            }

        left_coin, right_coin = pair_name.split("/")
        left_coin = left_coin.strip().upper()
        right_coin = right_coin.strip().upper()

        left_symbol = self._symbol(left_coin)
        right_symbol = self._symbol(right_coin)

        left_closes = self.get_closes(left_symbol, interval="1m", limit=1440)
        right_closes = self.get_closes(right_symbol, interval="1m", limit=1440)

        if not left_closes or not right_closes:
            return {
                "estimated_xscore": None,
                "z_score": None,
                "spread": None,
                "spread_std": None,
                "method": "data_empty"
            }

        n = min(len(left_closes), len(right_closes))
        left_closes = left_closes[-n:]
        right_closes = right_closes[-n:]

        params = self.pair_params.get(pair_name)
        alpha = 0.0
        beta = 1.0

        if params:
            alpha = self._safe_float(params.get("alpha"), 0.0)
            beta = self._safe_float(params.get("beta"), 1.0)

        spreads = []
        for a, b in zip(left_closes, right_closes):
            if a > 0 and b > 0:
                spread = math.log(a) - ((beta * math.log(b)) + alpha)
                spreads.append(spread)

        if len(spreads) < 30:
            return {
                "estimated_xscore": None,
                "z_score": None,
                "spread": None,
                "spread_std": None,
                "method": "not_enough_data"
            }

        spread_mean = mean(spreads)
        spread_std = pstdev(spreads)

        if spread_std <= 0:
            return {
                "estimated_xscore": 50.0,
                "z_score": 0.0,
                "spread": spreads[-1],
                "spread_std": spread_std,
                "method": "zero_std",
                "alpha": alpha,
                "beta": beta
            }

        current_spread = spreads[-1]
        z_score = (current_spread - spread_mean) / spread_std

        x_score = 50.0 + (z_score * 15.05)
        x_score = self._clamp(x_score, 0.0, 100.0)

        return {
            "estimated_xscore": round(x_score, 2),
            "z_score": round(z_score, 4),
            "spread": round(current_spread, 6),
            "spread_std": round(spread_std, 6),
            "method": "spread_model" if params else "ratio_like_fallback",
            "alpha": alpha,
            "beta": beta
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
            f"{market['left_coin']} score={left_score}, "
            f"5m={left['trend_5m']:.2f}%, 15m={left['trend_15m']:.2f}%, 1h={left['trend_1h']:.2f}%, "
            f"pressure={left['pressure']:.2f} | "
            f"{market['right_coin']} score={right_score}, "
            f"5m={right['trend_5m']:.2f}%, 15m={right['trend_15m']:.2f}%, 1h={right['trend_1h']:.2f}%, "
            f"pressure={right['pressure']:.2f}"
        )

    def _long_range(self, x_score, left_score, pressure):
        start_x = self._clamp(self._round_x(x_score - 5), 5, 30)
        end_x = self._clamp(self._round_x(x_score + 10), 18, 45)

        if left_score >= 3 and pressure < 1.0:
            end_x = self._clamp(end_x + 3, 18, 45)

        if start_x >= end_x:
            start_x = max(5, end_x - 6)

        return start_x, end_x

    def _short_range(self, x_score, right_score, pressure):
        start_x = self._clamp(self._round_x(x_score - 10), 55, 82)
        end_x = self._clamp(self._round_x(x_score + 5), 70, 95)

        if right_score >= 3 and pressure > 1.0:
            start_x = self._clamp(start_x - 3, 55, 82)

        if start_x >= end_x:
            start_x = max(55, end_x - 6)

        return start_x, end_x

    def self_analyze(self, row):
        pair_name = str(row.get("pair", "")).strip().upper()
        actual_x_score = self._safe_float(row.get("x_score", 50.0))
        status = str(row.get("status", "WAIT")).strip().upper()

        market = self.get_pair_market_data(pair_name)
        if not market or market.get("error"):
            return {
                "jarvis_status": "WAIT",
                "jarvis_reason": f"BINANCE_ERROR: {market.get('error', 'DATA_EMPTY') if market else 'DATA_EMPTY'}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        left = market["left"]
        right = market["right"]
        left_score, right_score = self.score_direction(market)
        reason = self.build_reason(market, left_score, right_score)

        if left["volatility_5m"] > 0.03 or right["volatility_5m"] > 0.03:
            return {
                "jarvis_status": "WAIT",
                "jarvis_reason": f"단기 변동성 과도 | {reason}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        if actual_x_score <= 35 and status in ["LONG_ENTRY", "LONG_READY", "WAIT", "SKIP"]:
            if left_score >= 3 and left["pressure"] < 1.0 and left["trend_5m"] >= -0.5:
                start_x, end_x = self._long_range(actual_x_score, left_score, left["pressure"])
                return {
                    "jarvis_status": "LONG",
                    "jarvis_reason": f"LONG 보정 승인 | {reason}",
                    "jarvis_start": start_x,
                    "jarvis_end": end_x
                }

        if actual_x_score >= 65 and status in ["SHORT_ENTRY", "SHORT_READY", "WAIT", "SKIP"]:
            if right_score >= 3 and left["pressure"] > 1.0 and left["trend_5m"] <= 0.5:
                start_x, end_x = self._short_range(actual_x_score, right_score, left["pressure"])
                return {
                    "jarvis_status": "SHORT",
                    "jarvis_reason": f"SHORT 보정 승인 | {reason}",
                    "jarvis_start": start_x,
                    "jarvis_end": end_x
                }

        if actual_x_score <= 35:
            return {
                "jarvis_status": "WAIT",
                "jarvis_reason": f"LONG 후보지만 보수적 대기 | {reason}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        if actual_x_score >= 65:
            return {
                "jarvis_status": "WAIT",
                "jarvis_reason": f"SHORT 후보지만 보수적 대기 | {reason}",
                "jarvis_start": "-",
                "jarvis_end": "-"
            }

        return {
            "jarvis_status": "SKIP",
            "jarvis_reason": f"중립 구간 | {reason}",
            "jarvis_start": "-",
            "jarvis_end": "-"
        }
