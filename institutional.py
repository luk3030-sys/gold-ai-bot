from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return default if np.isnan(x) else x
    except (TypeError, ValueError):
        return default


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(float(value), digits)


def confirmed_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """Return confirmed swing highs/lows; the last `right` candles cannot be pivots yet."""
    highs: List[Dict[str, Any]] = []
    lows: List[Dict[str, Any]] = []
    if len(df) < left + right + 3:
        return {"highs": highs, "lows": lows}

    for i in range(left, len(df) - right):
        high = float(df.iloc[i].high)
        low = float(df.iloc[i].low)
        left_highs = df.iloc[i - left:i].high
        right_highs = df.iloc[i + 1:i + right + 1].high
        left_lows = df.iloc[i - left:i].low
        right_lows = df.iloc[i + 1:i + right + 1].low
        if high > float(left_highs.max()) and high >= float(right_highs.max()):
            highs.append({"index": i, "time": str(df.iloc[i].datetime), "price": high})
        if low < float(left_lows.min()) and low <= float(right_lows.min()):
            lows.append({"index": i, "time": str(df.iloc[i].datetime), "price": low})
    return {"highs": highs, "lows": lows}


def _structure_bias(swings: Dict[str, List[Dict[str, Any]]]) -> str:
    highs = swings["highs"]
    lows = swings["lows"]
    if len(highs) < 2 or len(lows) < 2:
        return "UNKNOWN"
    hh = highs[-1]["price"] > highs[-2]["price"]
    hl = lows[-1]["price"] > lows[-2]["price"]
    lh = highs[-1]["price"] < highs[-2]["price"]
    ll = lows[-1]["price"] < lows[-2]["price"]
    if hh and hl:
        return "BULLISH"
    if lh and ll:
        return "BEARISH"
    return "MIXED"


def market_structure(df: pd.DataFrame, left: int = 2, right: int = 2) -> Dict[str, Any]:
    swings = confirmed_swings(df, left, right)
    bias = _structure_bias(swings)
    close = float(df.iloc[-1].close)
    prev_close = float(df.iloc[-2].close)
    last_high = swings["highs"][-1] if swings["highs"] else None
    last_low = swings["lows"][-1] if swings["lows"] else None

    event = "NONE"
    event_level = None
    if last_high and close > last_high["price"] and prev_close <= last_high["price"]:
        event = "CHOCH_UP" if bias == "BEARISH" else "BOS_UP"
        event_level = last_high["price"]
    elif last_low and close < last_low["price"] and prev_close >= last_low["price"]:
        event = "CHOCH_DOWN" if bias == "BULLISH" else "BOS_DOWN"
        event_level = last_low["price"]

    return {
        "bias": bias,
        "event": event,
        "event_level": _round(event_level),
        "last_swing_high": _round(last_high["price"] if last_high else None),
        "last_swing_low": _round(last_low["price"] if last_low else None),
        "swing_high_time": last_high["time"] if last_high else None,
        "swing_low_time": last_low["time"] if last_low else None,
        "swing_high_count": len(swings["highs"]),
        "swing_low_count": len(swings["lows"]),
    }


def liquidity_sweep(df: pd.DataFrame, lookback: int = 50, left: int = 2, right: int = 2) -> Dict[str, Any]:
    sub = df.iloc[-lookback:].reset_index(drop=True) if len(df) > lookback else df.reset_index(drop=True)
    swings = confirmed_swings(sub, left, right)
    cur = sub.iloc[-1]
    result = {"type": "NONE", "level": None, "strength": 0}

    prior_highs = [s for s in swings["highs"] if s["index"] < len(sub) - 1]
    prior_lows = [s for s in swings["lows"] if s["index"] < len(sub) - 1]

    if prior_highs:
        level = prior_highs[-1]["price"]
        if float(cur.high) > level and float(cur.close) < level:
            wick = float(cur.high) - max(float(cur.open), float(cur.close))
            body = max(abs(float(cur.close) - float(cur.open)), 1e-9)
            result = {"type": "BUY_SIDE_SWEEP", "level": _round(level), "strength": min(3, int(wick / body) + 1)}
    if prior_lows:
        level = prior_lows[-1]["price"]
        if float(cur.low) < level and float(cur.close) > level:
            wick = min(float(cur.open), float(cur.close)) - float(cur.low)
            body = max(abs(float(cur.close) - float(cur.open)), 1e-9)
            candidate = {"type": "SELL_SIDE_SWEEP", "level": _round(level), "strength": min(3, int(wick / body) + 1)}
            if candidate["strength"] >= result["strength"]:
                result = candidate
    return result


def fair_value_gaps(df: pd.DataFrame, lookback: int = 80) -> Dict[str, Any]:
    """Find latest unfilled 3-candle imbalance using a standard ICT-style approximation."""
    start = max(2, len(df) - lookback)
    latest_bull = None
    latest_bear = None
    close = float(df.iloc[-1].close)

    for i in range(start, len(df)):
        a = df.iloc[i - 2]
        c = df.iloc[i]
        if float(c.low) > float(a.high):
            zone = (float(a.high), float(c.low))
            # Keep if price has not fully traded through the lower boundary after formation.
            future_low = float(df.iloc[i:].low.min())
            if future_low > zone[0]:
                latest_bull = {"type": "BULLISH_FVG", "low": zone[0], "high": zone[1], "index": i, "time": str(c.datetime)}
        if float(c.high) < float(a.low):
            zone = (float(c.high), float(a.low))
            future_high = float(df.iloc[i:].high.max())
            if future_high < zone[1]:
                latest_bear = {"type": "BEARISH_FVG", "low": zone[0], "high": zone[1], "index": i, "time": str(c.datetime)}

    active = []
    for item in (latest_bull, latest_bear):
        if item:
            active.append({
                **item,
                "low": _round(item["low"]),
                "high": _round(item["high"]),
                "distance": _round(min(abs(close - item["low"]), abs(close - item["high"]))),
                "price_inside": item["low"] <= close <= item["high"],
            })
    active.sort(key=lambda x: x.get("distance") if x.get("distance") is not None else 1e18)
    return {"active": active, "nearest": active[0] if active else None}


def displacement_and_order_block(df: pd.DataFrame, atr_col: str = "atr14", atr_mult: float = 1.25, search_back: int = 10) -> Dict[str, Any]:
    if len(df) < search_back + 3 or atr_col not in df.columns:
        return {"displacement": "NONE", "order_block": None}

    cur = df.iloc[-1]
    body = abs(float(cur.close) - float(cur.open))
    atr = max(_f(cur.get(atr_col), 0.0), 1e-9)
    direction = "BULLISH" if float(cur.close) > float(cur.open) else "BEARISH"
    if body < atr_mult * atr:
        return {"displacement": "NONE", "order_block": None, "body_atr": round(body / atr, 2)}

    ob = None
    for j in range(len(df) - 2, max(-1, len(df) - 2 - search_back), -1):
        candle = df.iloc[j]
        candle_bull = float(candle.close) > float(candle.open)
        if (direction == "BULLISH" and not candle_bull) or (direction == "BEARISH" and candle_bull):
            ob = {
                "type": "BULLISH_OB" if direction == "BULLISH" else "BEARISH_OB",
                "low": _round(float(candle.low)),
                "high": _round(float(candle.high)),
                "time": str(candle.datetime),
            }
            break
    return {"displacement": direction, "order_block": ob, "body_atr": round(body / atr, 2)}


def premium_discount(df: pd.DataFrame, lookback: int = 80) -> Dict[str, Any]:
    sub = df.iloc[-lookback:] if len(df) > lookback else df
    low = float(sub.low.min())
    high = float(sub.high.max())
    midpoint = (low + high) / 2
    price = float(df.iloc[-1].close)
    zone = "PREMIUM" if price > midpoint else "DISCOUNT" if price < midpoint else "EQUILIBRIUM"
    position = 50.0 if high <= low else 100 * (price - low) / (high - low)
    return {
        "range_low": _round(low),
        "range_high": _round(high),
        "equilibrium": _round(midpoint),
        "zone": zone,
        "position_pct": round(position, 1),
    }


def institutional_context(df: pd.DataFrame, *, timeframe: str = "H1") -> Dict[str, Any]:
    structure = market_structure(df)
    sweep = liquidity_sweep(df)
    fvg = fair_value_gaps(df)
    disp = displacement_and_order_block(df)
    pd_zone = premium_discount(df)

    buy_score = 0
    sell_score = 0
    buy_reasons: List[str] = []
    sell_reasons: List[str] = []

    event = structure["event"]
    if event == "BOS_UP":
        buy_score += 12; buy_reasons.append(f"{timeframe} BOS w górę")
    elif event == "CHOCH_UP":
        buy_score += 16; buy_reasons.append(f"{timeframe} CHOCH w górę")
    elif event == "BOS_DOWN":
        sell_score += 12; sell_reasons.append(f"{timeframe} BOS w dół")
    elif event == "CHOCH_DOWN":
        sell_score += 16; sell_reasons.append(f"{timeframe} CHOCH w dół")

    if structure["bias"] == "BULLISH":
        buy_score += 5; buy_reasons.append(f"{timeframe} struktura HH/HL")
    elif structure["bias"] == "BEARISH":
        sell_score += 5; sell_reasons.append(f"{timeframe} struktura LH/LL")

    if sweep["type"] == "SELL_SIDE_SWEEP":
        pts = 8 + 2 * int(sweep.get("strength", 1))
        buy_score += pts; buy_reasons.append(f"{timeframe} sweep płynności pod dołkiem")
    elif sweep["type"] == "BUY_SIDE_SWEEP":
        pts = 8 + 2 * int(sweep.get("strength", 1))
        sell_score += pts; sell_reasons.append(f"{timeframe} sweep płynności nad szczytem")

    nearest = fvg.get("nearest")
    if nearest and nearest.get("price_inside"):
        if nearest["type"] == "BULLISH_FVG":
            buy_score += 7; buy_reasons.append(f"{timeframe} cena w bullish FVG")
        elif nearest["type"] == "BEARISH_FVG":
            sell_score += 7; sell_reasons.append(f"{timeframe} cena w bearish FVG")

    if disp["displacement"] == "BULLISH":
        buy_score += 7; buy_reasons.append(f"{timeframe} bullish displacement {disp.get('body_atr')} ATR")
    elif disp["displacement"] == "BEARISH":
        sell_score += 7; sell_reasons.append(f"{timeframe} bearish displacement {disp.get('body_atr')} ATR")

    if pd_zone["zone"] == "DISCOUNT":
        buy_score += 4; buy_reasons.append(f"{timeframe} cena w discount range")
    elif pd_zone["zone"] == "PREMIUM":
        sell_score += 4; sell_reasons.append(f"{timeframe} cena w premium range")

    return {
        "timeframe": timeframe,
        "buy_score": int(buy_score),
        "sell_score": int(sell_score),
        "buy_reasons": buy_reasons,
        "sell_reasons": sell_reasons,
        "structure": structure,
        "liquidity_sweep": sweep,
        "fvg": fvg,
        "displacement": disp,
        "premium_discount": pd_zone,
    }
