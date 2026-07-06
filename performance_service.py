import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

from config import env_int
from db import (
    add_run, count_signals_since, create_signal, last_closed_loss,
    recent_fingerprint_exists,
)
from notifier import format_signal, send_telegram
from performance import performance_report
from strategy import analyze
from tracker import track_open_signals


def _fingerprint(analysis: Dict) -> str:
    raw = "|".join([
        str(analysis.get("symbol")), str(analysis.get("signal")), str(analysis.get("setup_type")),
        str(analysis.get("regime")), str(analysis.get("closed_h1_candle_time")),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _cooldown_reason(analysis: Dict) -> str | None:
    now = datetime.now(timezone.utc)
    cooldown_minutes = env_int("SIGNAL_COOLDOWN_MINUTES", 60)
    fingerprint = _fingerprint(analysis)
    since = (now - timedelta(minutes=cooldown_minutes)).isoformat()
    if recent_fingerprint_exists(fingerprint, since):
        return f"Duplikat/cooldown {cooldown_minutes} min"

    today = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    max_per_day = env_int("MAX_SIGNALS_PER_DAY", 3)
    if count_signals_since(today) >= max_per_day:
        return f"Limit {max_per_day} sygnałów dziennie"

    loss = last_closed_loss()
    if loss and loss.get("closed_at"):
        loss_dt = datetime.fromisoformat(loss["closed_at"])
        if loss_dt.tzinfo is None:
            loss_dt = loss_dt.replace(tzinfo=timezone.utc)
        loss_cooldown = env_int("LOSS_COOLDOWN_MINUTES", 120)
        if now - loss_dt < timedelta(minutes=loss_cooldown):
            return f"Cooldown po stracie {loss_cooldown} min"
    return None


def tick() -> Dict:
    try:
        tracking = track_open_signals()
        analysis = analyze()
        result = {"tracking": tracking, "analysis": analysis, "new_signal": None, "telegram_sent": False}

        if analysis.get("signal") in {"BUY", "SELL"}:
            reason = _cooldown_reason(analysis)
            if reason:
                result["blocked_reason"] = reason
            else:
                fingerprint = _fingerprint(analysis)
                signal = create_signal(analysis, fingerprint, os.getenv("PRIMARY_TARGET", "TP2"))
                perf = performance_report()
                text = format_signal(analysis, perf.get("overall"))
                sent = send_telegram(text)
                result["new_signal"] = signal
                result["telegram_sent"] = sent

        add_run("tick", "ok", result)
        return result
    except Exception as exc:
        payload = {"error": str(exc), "type": type(exc).__name__}
        add_run("tick", "error", payload)
        raise


def manual_run(send_any: bool = True) -> Dict:
    tracking = track_open_signals()
    analysis = analyze()
    perf = performance_report()
    sent = False
    if send_any or analysis.get("signal") in {"BUY", "SELL"}:
        sent = send_telegram(format_signal(analysis, perf.get("overall")))
    result = {"tracking": tracking, "analysis": analysis, "telegram_sent": sent}
    add_run("manual", "ok", result)
    return result
