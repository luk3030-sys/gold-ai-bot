from __future__ import annotations

import hashlib
import os
from typing import Any, Dict

import pandas as pd

from config import env_float, env_int
from data_provider import fetch_ohlc
from db import get_metadata, set_metadata
from indicators import enrich


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def evaluate_move_frame(df: pd.DataFrame) -> Dict[str, Any]:
    """Evaluate newest (possibly forming) candle against ATR from prior closed candles."""
    if len(df) < 25:
        return {"triggered": False, "reason": "insufficient_data"}

    work = enrich(df.copy())
    cur = work.iloc[-1]
    prev = work.iloc[-2]
    atr_ref = _safe_float(prev.atr14)
    if atr_ref <= 0:
        return {"triggered": False, "reason": "invalid_atr"}

    body = abs(float(cur.close) - float(cur.open))
    rng = max(float(cur.high) - float(cur.low), 1e-9)
    move = float(cur.close) - float(cur.open)
    direction = "UP" if move > 0 else "DOWN" if move < 0 else "FLAT"
    body_atr = body / atr_ref
    range_atr = rng / atr_ref
    body_ratio = body / rng

    atr_threshold = env_float("MOVE_ALERT_ATR_MULT", 0.9)
    range_threshold = env_float("MOVE_ALERT_RANGE_ATR_MULT", 1.2)
    body_ratio_min = env_float("MOVE_ALERT_BODY_RATIO_MIN", 0.55)
    min_abs_move = env_float("MOVE_ALERT_MIN_ABS_MOVE", 0.0)

    triggered = (
        direction in {"UP", "DOWN"}
        and abs(move) >= min_abs_move
        and body_ratio >= body_ratio_min
        and (body_atr >= atr_threshold or range_atr >= range_threshold)
    )
    severity = "EXTREME" if max(body_atr, range_atr) >= 2.0 else "HIGH" if max(body_atr, range_atr) >= 1.4 else "ELEVATED"
    return {
        "triggered": bool(triggered),
        "direction": direction,
        "severity": severity,
        "candle_time": str(cur.datetime),
        "open": round(float(cur.open), 2),
        "high": round(float(cur.high), 2),
        "low": round(float(cur.low), 2),
        "close": round(float(cur.close), 2),
        "move_points": round(move, 2),
        "body_atr": round(body_atr, 2),
        "range_atr": round(range_atr, 2),
        "body_ratio": round(body_ratio, 2),
        "atr_reference": round(atr_ref, 2),
    }


def detect_large_move(symbol: str | None = None) -> Dict[str, Any]:
    symbol = symbol or os.getenv("SYMBOL", "XAU/USD")
    interval = os.getenv("MOVE_ALERT_INTERVAL", "15min")
    df = fetch_ohlc(symbol, interval, env_int("MOVE_ALERT_OUTPUTSIZE", 120), closed_only=False)
    result = evaluate_move_frame(df)
    result.update({"symbol": symbol, "interval": interval})
    if result.get("triggered"):
        raw = f"{symbol}|{interval}|{result.get('candle_time')}|{result.get('direction')}|{result.get('severity')}"
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        key = "move_alert_last_fingerprint"
        last = get_metadata(key)
        result["fingerprint"] = fingerprint
        result["is_new"] = fingerprint != last
    else:
        result["is_new"] = False
    return result


def mark_move_alert_sent(result: Dict[str, Any]) -> None:
    fingerprint = result.get("fingerprint")
    if fingerprint:
        set_metadata("move_alert_last_fingerprint", str(fingerprint))
