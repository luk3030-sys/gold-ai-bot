import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pandas as pd

from config import env_int
from data_provider import fetch_ohlc
from db import add_event, open_signals, update_signal, utc_now_iso


def evaluate_bar(signal: Dict, high: float, low: float, policy: str = "conservative") -> Dict[str, bool]:
    side = signal["side"]
    if side == "BUY":
        hits = {
            "sl": low <= signal["sl"],
            "tp1": signal.get("tp1") is not None and high >= signal["tp1"],
            "tp2": signal.get("tp2") is not None and high >= signal["tp2"],
            "tp3": signal.get("tp3") is not None and high >= signal["tp3"],
        }
    else:
        hits = {
            "sl": high >= signal["sl"],
            "tp1": signal.get("tp1") is not None and low <= signal["tp1"],
            "tp2": signal.get("tp2") is not None and low <= signal["tp2"],
            "tp3": signal.get("tp3") is not None and low <= signal["tp3"],
        }
    hits["ambiguous_tp2_sl"] = hits["sl"] and hits["tp2"]
    hits["policy"] = policy
    return hits


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _close(signal, outcome: str, r_result: float, price: float, event_type: str):
    now = utc_now_iso()
    update_signal(signal["id"], status="CLOSED", outcome=outcome, r_result=r_result, closed_at=now, last_checked_at=now)
    add_event(signal["id"], event_type, price, {"r_result": r_result})


def track_open_signals() -> dict:
    signals = open_signals()
    if not signals:
        return {"checked": 0, "closed": 0, "events": []}

    policy = os.getenv("AMBIGUOUS_POLICY", "conservative").lower()
    max_age_hours = env_int("MAX_SIGNAL_AGE_HOURS", 72)
    interval = os.getenv("TRACK_INTERVAL", "15min")
    outputsize = env_int("TRACK_OUTPUTSIZE", 500)
    events = []
    closed = 0

    by_symbol = {}
    for signal in signals:
        by_symbol.setdefault(signal["symbol"], []).append(signal)

    for symbol, symbol_signals in by_symbol.items():
        df = fetch_ohlc(symbol, interval, outputsize, closed_only=True)
        for signal in symbol_signals:
            created_at = _parse_iso(signal["created_at"])
            last_checked = _parse_iso(signal.get("last_checked_at")) or created_at
            if created_at is None:
                continue

            candle_times = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
            cutoff = pd.Timestamp(last_checked).tz_convert("UTC")
            candles = df[candle_times > cutoff]
            is_closed = False

            for _, candle in candles.iterrows():
                hit = evaluate_bar(signal, float(candle.high), float(candle.low), policy)

                if hit["tp1"] and not signal.get("tp1_hit"):
                    update_signal(signal["id"], tp1_hit=1)
                    signal["tp1_hit"] = 1
                    add_event(signal["id"], "TP1_HIT", signal.get("tp1"), {})
                    events.append({"signal_id": signal["id"], "event": "TP1_HIT"})

                if hit["tp3"] and not signal.get("tp3_hit"):
                    update_signal(signal["id"], tp3_hit=1)
                    signal["tp3_hit"] = 1
                    add_event(signal["id"], "TP3_TOUCHED", signal.get("tp3"), {})

                if hit["ambiguous_tp2_sl"]:
                    if policy == "optimistic":
                        update_signal(signal["id"], tp2_hit=1)
                        _close(signal, "TP2_HIT", float(signal.get("rr_tp2") or 3.0), signal["tp2"], "CLOSED_TP2")
                    elif policy == "ambiguous":
                        _close(signal, "AMBIGUOUS", 0.0, float(candle.close), "CLOSED_AMBIGUOUS")
                    else:
                        _close(signal, "SL_HIT", -1.0, signal["sl"], "CLOSED_SL_CONSERVATIVE")
                    closed += 1; is_closed = True
                    events.append({"signal_id": signal["id"], "event": "CLOSED_AMBIGUOUS_BAR"})
                    break

                if hit["sl"]:
                    _close(signal, "SL_HIT", -1.0, signal["sl"], "CLOSED_SL")
                    closed += 1; is_closed = True
                    events.append({"signal_id": signal["id"], "event": "SL_HIT"})
                    break

                if hit["tp2"]:
                    update_signal(signal["id"], tp2_hit=1)
                    _close(signal, "TP2_HIT", float(signal.get("rr_tp2") or 3.0), signal["tp2"], "CLOSED_TP2")
                    closed += 1; is_closed = True
                    events.append({"signal_id": signal["id"], "event": "TP2_HIT"})
                    break

            if not is_closed:
                now = datetime.now(timezone.utc)
                if now - created_at >= timedelta(hours=max_age_hours):
                    _close(signal, "TIMEOUT", 0.0, float(df.iloc[-1].close), "CLOSED_TIMEOUT")
                    closed += 1
                    events.append({"signal_id": signal["id"], "event": "TIMEOUT"})
                elif not candles.empty:
                    last_dt = pd.to_datetime(candles.iloc[-1].datetime, utc=True).to_pydatetime()
                    update_signal(signal["id"], last_checked_at=last_dt.isoformat())

    return {"checked": len(signals), "closed": closed, "events": events}
