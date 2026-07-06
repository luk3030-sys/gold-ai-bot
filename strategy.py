import math
import os
from typing import Dict, Tuple

from config import env_bool, env_float, env_int
from data_provider import fetch_dxy_context, fetch_ohlc
from indicators import enrich
from patterns import candle_patterns, interpret_patterns

INTERVALS = {"m15": "15min", "h1": "1h", "h4": "4h", "d1": "1day"}


def _num(value, default=0.0):
    try:
        x = float(value)
        return default if math.isnan(x) else x
    except (TypeError, ValueError):
        return default


def roundp(x):
    return None if x is None else round(float(x), 2)


def rr(entry, sl, tp):
    if None in (entry, sl, tp):
        return None
    risk = abs(entry - sl)
    return None if risk <= 0 else round(abs(tp - entry) / risk, 2)


def trend(row) -> str:
    if row.close > row.ema50 > row.ema200:
        return "UP"
    if row.close < row.ema50 < row.ema200:
        return "DOWN"
    return "NEUTRAL"


def levels(df, lookback=40) -> Tuple[float, float]:
    # Exclude the current signal candle so a breakout is not its own resistance/support.
    sub = df.iloc[-(lookback + 1):-1] if len(df) > lookback + 1 else df.iloc[:-1]
    if sub.empty:
        sub = df
    return float(sub.low.min()), float(sub.high.max())


def detect_regime(dfs, tr: Dict[str, str]) -> str:
    h1 = dfs["h1"].iloc[-1]
    h4 = dfs["h4"].iloc[-1]
    adx_h4 = _num(h4.adx14)
    atr_pct = _num(h1.atr_pct, 50)
    if tr["h4"] == tr["d1"] == "UP" and adx_h4 >= 25:
        return "STRONG_UP"
    if tr["h4"] == tr["d1"] == "DOWN" and adx_h4 >= 25:
        return "STRONG_DOWN"
    if tr["h4"] == "UP" and adx_h4 >= 18:
        return "TREND_UP"
    if tr["h4"] == "DOWN" and adx_h4 >= 18:
        return "TREND_DOWN"
    if atr_pct >= 80:
        return "HIGH_VOLATILITY_RANGE"
    return "RANGE"


def detect_setup(dfs, tr: Dict[str, str], support: float, resistance: float, regime: str) -> str:
    h1 = dfs["h1"]
    cur = h1.iloc[-1]
    prev = h1.iloc[-2]
    atr = max(_num(cur.atr14), 1e-9)
    near_ema = min(abs(cur.close - cur.ema20), abs(cur.close - cur.ema50)) <= 0.6 * atr

    if tr["d1"] == tr["h4"] and tr["h4"] in {"UP", "DOWN"} and (tr["h1"] == "NEUTRAL" or near_ema):
        return "TREND_PULLBACK"
    if cur.close > resistance and prev.close <= resistance:
        return "BREAKOUT_UP"
    if cur.close < support and prev.close >= support:
        return "BREAKOUT_DOWN"
    if tr["d1"] == "DOWN" and tr["h1"] == "UP":
        return "REVERSAL_ATTEMPT_UP"
    if tr["d1"] == "UP" and tr["h1"] == "DOWN":
        return "REVERSAL_ATTEMPT_DOWN"
    return "NO_CLEAR_SETUP"


def analyze() -> dict:
    symbol = os.getenv("SYMBOL", "XAU/USD")
    min_score = env_int("MIN_SCORE", 80)
    min_rr = env_float("MIN_RR", 2.0)
    macro_block = env_bool("MACRO_BLOCK", False)

    dfs = {key: enrich(fetch_ohlc(symbol, interval, 260, closed_only=True)) for key, interval in INTERVALS.items()}
    if any(len(df) < 205 for df in dfs.values()):
        raise RuntimeError("Za mało danych do stabilnego EMA200")

    last = {key: df.iloc[-1] for key, df in dfs.items()}
    tr = {key: trend(row) for key, row in last.items()}
    price = float(last["h1"].close)
    atr_h1 = max(_num(last["h1"].atr14), max(price * 0.003, 1.0))
    support, resistance = levels(dfs["h1"], env_int("LEVEL_LOOKBACK", 40))
    patterns = candle_patterns(dfs["h1"])
    regime = detect_regime(dfs, tr)
    setup_type = detect_setup(dfs, tr, support, resistance, regime)

    buy_score = sell_score = 0
    buy_reasons, sell_reasons = [], []

    weights = {
        "d1": env_int("WEIGHT_D1", 15),
        "h4": env_int("WEIGHT_H4", 20),
        "h1": env_int("WEIGHT_H1", 20),
        "m15": env_int("WEIGHT_M15", 5),
    }
    for tf in ["d1", "h4", "h1"]:
        if tr[tf] == "UP":
            buy_score += weights[tf]; buy_reasons.append(f"{tf.upper()} trend wzrostowy")
        elif tr[tf] == "DOWN":
            sell_score += weights[tf]; sell_reasons.append(f"{tf.upper()} trend spadkowy")

    if last["m15"].close > last["m15"].ema20:
        buy_score += weights["m15"]; buy_reasons.append("M15 powyżej EMA20")
    elif last["m15"].close < last["m15"].ema20:
        sell_score += weights["m15"]; sell_reasons.append("M15 poniżej EMA20")

    rsi_h1 = _num(last["h1"].rsi14, 50)
    adx_h1 = _num(last["h1"].adx14)
    adx_h4 = _num(last["h4"].adx14)
    macdh = _num(last["h1"].macd_hist)
    if 45 <= rsi_h1 <= 68:
        buy_score += 10; buy_reasons.append(f"RSI H1 sprzyja BUY: {rsi_h1:.1f}")
    if 32 <= rsi_h1 <= 55:
        sell_score += 10; sell_reasons.append(f"RSI H1 sprzyja SELL: {rsi_h1:.1f}")
    if macdh > 0:
        buy_score += 10; buy_reasons.append("MACD histogram dodatni")
    elif macdh < 0:
        sell_score += 10; sell_reasons.append("MACD histogram ujemny")
    if adx_h1 >= 18:
        buy_score += 5; sell_score += 5

    if "bullish_engulfing" in patterns or "pin_bar_bullish" in patterns:
        buy_score += 10; buy_reasons.append("Price Action wspiera BUY")
    if "bearish_engulfing" in patterns or "pin_bar_bearish" in patterns:
        sell_score += 10; sell_reasons.append("Price Action wspiera SELL")

    if regime == "STRONG_UP":
        buy_score += 10; buy_reasons.append("Reżim: silny trend wzrostowy")
        sell_score -= 5
    elif regime == "STRONG_DOWN":
        sell_score += 10; sell_reasons.append("Reżim: silny trend spadkowy")
        buy_score -= 5
    elif regime == "HIGH_VOLATILITY_RANGE":
        buy_score -= 5; sell_score -= 5

    if setup_type in {"TREND_PULLBACK", "BREAKOUT_UP"} and tr["h4"] == "UP":
        buy_score += 10; buy_reasons.append(f"Setup: {setup_type}")
    if setup_type in {"TREND_PULLBACK", "BREAKOUT_DOWN"} and tr["h4"] == "DOWN":
        sell_score += 10; sell_reasons.append(f"Setup: {setup_type}")

    dxy_ctx = fetch_dxy_context("1h", 220)
    dxy_status = dxy_ctx.get("status", "UNAVAILABLE")
    dxy_symbol_used = dxy_ctx.get("symbol")
    dxy_kind = dxy_ctx.get("kind", "none")
    data_quality_score = 90
    if dxy_ctx.get("available"):
        dxy_df = enrich(dxy_ctx["df"])
        dxy_last = dxy_df.iloc[-1]
        dxy_bullish = dxy_last.close > dxy_last.ema50
        # A proxy is deliberately weighted less than the direct DXY index.
        dxy_weight = env_int("DXY_WEIGHT", 5) if dxy_kind == "direct" else env_int("DXY_PROXY_WEIGHT", 2)
        if dxy_bullish:
            sell_score += dxy_weight
            sell_reasons.append(f"USD filtr {dxy_symbol_used} powyżej EMA50 — wsparcie dla SELL GOLD")
            dxy_status = f"BULLISH_{dxy_kind.upper()}"
        else:
            buy_score += dxy_weight
            buy_reasons.append(f"USD filtr {dxy_symbol_used} poniżej EMA50 — wsparcie dla BUY GOLD")
            dxy_status = f"BEARISH_{dxy_kind.upper()}"
        data_quality_score = 100 if dxy_kind == "direct" else 95
    else:
        penalty = env_int("DXY_MISSING_PENALTY", 5)
        if env_bool("DXY_REQUIRED", False):
            buy_score -= max(penalty, 15); sell_score -= max(penalty, 15)
        else:
            buy_score -= penalty; sell_score -= penalty
        dxy_status = "UNAVAILABLE"
        data_quality_score = 80

    if macro_block:
        buy_score -= 30; sell_score -= 30
        buy_reasons.append("MACRO_BLOCK aktywny")
        sell_reasons.append("MACRO_BLOCK aktywny")

    buy_score = max(0, min(100, int(round(buy_score))))
    sell_score = max(0, min(100, int(round(sell_score))))

    if buy_score > sell_score:
        signal, score, reasons = "BUY", buy_score, buy_reasons
        entry = price
        structural_sl = support
        sl = min(structural_sl, price - 1.3 * atr_h1)
        risk = abs(entry - sl)
        tp1, tp2, tp3 = entry + 2 * risk, entry + 3 * risk, entry + 4 * risk
    elif sell_score > buy_score:
        signal, score, reasons = "SELL", sell_score, sell_reasons
        entry = price
        structural_sl = resistance
        sl = max(structural_sl, price + 1.3 * atr_h1)
        risk = abs(sl - entry)
        tp1, tp2, tp3 = entry - 2 * risk, entry - 3 * risk, entry - 4 * risk
    else:
        signal, score, reasons = "NO TRADE", 0, ["Brak przewagi jednej strony"]
        entry = sl = tp1 = tp2 = tp3 = None

    rr1, rr2, rr3 = rr(entry, sl, tp1), rr(entry, sl, tp2), rr(entry, sl, tp3)
    if signal != "NO TRADE" and (score < min_score or rr2 is None or rr2 < min_rr or macro_block):
        reasons.append(f"Sygnał zablokowany: score={score}/{min_score}, RR2={rr2}/{min_rr}, macro={macro_block}")
        signal = "NO TRADE"

    h1_time = str(dfs["h1"].iloc[-1].datetime)
    return {
        "symbol": symbol,
        "signal": signal,
        "score": score,
        "score_type": "rule_based_not_probability",
        "buy_score": buy_score,
        "sell_score": sell_score,
        "price": roundp(price),
        "setup_type": setup_type,
        "regime": regime,
        "trend_m15": tr["m15"],
        "trend_h1": tr["h1"],
        "trend_h4": tr["h4"],
        "trend_d1": tr["d1"],
        "rsi_h1": round(rsi_h1, 1),
        "adx_h1": roundp(adx_h1),
        "adx_h4": roundp(adx_h4),
        "atr_h1": roundp(atr_h1),
        "support": roundp(support),
        "resistance": roundp(resistance),
        "entry": roundp(entry),
        "sl": roundp(sl),
        "tp1": roundp(tp1),
        "tp2": roundp(tp2),
        "tp3": roundp(tp3),
        "rr_tp1": rr1,
        "rr_tp2": rr2,
        "rr_tp3": rr3,
        "patterns_h1": patterns,
        "pattern_notes": interpret_patterns(patterns),
        "reasons": reasons or ["Brak wystarczającej przewagi"],
        "dxy_status": dxy_status,
        "dxy_symbol_used": dxy_symbol_used,
        "dxy_kind": dxy_kind,
        "data_quality_score": data_quality_score,
        "closed_h1_candle_time": h1_time,
        "watch_plan": [
            f"BUY dopiero po wybiciu i utrzymaniu powyżej {roundp(resistance)}",
            f"SELL dopiero po utracie i retestcie poniżej {roundp(support)}",
            f"Strefa neutralna: {roundp(support)}–{roundp(resistance)}",
        ],
    }
