import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Dict

from config import env_bool, env_int
from db import (
    acquire_job_lock,
    add_run,
    count_signals_since,
    create_signal,
    database_info,
    last_closed_loss,
    recent_fingerprint_exists,
    release_job_lock,
)
from move_detector import detect_large_move, mark_move_alert_sent
from data_provider import ProviderDataUnavailable
from quota_guard import QuotaGuardBlocked, RateLimitError, quota_status
from notifier import format_move_alert, format_signal, send_telegram
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
    lock_name = "tick"
    owner = acquire_job_lock(lock_name, ttl_seconds=env_int("TICK_LOCK_TTL_SECONDS", 240))
    if not owner:
        return {"status": "skipped", "reason": "tick_already_running", "database": database_info(), "quota": quota_status()}

    try:
        try:
            tracking = track_open_signals()
        except (QuotaGuardBlocked, RateLimitError, ProviderDataUnavailable) as exc:
            tracking = {"checked": 0, "closed": 0, "events": [], "status": "degraded", "error": f"{type(exc).__name__}: {exc}"}

        move_alert = None
        move_sent = False
        if env_bool("MOVE_ALERT_ENABLED", True):
            try:
                move_alert = detect_large_move()
                if move_alert.get("triggered") and move_alert.get("is_new"):
                    move_sent = send_telegram(format_move_alert(move_alert))
                    if move_sent:
                        mark_move_alert_sent(move_alert)
            except Exception as exc:
                move_alert = {"triggered": False, "status": "degraded", "error": f"{type(exc).__name__}: {exc}"}

        try:
            analysis = analyze()
        except (QuotaGuardBlocked, RateLimitError, ProviderDataUnavailable) as exc:
            result = {
                "status": "degraded",
                "reason": "market_data_unavailable",
                "error": f"{type(exc).__name__}: {exc}",
                "tracking": tracking,
                "move_alert": move_alert,
                "move_telegram_sent": move_sent,
                "analysis": None,
                "new_signal": None,
                "telegram_sent": False,
                "database": database_info(),
                "quota": quota_status(),
            }
            add_run("tick_v6_3_2", "degraded", result)
            return result

        result = {
            "status": "ok",
            "tracking": tracking,
            "move_alert": move_alert,
            "move_telegram_sent": move_sent,
            "analysis": analysis,
            "new_signal": None,
            "telegram_sent": False,
            "database": database_info(),
            "quota": quota_status(),
        }

        if analysis.get("signal") in {"BUY", "SELL"}:
            reason = _cooldown_reason(analysis)
            if reason:
                result["blocked_reason"] = reason
            else:
                fingerprint = _fingerprint(analysis)
                signal = create_signal(analysis, fingerprint, os.getenv("PRIMARY_TARGET", "TP2"))
                perf = performance_report()
                sent = send_telegram(format_signal(analysis, perf.get("overall")))
                result["new_signal"] = signal
                result["telegram_sent"] = sent

        add_run("tick_v6_3_2", "ok", result)
        return result
    except Exception as exc:
        payload = {"error": str(exc), "type": type(exc).__name__, "quota": quota_status()}
        try:
            add_run("tick_v6_3_2", "error", payload)
        except Exception:
            pass
        raise
    finally:
        release_job_lock(lock_name, owner)


def manual_run(send_any: bool = True) -> Dict:
    tracking = track_open_signals()
    analysis = analyze()
    perf = performance_report()
    sent = False
    if send_any or analysis.get("signal") in {"BUY", "SELL"}:
        sent = send_telegram(format_signal(analysis, perf.get("overall")))
    result = {"tracking": tracking, "analysis": analysis, "telegram_sent": sent}
    add_run("manual_v6_3_2", "ok", result)
    return result
