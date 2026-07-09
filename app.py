import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler

APP_VERSION = "6.5-smart-position-manager"
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

# Position manager settings
POSITIONS_FILE = os.getenv("POSITIONS_FILE", "positions.json")
TELEGRAM_OFFSET_FILE = os.getenv("TELEGRAM_OFFSET_FILE", "telegram_offset.json")
POSITION_CHECK_INTERVAL_MINUTES = int(os.getenv("POSITION_CHECK_INTERVAL_MINUTES", "5"))
TELEGRAM_POLL_INTERVAL_MINUTES = int(os.getenv("TELEGRAM_POLL_INTERVAL_MINUTES", "1"))
DEFAULT_POSITION_VOLUME = float(os.getenv("DEFAULT_POSITION_VOLUME", "0.003"))
AUTO_RISK_ATR_MULTIPLIER = float(os.getenv("AUTO_RISK_ATR_MULTIPLIER", "1.4"))
AUTO_RISK_MIN_POINTS = float(os.getenv("AUTO_RISK_MIN_POINTS", "18"))
TP1_RR = float(os.getenv("TP1_RR", "1.5"))
TP2_RR = float(os.getenv("TP2_RR", "2.5"))
TP3_RR = float(os.getenv("TP3_RR", "3.5"))
BE_TRIGGER_RR = float(os.getenv("BE_TRIGGER_RR", "1.0"))
SL_WARNING_DISTANCE_ATR = float(os.getenv("SL_WARNING_DISTANCE_ATR", "0.35"))
TP_WARNING_DISTANCE_ATR = float(os.getenv("TP_WARNING_DISTANCE_ATR", "0.35"))

# Big candle / volatility alerts
MOVE_ALERT_ENABLED = os.getenv("MOVE_ALERT_ENABLED", "true").lower() == "true"
MOVE_ALERT_INTERVALS = [x.strip() for x in os.getenv("MOVE_ALERT_INTERVALS", "5min,15min,1h").split(",") if x.strip()]
MOVE_BODY_ATR_MIN = float(os.getenv("MOVE_BODY_ATR_MIN", "0.85"))
MOVE_RANGE_ATR_MIN = float(os.getenv("MOVE_RANGE_ATR_MIN", "1.00"))
MOVE_BODY_RATIO_MIN = float(os.getenv("MOVE_BODY_RATIO_MIN", "0.55"))

app = Flask(__name__)
LAST_SIGNAL: Dict[str, Any] = {"status": "starting", "version": APP_VERSION}
LAST_ALERT_KEY: Optional[str] = None
LAST_MOVE_ALERT_KEYS: set = set()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def load_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_positions() -> List[Dict[str, Any]]:
    data = load_json(POSITIONS_FILE, {"positions": []})
    if isinstance(data, list):
        return data
    return data.get("positions", []) if isinstance(data, dict) else []


def save_positions(positions: List[Dict[str, Any]]) -> None:
    save_json(POSITIONS_FILE, {"version": APP_VERSION, "updated_utc": now_utc(), "positions": positions})


def next_position_id(positions: List[Dict[str, Any]]) -> int:
    ids = [int(p.get("id", 0)) for p in positions if str(p.get("id", "")).isdigit()]
    return max(ids, default=0) + 1


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
        "timezone": os.getenv("TIMEZONE", "Europe/Warsaw"),
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


def current_price_and_atr() -> Tuple[float, float]:
    h1 = add_indicators(fetch_ohlc("1h", 120))
    return float(h1.close.iloc[-1]), float(h1.atr14.iloc[-1])


def risk_plan_for_position(side: str, entry: float, atr_value: Optional[float] = None) -> Dict[str, float]:
    if atr_value is None:
        _, atr_value = current_price_and_atr()
    distance = max(float(atr_value) * AUTO_RISK_ATR_MULTIPLIER, AUTO_RISK_MIN_POINTS)
    side = side.upper()
    if side == "SELL":
        sl = entry + distance
        tp1 = entry - distance * TP1_RR
        tp2 = entry - distance * TP2_RR
        tp3 = entry - distance * TP3_RR
    elif side == "BUY":
        sl = entry - distance
        tp1 = entry + distance * TP1_RR
        tp2 = entry + distance * TP2_RR
        tp3 = entry + distance * TP3_RR
    else:
        raise ValueError("side must be BUY or SELL")
    return {"entry": round(entry, 2), "sl": round(sl, 2), "tp1": round(tp1, 2), "tp2": round(tp2, 2), "tp3": round(tp3, 2), "risk_distance": round(distance, 2)}


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
        rp = risk_plan_for_position("SELL", price, atr_h1)
    elif score_buy >= score_sell + 15 and score_buy >= MIN_SCORE_TO_ALERT:
        side = "BUY"; score = score_buy
        rp = risk_plan_for_position("BUY", price, atr_h1)
    else:
        side = "NO_TRADE"; score = max(score_buy, score_sell)
        rp = {"entry": round(price, 2), "sl": None, "tp1": None, "tp2": None, "tp3": None, "risk_distance": None}

    return {
        "version": APP_VERSION,
        "status": "ok",
        "symbol": SYMBOL,
        "time_utc": now_utc(),
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
        "risk_plan": rp | {"risk_note": "Risk max 1-2% capital. Signal is rule score, not probability."},
        "reasons": reasons,
        "closed_candles": CLOSED_CANDLES_ONLY,
    }


def detect_big_move(interval: str) -> Optional[Dict[str, Any]]:
    df = add_indicators(fetch_ohlc(interval, 80))
    if len(df) < 20:
        return None
    last = df.iloc[-1]
    body = float(last.close - last.open)
    rng = float(last.high - last.low)
    atr_value = float(last.atr14)
    if atr_value <= 0 or rng <= 0:
        return None
    body_atr = abs(body) / atr_value
    range_atr = rng / atr_value
    body_ratio = abs(body) / rng
    if body_atr >= MOVE_BODY_ATR_MIN or (range_atr >= MOVE_RANGE_ATR_MIN and body_ratio >= MOVE_BODY_RATIO_MIN):
        direction = "GÓRĘ" if body > 0 else "DÓŁ"
        quality = "EXTREME" if body_atr >= 1.4 or range_atr >= 1.6 else "ELEVATED"
        return {
            "interval": interval,
            "direction": direction,
            "price": round(float(last.close), 2),
            "candle_change": round(body, 2),
            "body_atr": round(body_atr, 2),
            "range_atr": round(range_atr, 2),
            "body_ratio": round(body_ratio, 2),
            "quality": quality,
            "datetime": str(last.datetime),
        }
    return None


def format_move_alert(m: Dict[str, Any]) -> str:
    return (
        f"💥 GOLD MOVE ALERT — MOCNY RUCH W {m['direction']}\n"
        f"Symbol: {SYMBOL} | Interwał: {m['interval']}\n"
        f"Poziom: {m['price']} | Zmiana świecy: {m['candle_change']} pkt\n"
        f"Body/ATR: {m['body_atr']} | Range/ATR: {m['range_atr']}\n"
        f"Jakość ruchu: {m['quality']} | Body ratio: {m['body_ratio']}\n\n"
        f"⚠️ To jest alert zmienności, nie automatyczny sygnał BUY/SELL."
    )


def check_move_alerts() -> None:
    global LAST_MOVE_ALERT_KEYS
    if not MOVE_ALERT_ENABLED:
        return
    for interval in MOVE_ALERT_INTERVALS:
        try:
            move = detect_big_move(interval)
            if not move:
                continue
            key = f"{interval}:{move['datetime']}:{move['direction']}"
            if key not in LAST_MOVE_ALERT_KEYS:
                send_telegram(format_move_alert(move))
                LAST_MOVE_ALERT_KEYS.add(key)
                LAST_MOVE_ALERT_KEYS = set(list(LAST_MOVE_ALERT_KEYS)[-50:])
        except Exception as e:
            print(f"MOVE ALERT ERROR {interval}: {e}")


def format_signal(s: Dict[str, Any]) -> str:
    rp = s["risk_plan"]
    inst = s["institutional"]
    return (
        f"🟣 GOLD AI BOT v6.5 — SMART POSITION MANAGER\n"
        f"Symbol: {s['symbol']}\nSygnał: {s['signal']}\nScore regułowy: {s['score']}/100\n"
        f"Cena: {s['price']}\nTrend M15/H1/H4/D1: {s['trend']['M15']} / {s['trend']['H1']} / {s['trend']['H4']} / {s['trend']['D1']}\n\n"
        f"Market Structure H1: {inst['market_structure_h1']['direction']} | BOS: {inst['market_structure_h1']['bos']} | CHOCH: {inst['market_structure_h1']['choch']}\n"
        f"Liquidity Sweep H1: {inst['liquidity_sweep_h1']}\n"
        f"FVG H1: {inst['fair_value_gap_h1']['latest']}\n"
        f"Order Block H1: {inst['order_block_h1']['latest']}\n\n"
        f"Entry: {rp['entry']}\nSL: {rp['sl']}\nTP1: {rp['tp1']}\nTP2: {rp['tp2']}\nTP3: {rp['tp3']}\n\n"
        f"Komendy: /position SELL {rp['entry']} albo /position BUY {rp['entry']}\n"
        f"Zasady: ryzyko max 1–2%, nie przesuwaj SL dalej od wejścia, nie dokładaj do straty."
    )


def send_telegram(text: str, chat_id: Optional[str] = None) -> None:
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN:
        return
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": target_chat_id, "text": text}, timeout=15)


def format_position(p: Dict[str, Any], price: Optional[float] = None) -> str:
    side = p["side"]
    entry = float(p["entry"])
    sl = p.get("sl")
    tp1 = p.get("tp1")
    tp2 = p.get("tp2")
    tp3 = p.get("tp3")
    pnl_points = None
    rr = None
    if price is not None:
        pnl_points = (entry - price) if side == "SELL" else (price - entry)
        risk = abs(float(sl) - entry) if sl else None
        rr = pnl_points / risk if risk else None
    status = ""
    if pnl_points is not None:
        status = f"\nAktualnie: {round(price, 2)} | PnL pkt: {round(pnl_points, 2)} | RR: {round(rr, 2) if rr is not None else '-'}"
    return (
        f"#{p['id']} {side} {entry} | wolumen {p.get('volume', DEFAULT_POSITION_VOLUME)}\n"
        f"SL: {sl} | TP1: {tp1} | TP2: {tp2} | TP3: {tp3}{status}"
    )


def add_position(side: str, entry: float, volume: Optional[float] = None, chat_id: Optional[str] = None) -> Dict[str, Any]:
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("Użyj BUY albo SELL")
    price, atr_value = current_price_and_atr()
    rp = risk_plan_for_position(side, entry, atr_value)
    positions = load_positions()
    p = {
        "id": next_position_id(positions),
        "symbol": SYMBOL,
        "side": side,
        "entry": round(entry, 2),
        "volume": float(volume or DEFAULT_POSITION_VOLUME),
        "sl": rp["sl"],
        "tp1": rp["tp1"],
        "tp2": rp["tp2"],
        "tp3": rp["tp3"],
        "risk_distance": rp["risk_distance"],
        "created_utc": now_utc(),
        "status": "OPEN",
        "alerts_sent": [],
        "chat_id": str(chat_id or TELEGRAM_CHAT_ID or ""),
        "note": "SL/TP calculated automatically from H1 ATR. Update broker manually unless you connect broker API.",
    }
    positions.append(p)
    save_positions(positions)
    return p


def close_position(position_id: int) -> bool:
    positions = load_positions()
    new_positions = [p for p in positions if int(p.get("id", -1)) != int(position_id)]
    save_positions(new_positions)
    return len(new_positions) != len(positions)


def update_position(position_id: int, **updates: Any) -> Optional[Dict[str, Any]]:
    positions = load_positions()
    updated = None
    for p in positions:
        if int(p.get("id", -1)) == int(position_id):
            for k, v in updates.items():
                if v is not None:
                    p[k] = v
            p["updated_utc"] = now_utc()
            updated = p
            break
    save_positions(positions)
    return updated


def position_monitor_job() -> None:
    try:
        price, atr_value = current_price_and_atr()
        positions = load_positions()
        changed = False
        for p in positions:
            side = p.get("side")
            entry = float(p.get("entry"))
            sl = safe_float(p.get("sl"))
            tp1 = safe_float(p.get("tp1"))
            tp2 = safe_float(p.get("tp2"))
            tp3 = safe_float(p.get("tp3"))
            alerts = set(p.get("alerts_sent", []))
            risk = abs(sl - entry) if sl is not None else None
            pnl_points = (entry - price) if side == "SELL" else (price - entry)
            rr = pnl_points / risk if risk else 0
            chat_id = p.get("chat_id") or TELEGRAM_CHAT_ID

            def alert_once(key: str, text: str):
                nonlocal changed
                if key not in alerts:
                    send_telegram(text, chat_id=chat_id)
                    alerts.add(key)
                    p["alerts_sent"] = sorted(alerts)
                    changed = True

            if risk and rr >= BE_TRIGGER_RR:
                alert_once(
                    f"BE_{BE_TRIGGER_RR}",
                    f"🛡️ Pozycja #{p['id']} {side}: osiągnięto około RR {round(rr, 2)}. Rozważ przesunięcie SL na BE: {entry}.\nCena: {round(price, 2)}",
                )
            for tp_key, tp_value in [("TP1", tp1), ("TP2", tp2), ("TP3", tp3)]:
                if tp_value is None:
                    continue
                hit = price <= tp_value if side == "SELL" else price >= tp_value
                near = abs(price - tp_value) <= atr_value * TP_WARNING_DISTANCE_ATR
                if hit:
                    alert_once(f"HIT_{tp_key}", f"🎯 Pozycja #{p['id']} {side}: osiągnięto {tp_key} {tp_value}. Aktualna cena: {round(price, 2)}")
                elif near:
                    alert_once(f"NEAR_{tp_key}", f"⏳ Pozycja #{p['id']} {side}: cena blisko {tp_key} {tp_value}. Aktualna cena: {round(price, 2)}")
            if sl is not None:
                sl_hit = price >= sl if side == "SELL" else price <= sl
                sl_near = abs(price - sl) <= atr_value * SL_WARNING_DISTANCE_ATR
                if sl_hit:
                    alert_once("HIT_SL", f"🛑 Pozycja #{p['id']} {side}: cena dotknęła/przebiła SL {sl}. Aktualna cena: {round(price, 2)}")
                elif sl_near:
                    alert_once("NEAR_SL", f"⚠️ Pozycja #{p['id']} {side}: cena blisko SL {sl}. Aktualna cena: {round(price, 2)}")
        if changed:
            save_positions(positions)
    except Exception as e:
        print(f"POSITION MONITOR ERROR: {e}")


def command_help() -> str:
    return (
        "Komendy Gold AI Bot v6.5:\n"
        "/position SELL 4097 — dodaj pozycję SELL i automatycznie wylicz SL/TP\n"
        "/position BUY 4097 — dodaj pozycję BUY i automatycznie wylicz SL/TP\n"
        "/positions — pokaż otwarte pozycje\n"
        "/close 1 — usuń pozycję #1 z pamięci bota\n"
        "/setsl 1 4202 — zmień SL pozycji #1\n"
        "/settp 1 3969 3892 3814 — zmień TP1/TP2/TP3 pozycji #1\n"
        "/signal — wygeneruj aktualny sygnał\n"
        "/price — aktualna cena i ATR H1\n"
        "Uwaga: bot nie składa zleceń u brokera. SL/TP trzeba wpisać ręcznie w aplikacji brokera, chyba że podłączysz API brokera."
    )


def handle_command(text: str, chat_id: str) -> str:
    raw = text.strip()
    parts = raw.split()
    if not parts:
        return command_help()
    cmd = parts[0].lower()

    # Accept plain "SELL 4097" and "BUY 4097" as shortcut.
    if cmd in ("buy", "sell") and len(parts) >= 2:
        side = cmd.upper()
        entry = safe_float(parts[1])
        if entry is None:
            return "Nie rozumiem ceny wejścia. Przykład: SELL 4097"
        p = add_position(side, entry, chat_id=chat_id)
        return "✅ Dodano pozycję do pamięci bota:\n" + format_position(p)

    if cmd in ("/start", "/help"):
        return command_help()

    if cmd == "/position":
        if len(parts) < 3:
            return "Format: /position SELL 4097 albo /position BUY 4097"
        side = parts[1].upper()
        entry = safe_float(parts[2])
        volume = safe_float(parts[3]) if len(parts) >= 4 else None
        if side not in ("BUY", "SELL") or entry is None:
            return "Format: /position SELL 4097 albo /position BUY 4097"
        p = add_position(side, entry, volume, chat_id=chat_id)
        return "✅ Dodano pozycję do pamięci bota:\n" + format_position(p)

    if cmd == "/positions":
        positions = load_positions()
        if not positions:
            return "Brak otwartych pozycji w pamięci bota."
        try:
            price, _ = current_price_and_atr()
        except Exception:
            price = None
        return "📌 Otwarte pozycje:\n\n" + "\n\n".join(format_position(p, price) for p in positions)

    if cmd == "/close":
        if len(parts) < 2 or not parts[1].isdigit():
            return "Format: /close 1"
        ok = close_position(int(parts[1]))
        return "✅ Usunięto pozycję z pamięci bota." if ok else "Nie znaleziono pozycji o takim ID."

    if cmd == "/setsl":
        if len(parts) < 3 or not parts[1].isdigit():
            return "Format: /setsl 1 4202"
        sl = safe_float(parts[2])
        if sl is None:
            return "Nie rozumiem poziomu SL."
        p = update_position(int(parts[1]), sl=round(sl, 2))
        return "✅ Zmieniono SL:\n" + format_position(p) if p else "Nie znaleziono pozycji."

    if cmd == "/settp":
        if len(parts) < 3 or not parts[1].isdigit():
            return "Format: /settp 1 3969 3892 3814"
        updates = {}
        for idx, name in enumerate(["tp1", "tp2", "tp3"], start=2):
            if len(parts) > idx:
                value = safe_float(parts[idx])
                if value is not None:
                    updates[name] = round(value, 2)
        p = update_position(int(parts[1]), **updates)
        return "✅ Zmieniono TP:\n" + format_position(p) if p else "Nie znaleziono pozycji."

    if cmd == "/signal":
        s = build_signal()
        return format_signal(s)

    if cmd == "/price":
        price, atr_value = current_price_and_atr()
        return f"Cena {SYMBOL}: {round(price, 2)}\nATR H1: {round(atr_value, 2)}"

    return "Nieznana komenda.\n\n" + command_help()


def telegram_poll_job() -> None:
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN:
        return
    state = load_json(TELEGRAM_OFFSET_FILE, {"offset": None})
    params = {"timeout": 5}
    if state.get("offset") is not None:
        params["offset"] = int(state["offset"])
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            return
        max_update_id = None
        for update in data.get("result", []):
            max_update_id = update.get("update_id")
            message = update.get("message") or update.get("edited_message") or {}
            text = message.get("text") or ""
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", ""))
            if not text or not chat_id:
                continue
            response = handle_command(text, chat_id)
            send_telegram(response, chat_id=chat_id)
        if max_update_id is not None:
            save_json(TELEGRAM_OFFSET_FILE, {"offset": int(max_update_id) + 1, "updated_utc": now_utc()})
    except Exception as e:
        print(f"TELEGRAM POLL ERROR: {e}")


def job() -> None:
    global LAST_SIGNAL, LAST_ALERT_KEY
    try:
        signal = build_signal()
        LAST_SIGNAL = signal
        key = f"{signal['signal']}:{signal['risk_plan']['entry']}:{signal['score']}"
        if signal["signal"] != "NO_TRADE" and key != LAST_ALERT_KEY:
            send_telegram(format_signal(signal))
            LAST_ALERT_KEY = key
    except Exception as e:
        LAST_SIGNAL = {"status": "error", "version": APP_VERSION, "error": str(e), "time_utc": now_utc()}


@app.get("/")
def root():
    return jsonify({"app": "Gold AI Bot v6.5", "version": APP_VERSION, "status": "ok"})


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "scheduler_enabled": SCHEDULER_ENABLED,
        "closed_candles": CLOSED_CANDLES_ONLY,
        "telegram_polling": ENABLE_TELEGRAM and bool(TELEGRAM_BOT_TOKEN),
        "positions_count": len(load_positions()),
        "move_alert_enabled": MOVE_ALERT_ENABLED,
        "move_alert_intervals": MOVE_ALERT_INTERVALS,
    })


@app.get("/signal")
def signal_endpoint():
    job()
    return jsonify(LAST_SIGNAL)


@app.get("/last")
def last_endpoint():
    return jsonify(LAST_SIGNAL)


@app.get("/positions")
def positions_endpoint():
    return jsonify({"positions": load_positions(), "count": len(load_positions()), "version": APP_VERSION})


@app.post("/positions")
def add_position_endpoint():
    data = request.get_json(force=True, silent=True) or {}
    side = str(data.get("side", "")).upper()
    entry = safe_float(data.get("entry"))
    volume = safe_float(data.get("volume"))
    if side not in ("BUY", "SELL") or entry is None:
        return jsonify({"status": "error", "message": "Use JSON: {'side':'SELL','entry':4097}"}), 400
    p = add_position(side, entry, volume)
    return jsonify({"status": "ok", "position": p})


@app.post("/telegram/webhook")
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if text and chat_id:
        send_telegram(handle_command(text, chat_id), chat_id=chat_id)
    return jsonify({"ok": True})


@app.get("/move-alert-test")
def move_alert_test():
    results = []
    for interval in MOVE_ALERT_INTERVALS:
        try:
            results.append({"interval": interval, "move": detect_big_move(interval)})
        except Exception as e:
            results.append({"interval": interval, "error": str(e)})
    return jsonify({"results": results})


if SCHEDULER_ENABLED:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(job, "interval", minutes=RUN_INTERVAL_MINUTES, id="gold_ai_bot_v6_5_signal", replace_existing=True)
    scheduler.add_job(position_monitor_job, "interval", minutes=POSITION_CHECK_INTERVAL_MINUTES, id="position_monitor", replace_existing=True)
    scheduler.add_job(check_move_alerts, "interval", minutes=POSITION_CHECK_INTERVAL_MINUTES, id="move_alerts", replace_existing=True)
    # Polling allows Telegram commands without setting a webhook. Highest practical frequency is 1 minute.
    scheduler.add_job(telegram_poll_job, "interval", minutes=max(1, TELEGRAM_POLL_INTERVAL_MINUTES), id="telegram_poll", replace_existing=True)
    scheduler.start()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
