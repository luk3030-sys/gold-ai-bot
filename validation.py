"""Historical validation engine.

This is deliberately separated from the live engine. It uses H1 bars and resamples
H4/D1 from them, so results are an approximation of live v5 (no M15/DXY filter).
It is intended to detect obviously bad parameter sets, not to promise future returns.
"""
import math
import os
from typing import Dict, List

import numpy as np
import pandas as pd

from config import env_int
from data_provider import fetch_ohlc
from indicators import enrich


def _trend(row):
    if row.close > row.ema50 > row.ema200:
        return "UP"
    if row.close < row.ema50 < row.ema200:
        return "DOWN"
    return "NEUTRAL"


def _resample(df, rule):
    tmp = df.set_index("datetime")
    out = tmp.resample(rule, label="right", closed="right").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna().reset_index()
    return enrich(out)


def _metrics(trades: List[Dict]) -> Dict:
    if not trades:
        return {"trades": 0, "win_rate_pct": None, "expectancy_r": None, "net_r": 0.0, "max_drawdown_r": None}
    rs = [t["r_result"] for t in trades]
    equity = peak = max_dd = 0.0
    for r in rs:
        equity += r; peak = max(peak, equity); max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(rs),
        "win_rate_pct": round(100 * sum(r > 0 for r in rs) / len(rs), 2),
        "expectancy_r": round(sum(rs) / len(rs), 3),
        "net_r": round(sum(rs), 3),
        "max_drawdown_r": round(max_dd, 3),
    }


def run_validation(symbol: str, bars: int = 1500) -> Dict:
    bars = max(500, min(int(bars), 5000))
    min_score = env_int("VALIDATION_MIN_SCORE", env_int("MIN_SCORE", 80))
    max_hold = env_int("VALIDATION_MAX_HOLD_H1_BARS", 72)

    h1 = enrich(fetch_ohlc(symbol, "1h", bars, closed_only=True))
    h4 = _resample(h1[["datetime", "open", "high", "low", "close"]], "4h")
    d1 = _resample(h1[["datetime", "open", "high", "low", "close"]], "1D")

    trades = []
    i = 220
    while i < len(h1) - 2:
        row = h1.iloc[i]
        h4_sub = h4[h4.datetime <= row.datetime]
        d1_sub = d1[d1.datetime <= row.datetime]
        if h4_sub.empty or d1_sub.empty:
            i += 1; continue
        h4r, d1r = h4_sub.iloc[-1], d1_sub.iloc[-1]
        tr_h1, tr_h4, tr_d1 = _trend(row), _trend(h4r), _trend(d1r)
        score_buy = score_sell = 0
        if tr_d1 == "UP": score_buy += 15
        if tr_d1 == "DOWN": score_sell += 15
        if tr_h4 == "UP": score_buy += 20
        if tr_h4 == "DOWN": score_sell += 20
        if tr_h1 == "UP": score_buy += 20
        if tr_h1 == "DOWN": score_sell += 20
        rsi = float(row.rsi14) if not math.isnan(float(row.rsi14)) else 50
        macdh = float(row.macd_hist) if not math.isnan(float(row.macd_hist)) else 0
        adx = float(row.adx14) if not math.isnan(float(row.adx14)) else 0
        if 45 <= rsi <= 68: score_buy += 10
        if 32 <= rsi <= 55: score_sell += 10
        if macdh > 0: score_buy += 10
        if macdh < 0: score_sell += 10
        if adx >= 18: score_buy += 5; score_sell += 5

        side = None
        score = max(score_buy, score_sell)
        if score >= min_score and score_buy > score_sell:
            side = "BUY"
        elif score >= min_score and score_sell > score_buy:
            side = "SELL"
        if not side:
            i += 1; continue

        atr = float(row.atr14) if not math.isnan(float(row.atr14)) else float(row.close) * 0.004
        sub = h1.iloc[max(0, i - 40):i]
        support, resistance = float(sub.low.min()), float(sub.high.max())
        entry = float(row.close)
        if side == "BUY":
            sl = min(support, entry - 1.3 * atr); target = entry + 3 * abs(entry - sl)
        else:
            sl = max(resistance, entry + 1.3 * atr); target = entry - 3 * abs(sl - entry)

        outcome = None
        exit_index = min(i + max_hold, len(h1) - 1)
        for j in range(i + 1, exit_index + 1):
            bar = h1.iloc[j]
            if side == "BUY":
                hit_sl, hit_tp = bar.low <= sl, bar.high >= target
            else:
                hit_sl, hit_tp = bar.high >= sl, bar.low <= target
            if hit_sl and hit_tp:
                outcome = -1.0  # conservative same-bar policy
                exit_index = j; break
            if hit_sl:
                outcome = -1.0; exit_index = j; break
            if hit_tp:
                outcome = 3.0; exit_index = j; break
        if outcome is None:
            outcome = 0.0

        trades.append({
            "entry_time": str(row.datetime), "side": side, "score": score,
            "entry": round(entry, 2), "sl": round(sl, 2), "target": round(target, 2),
            "r_result": outcome,
        })
        i = max(i + 1, exit_index + 1)  # no overlapping validation trades

    split_time = h1.iloc[int(len(h1) * 0.7)].datetime
    holdout = [t for t in trades if pd.Timestamp(t["entry_time"]) >= split_time]
    in_sample = [t for t in trades if pd.Timestamp(t["entry_time"]) < split_time]
    return {
        "symbol": symbol,
        "bars": len(h1),
        "method": "H1 walk-forward-like simulation; H4/D1 resampled; no M15/DXY; conservative same-bar policy",
        "limitations": [
            "To nie jest identyczny silnik live v5.",
            "Nie uwzględnia spreadu, poślizgu ani opóźnienia egzekucji.",
            "Wyniki historyczne nie gwarantują przyszłych rezultatów.",
        ],
        "all": _metrics(trades),
        "in_sample_first_70pct": _metrics(in_sample),
        "holdout_last_30pct": _metrics(holdout),
        "sample_trades": trades[-20:],
    }
