import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

APP_VERSION = "6.2-institutional-smart-money-any-large-candle-move"
SYMBOL = os.getenv("SYMBOL", "XAU/USD")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "true").lower() == "true"
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
CLOSED_CANDLES_ONLY = os.getenv("CLOSED_CANDLES_ONLY", "true").lower() == "true"
RUN_INTERVAL_MINUTES = int(os.getenv("RUN_INTERVAL_MINUTES", "15"))
MIN_SCORE_TO_ALERT = int(os.getenv("MIN_SCORE_TO_ALERT", "75"))
MAX_SPREAD_POINTS = float(os.getenv("MAX_SPREAD_POINTS", "2.0"))
LARGE_CANDLE_ALERT_ENABLED = os.getenv("LARGE_CANDLE_ALERT_ENABLED", "true").lower() == "true"
LARGE_CANDLE_INTERVALS = [x.strip() for x in os.getenv("LARGE_CANDLE_INTERVALS", "15min,1h").split(",") if x.strip()]
LARGE_CANDLE_ATR_MULTIPLIER = float(os.getenv("LARGE_CANDLE_ATR_MULTIPLIER", "1.2"))
LARGE_CANDLE_MIN_POINTS = float(os.getenv("LARGE_CANDLE_MIN_POINTS", "20"))
LARGE_CANDLE_BODY_RATIO = float(os.getenv("LARGE_CANDLE_BODY_RATIO", "0.55"))
LARGE_CANDLE_RANGE_ATR_MULTIPLIER = float(os.getenv("LARGE_CANDLE_RANGE_ATR_MULTIPLIER", "1.5"))
LARGE_CANDLE_MODE = os.getenv("LARGE_CANDLE_MODE", "ANY").upper()  # ANY, BODY, RANGE

app = Flask(__name__)
LAST_SIGNAL: Dict[str, Any] = {"status": "starting", "version": APP_VERSION}
LAST_ALERT_KEY: Optional[str] = None
LAST_LARGE_CANDLE_ALERT_KEY: Optional[str] = None


def fetch_ohlc(interval: str, outputsize: int = 300) -> pd.DataFrame:
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "values" not in data:
        raise RuntimeError(f"Bad TwelveData response: {data}")
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().sort_values("datetime").reset_index(drop=True)
    if CLOSED_CANDLES_ONLY and len(df) > 2:
        df = df.iloc[:-1].copy()
    return df


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/period, adjust=False).mean()
    ma_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema20"] = ema(out["close"], 20)
    out["ema50"] = ema(out["close"], 50)
    out["ema200"] = ema(out["close"], 200)
    out["rsi14"] = rsi(out["close"], 14)
    out["atr14"] = atr(out, 14)
    return out


def swing_points(df: pd.DataFrame, left: int = 2, right: int = 2) -> Dict[str, List[Dict[str, float]]]:
    highs, lows = [], []
    for i in range(left, len(df) - right):
        window = df.iloc[i-left:i+right+1]
        row = df.iloc[i]
        if row.high == window.high.max():
            highs.append({"i": i, "price": float(row.high)})
        if row.low == window.low.min():
            lows.append({"i": i, "price": float(row.low)})
    return {"highs": highs[-10:], "lows": lows[-10:]}


def market_structure(df: pd.DataFrame) -> Dict[str, Any]:
    sp = swing_points(df)
    highs, lows = sp["highs"], sp["lows"]
    close = float(df.close.iloc[-1])
    direction = "NEUTRAL"
    bos = None
    choch = None
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1]["price"] > highs[-2]["price"]
        hl = lows[-1]["price"] > lows[-2]["price"]
        lh = highs[-1]["price"] < highs[-2]["price"]
        ll = lows[-1]["price"] < lows[-2]["price"]
        if hh and hl:
            direction = "UP"
        elif lh and ll:
            direction = "DOWN"
        last_high = highs[-1]["price"]
        last_low = lows[-1]["price"]
        if close > last_high:
            bos = "BULLISH_BOS"
        elif close < last_low:
            bos = "BEARISH_BOS"
        if direction == "DOWN" and close > last_high:
            choch = "BULLISH_CHOCH"
        elif direction == "UP" and close < last_low:
            choch = "BEARISH_CHOCH"
    return {"direction": direction, "bos": bos, "choch": choch, "swings": sp}


def liquidity_sweep(df: pd.DataFrame) -> Dict[str, Any]:
    sp = swing_points(df)
    last = df.iloc[-1]
    result = {"bullish_sweep": False, "bearish_sweep": False, "level": None}
    if sp["lows"]:
        prev_low = sp["lows"][-1]["price"]
        if last.low < prev_low and last.close > prev_low:
            result = {"bullish_sweep": True, "bearish_sweep": False, "level": prev_low}
    if sp["highs"]:
        prev_high = sp["highs"][-1]["price"]
        if last.high > prev_high and last.close < prev_high:
            result = {"bullish_sweep": False, "bearish_sweep": True, "level": prev_high}
    return result


def fair_value_gap(df: pd.DataFrame) -> Dict[str, Any]:
    gaps = []
    for i in range(2, len(df)):
        c1 = df.iloc[i-2]
        c3 = df.iloc[i]
        if c1.high < c3.low:
            gaps.append({"type": "BULLISH_FVG", "low": float(c1.high), "high": float(c3.low), "i": i})
        if c1.low > c3.high:
            gaps.append({"type": "BEARISH_FVG", "low": float(c3.high), "high": float(c1.low), "i": i})
    return {"latest": gaps[-1] if gaps else None, "count": len(gaps)}


def order_block(df: pd.DataFrame) -> Dict[str, Any]:
    a = atr(df, 14)
    latest = None
    for i in range(5, len(df)):
        prev = df.iloc[i-1]
        cur = df.iloc[i]
        impulse = abs(cur.close - cur.open) > float(a.iloc[i]) * 1.2
        if not impulse:
            continue
        if cur.close > cur.open and prev.close < prev.open:
            latest = {"type": "BULLISH_OB", "low": float(prev.low), "high": float(prev.high), "i": i-1}
        elif cur.close < cur.open and prev.close > prev.open:
            latest = {"type": "BEARISH_OB", "low": float(prev.low), "high": float(prev.high), "i": i-1}
    return {"latest": latest}


def trend(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    if last.close > last.ema20 > last.ema50:
        return "UP"
    if last.close < last.ema20 < last.ema50:
        return "DOWN"
    return "NEUTRAL"



def detect_large_candle(df: pd.DataFrame, interval: str) -> Dict[str, Any]:
    """Detects a large closed candle move.

    v6.2 supports ANY large movement:
    - BODY impulse: strong directional candle body.
    - RANGE expansion: large high-low candle range, including long wick / news spike.

    This means the bot can alert even when the candle made a big total move,
    not only when it closed strongly up or down.
    """
    if len(df) < 25:
        return {"alert": False, "reason": "not_enough_data", "interval": interval}

    enriched = add_indicators(df)
    last = enriched.iloc[-1]
    body = abs(float(last.close) - float(last.open))
    full_range = max(float(last.high) - float(last.low), 0.0001)
    atr_value = float(last.atr14) if pd.notna(last.atr14) else 0.0
    direction = "UP" if last.close > last.open else "DOWN" if last.close < last.open else "NEUTRAL"
    body_ratio = body / full_range

    body_impulse = (
        direction != "NEUTRAL"
        and body >= LARGE_CANDLE_MIN_POINTS
        and atr_value > 0
        and body >= atr_value * LARGE_CANDLE_ATR_MULTIPLIER
        and body_ratio >= LARGE_CANDLE_BODY_RATIO
    )

    range_expansion = (
        full_range >= LARGE_CANDLE_MIN_POINTS
        and atr_value > 0
        and full_range >= atr_value * LARGE_CANDLE_RANGE_ATR_MULTIPLIER
    )

    mode = LARGE_CANDLE_MODE
    if mode == "BODY":
        is_large = body_impulse
        alert_type = "BODY_IMPULSE" if body_impulse else "NONE"
    elif mode == "RANGE":
        is_large = range_expansion
        alert_type = "RANGE_EXPANSION" if range_expansion else "NONE"
    else:
        is_large = body_impulse or range_expansion
        if body_impulse and range_expansion:
            alert_type = "BODY_AND_RANGE"
        elif body_impulse:
            alert_type = "BODY_IMPULSE"
        elif range_expansion:
            alert_type = "RANGE_EXPANSION"
        else:
            alert_type = "NONE"

    return {
        "alert": bool(is_large),
        "alert_type": alert_type,
        "mode": mode,
        "interval": interval,
        "datetime": str(last.datetime),
        "direction": direction,
        "open": round(float(last.open), 2),
        "high": round(float(last.high), 2),
        "low": round(float(last.low), 2),
        "close": round(float(last.close), 2),
        "body_points": round(body, 2),
        "range_points": round(full_range, 2),
        "atr14": round(atr_value, 2),
        "body_to_atr": round(body / atr_value, 2) if atr_value > 0 else None,
        "range_to_atr": round(full_range / atr_value, 2) if atr_value > 0 else None,
        "body_ratio": round(body_ratio, 2),
    }


def build_large_candle_alerts() -> List[Dict[str, Any]]:
    if not LARGE_CANDLE_ALERT_ENABLED:
        return []
    alerts = []
    for interval in LARGE_CANDLE_INTERVALS:
        df = fetch_ohlc(interval, outputsize=120)
        event = detect_large_candle(df, interval)
        if event.get("alert"):
            alerts.append(event)
    return alerts


def format_large_candle_alert(event: Dict[str, Any]) -> str:
    emoji = "🟢" if event["direction"] == "UP" else "🔴"
    direction_pl = "mocno do góry" if event["direction"] == "UP" else "mocno w dół"
    return (
        f"{emoji} GOLD AI BOT v6.2 — DUŻY RUCH ŚWIECY\n"
        f"Symbol: {SYMBOL}\n"
        f"Interwał: {event['interval']}\n"
        f"Ruch: {direction_pl}\n"
        f"Typ alertu: {event.get('alert_type')} | Tryb: {event.get('mode')}\n"
        f"Czas świecy: {event['datetime']}\n\n"
        f"Open: {event['open']} | Close: {event['close']}\n"
        f"High: {event['high']} | Low: {event['low']}\n"
        f"Korpus: {event['body_points']} pkt | Zakres: {event['range_points']} pkt\n"
        f"ATR14: {event['atr14']} | Korpus/ATR: {event['body_to_atr']} | Zakres/ATR: {event.get('range_to_atr')}\n\n"
        f"Uwaga: to alert zmienności, nie samodzielny sygnał wejścia. Sprawdź H1/H4 i poziomy płynności przed decyzją."
    )

def build_signal() -> Dict[str, Any]:
    frames = {tf: add_indicators(fetch_ohlc(tf)) for tf in ["15min", "1h", "4h", "1day"]}
    m15, h1, h4, d1 = frames["15min"], frames["1h"], frames["4h"], frames["1day"]
    price = float(h1.close.iloc[-1])
    atr_h1 = float(h1.atr14.iloc[-1])
    trends = {"M15": trend(m15), "H1": trend(h1), "H4": trend(h4), "D1": trend(d1)}
    ms_h1, ms_h4 = market_structure(h1), market_structure(h4)
    sweep = liquidity_sweep(h1)
    fvg = fair_value_gap(h1)
    ob = order_block(h1)

    score_sell = 0
    score_buy = 0
    reasons = []

    for tf in ["H4", "D1"]:
        if trends[tf] == "DOWN":
            score_sell += 15; reasons.append(f"{tf} trend DOWN")
        if trends[tf] == "UP":
            score_buy += 15; reasons.append(f"{tf} trend UP")
    if trends["H1"] == "DOWN": score_sell += 10
    if trends["H1"] == "UP": score_buy += 10
    if ms_h1["bos"] == "BEARISH_BOS": score_sell += 15; reasons.append("H1 bearish BOS")
    if ms_h1["bos"] == "BULLISH_BOS": score_buy += 15; reasons.append("H1 bullish BOS")
    if ms_h4["direction"] == "DOWN": score_sell += 10
    if ms_h4["direction"] == "UP": score_buy += 10
    if sweep["bearish_sweep"]: score_sell += 15; reasons.append("liquidity sweep above highs")
    if sweep["bullish_sweep"]: score_buy += 15; reasons.append("liquidity sweep below lows")
    if fvg["latest"] and fvg["latest"]["type"] == "BEARISH_FVG": score_sell += 10
    if fvg["latest"] and fvg["latest"]["type"] == "BULLISH_FVG": score_buy += 10
    if ob["latest"] and ob["latest"]["type"] == "BEARISH_OB": score_sell += 10
    if ob["latest"] and ob["latest"]["type"] == "BULLISH_OB": score_buy += 10

    if score_sell >= score_buy + 15 and score_sell >= MIN_SCORE_TO_ALERT:
        side = "SELL"; score = score_sell
        sl = max(price + atr_h1 * 1.4, price + 18)
        tp1 = price - (sl - price) * 1.5
        tp2 = price - (sl - price) * 2.5
        tp3 = price - (sl - price) * 3.5
    elif score_buy >= score_sell + 15 and score_buy >= MIN_SCORE_TO_ALERT:
        side = "BUY"; score = score_buy
        sl = min(price - atr_h1 * 1.4, price - 18)
        tp1 = price + (price - sl) * 1.5
        tp2 = price + (price - sl) * 2.5
        tp3 = price + (price - sl) * 3.5
    else:
        side = "NO_TRADE"; score = max(score_buy, score_sell)
        sl = tp1 = tp2 = tp3 = None

    return {
        "version": APP_VERSION,
        "status": "ok",
        "symbol": SYMBOL,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "signal": side,
        "score": int(score),
        "price": round(price, 2),
        "trend": trends,
        "institutional": {
            "market_structure_h1": ms_h1,
            "market_structure_h4": ms_h4,
            "liquidity_sweep_h1": sweep,
            "fair_value_gap_h1": fvg,
            "order_block_h1": ob,
        },
        "risk_plan": {
            "entry": round(price, 2),
            "sl": round(sl, 2) if sl else None,
            "tp1": round(tp1, 2) if tp1 else None,
            "tp2": round(tp2, 2) if tp2 else None,
            "tp3": round(tp3, 2) if tp3 else None,
            "risk_note": "Risk max 1-2% capital. Signal is rule score, not probability.",
        },
        "reasons": reasons,
        "closed_candles": CLOSED_CANDLES_ONLY,
    }


def format_signal(s: Dict[str, Any]) -> str:
    rp = s["risk_plan"]
    inst = s["institutional"]
    return (
        f"🟣 GOLD AI BOT v6 — INSTITUTIONAL SMART MONEY\n"
        f"Symbol: {s['symbol']}\nSygnał: {s['signal']}\nScore regułowy: {s['score']}/100\n"
        f"Cena: {s['price']}\nTrend M15/H1/H4/D1: {s['trend']['M15']} / {s['trend']['H1']} / {s['trend']['H4']} / {s['trend']['D1']}\n\n"
        f"Market Structure H1: {inst['market_structure_h1']['direction']} | BOS: {inst['market_structure_h1']['bos']} | CHOCH: {inst['market_structure_h1']['choch']}\n"
        f"Liquidity Sweep H1: {inst['liquidity_sweep_h1']}\n"
        f"FVG H1: {inst['fair_value_gap_h1']['latest']}\n"
        f"Order Block H1: {inst['order_block_h1']['latest']}\n\n"
        f"Entry: {rp['entry']}\nSL: {rp['sl']}\nTP1: {rp['tp1']}\nTP2: {rp['tp2']}\nTP3: {rp['tp3']}\n\n"
        f"Zasady: ryzyko max 1–2%, nie przesuwaj SL dalej od wejścia, nie dokładaj do straty."
    )


def send_telegram(text: str) -> None:
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)


def job() -> None:
    global LAST_SIGNAL, LAST_ALERT_KEY, LAST_LARGE_CANDLE_ALERT_KEY
    try:
        signal = build_signal()
        LAST_SIGNAL = signal

        # 1) Standard institutional signal alert
        key = f"{signal['signal']}:{signal['risk_plan']['entry']}:{signal['score']}"
        if signal["signal"] != "NO_TRADE" and key != LAST_ALERT_KEY:
            send_telegram(format_signal(signal))
            LAST_ALERT_KEY = key

        # 2) Extra volatility alert: strong M15/H1 candle up or down
        for event in build_large_candle_alerts():
            candle_key = f"{event['interval']}:{event['datetime']}:{event['direction']}"
            if candle_key != LAST_LARGE_CANDLE_ALERT_KEY:
                send_telegram(format_large_candle_alert(event))
                LAST_LARGE_CANDLE_ALERT_KEY = candle_key

    except Exception as e:
        LAST_SIGNAL = {"status": "error", "version": APP_VERSION, "error": str(e), "time_utc": datetime.now(timezone.utc).isoformat()}


@app.get("/")
def root():
    return jsonify({"app": "Gold AI Bot v6", "version": APP_VERSION, "status": "ok"})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION, "scheduler_enabled": SCHEDULER_ENABLED, "closed_candles": CLOSED_CANDLES_ONLY, "large_candle_alerts": LARGE_CANDLE_ALERT_ENABLED, "large_candle_intervals": LARGE_CANDLE_INTERVALS, "large_candle_mode": LARGE_CANDLE_MODE})


@app.get("/signal")
def signal_endpoint():
    job()
    return jsonify(LAST_SIGNAL)


@app.get("/last")
def last_endpoint():
    return jsonify(LAST_SIGNAL)


if SCHEDULER_ENABLED:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(job, "interval", minutes=RUN_INTERVAL_MINUTES, id="gold_ai_bot_v6_1_signal")
    scheduler.start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
