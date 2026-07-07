import os
from functools import wraps

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from config import env_bool, env_int
from data_provider import fetch_last_price, fetch_ohlc, provider_health, market_cache_status
from db import db_health, database_info, init_db, list_signals, recent_runs
from move_detector import detect_large_move
from notifier import format_signal, send_telegram
from performance import performance_report
from performance_service import manual_run, tick
from strategy import analyze
from tracker import track_open_signals
from validation import run_validation
from quota_guard import quota_status

load_dotenv()
init_db()
app = Flask(__name__)

VERSION = "6.3.2-quota-guard-smart-cache"


def _authorized() -> bool:
    secret = os.getenv("CRON_SECRET", "").strip()
    if not secret:
        return True
    return request.args.get("secret") == secret or request.headers.get("X-Cron-Secret") == secret


def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _authorized():
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def _endpoint_error(endpoint: str, exc: Exception):
    """Return a useful JSON error instead of a generic Flask 500 page."""
    app.logger.exception("%s failed", endpoint)
    message = str(exc)
    hint = "Sprawdź Render Logs oraz /market-diagnostics."
    lower = message.lower()
    if "twelvedata" in lower or "api" in lower or "429" in lower:
        hint = "Prawdopodobny problem danych/API Twelve Data: limit, plan, chwilowy błąd lub brak danych dla interwału."
    elif "za mało danych" in lower or "ema200" in lower:
        hint = "Dostawca zwrócił za mało świec do stabilnego EMA200."
    return jsonify({
        "status": "error",
        "version": VERSION,
        "endpoint": endpoint,
        "error_type": type(exc).__name__,
        "error": message,
        "hint": hint,
    }), 503


HTML = """
<!doctype html><html lang='pl'><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Gold AI Bot v6.3.2</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f4f5f7;color:#111}.box{max-width:1040px;margin:20px auto;background:#fff;padding:22px;border-radius:16px;box-shadow:0 2px 18px #0001}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.card{padding:16px;border:1px solid #ddd;border-radius:12px}a.btn{display:inline-block;background:#111;color:#fff;padding:11px 14px;border-radius:9px;text-decoration:none;margin:5px}.muted{color:#666}code{background:#f1f1f1;padding:2px 5px;border-radius:5px}</style></head>
<body><div class='box'><h1>Gold AI Bot v6.3.2 — Quota Guard + Smart Multi-Timeframe Cache</h1>
<p class='muted'>Institutional Smart Money + PostgreSQL Performance Engine + Quota Guard + trwały Smart Multi-Timeframe Cache. Cron może działać co 10 minut bez pobierania wszystkich interwałów od nowa.</p>
<div class='grid'>
<div class='card'><b>Analiza</b><br><a class='btn' href='/analyze'>Analiza</a><a class='btn' href='/institutional'>Institutional</a></div>
<div class='card'><b>Automatyka</b><br><a class='btn' href='/tick'>Tick</a><a class='btn' href='/move-watch'>Move watch</a></div>
<div class='card'><b>Performance</b><br><a class='btn' href='/performance'>Wyniki</a><a class='btn' href='/signals'>Sygnały</a></div>
<div class='card'><b>Stability</b><br><a class='btn' href='/health'>Health</a><a class='btn' href='/ready'>Ready</a><a class='btn' href='/quota-status'>Quota</a><a class='btn' href='/cache-status'>Cache</a></div>
</div>
<p>Na Render Free: <code>SCHEDULER_ENABLED=false</code> i zewnętrzny cron na <code>/tick</code> co 10 minut. Smart cache odświeża M15/H1/H4/D1 tylko wtedy, gdy powinna istnieć nowa zamknięta świeca.</p></div></body></html>
"""


@app.get("/")
def home():
    return HTML


@app.get("/health")
def health():
    db = db_health()
    return jsonify({
        "status": "ok" if db.get("ok") else "degraded",
        "version": VERSION,
        "scheduler_enabled": env_bool("SCHEDULER_ENABLED", False),
        "closed_candles": env_bool("USE_CLOSED_CANDLES", True),
        "database": db,
        "dxy_enabled": env_bool("DXY_ENABLED", True),
        "move_alert_enabled": env_bool("MOVE_ALERT_ENABLED", True),
        "institutional_engine": True,
        "quota_guard_enabled": env_bool("QUOTA_GUARD_ENABLED", True),
        "smart_mtf_cache": True,
    })


@app.get("/ready")
def ready():
    db = db_health()
    market = provider_health() if env_bool("READY_CHECK_MARKET", True) else {"ok": True, "skipped": True}
    ok = bool(db.get("ok")) and bool(market.get("ok"))
    return jsonify({"ready": ok, "version": VERSION, "database": db, "market": market}), (200 if ok else 503)


@app.get("/data-health")
def data_health():
    return jsonify(provider_health())


@app.get("/analyze")
def analyze_endpoint():
    try:
        return jsonify(analyze())
    except Exception as exc:
        return _endpoint_error("/analyze", exc)


@app.get("/institutional")
def institutional_endpoint():
    try:
        a = analyze()
        return jsonify({
            "symbol": a.get("symbol"), "price": a.get("price"), "signal": a.get("signal"),
            "setup_type": a.get("setup_type"), "regime": a.get("regime"),
            "institutional": a.get("institutional"), "watch_plan": a.get("watch_plan"),
        })
    except Exception as exc:
        return _endpoint_error("/institutional", exc)


@app.get("/market-diagnostics")
@protected
def market_diagnostics():
    symbol = os.getenv("SYMBOL", "XAU/USD")
    checks = {}
    force_refresh = request.args.get("refresh") in {"1", "true", "yes"}
    for name, interval in (("m15", "15min"), ("h1", "1h"), ("h4", "4h"), ("d1", "1day")):
        try:
            df = fetch_ohlc(symbol, interval, 320, closed_only=True, force_refresh=force_refresh)
            checks[name] = {
                "ok": True,
                "interval": interval,
                "rows": int(len(df)),
                "last_candle": str(df.iloc[-1].datetime) if len(df) else None,
                "data_source": df.attrs.get("data_source"),
                "stale": bool(df.attrs.get("stale", False)),
                "stale_age_seconds": df.attrs.get("stale_age_seconds"),
                "smart_cache_hit": bool(df.attrs.get("smart_cache_hit", False)),
                "fallback_reason": df.attrs.get("fallback_reason"),
            }
        except Exception as exc:
            checks[name] = {
                "ok": False,
                "interval": interval,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    all_ok = all(item.get("ok") for item in checks.values())
    return jsonify({"status": "ok" if all_ok else "degraded", "symbol": symbol, "checks": checks}), (200 if all_ok else 503)


@app.get("/quota-status")
def quota_status_endpoint():
    return jsonify(quota_status())


@app.get("/cache-status")
def cache_status_endpoint():
    return jsonify(market_cache_status(int(request.args.get("limit", 100))))


@app.get("/run-now")
@protected
def run_now_endpoint():
    return jsonify(manual_run(send_any=True))


# Compatibility alias for older v6 cron configurations.
@app.get("/signal")
@protected
def signal_endpoint():
    return jsonify(manual_run(send_any=True))


@app.get("/tick")
@protected
def tick_endpoint():
    return jsonify(tick())


@app.get("/move-watch")
@protected
def move_watch_endpoint():
    return jsonify(detect_large_move())


@app.get("/track-now")
@protected
def track_now():
    return jsonify(track_open_signals())


@app.get("/telegram-test")
def telegram_test():
    return jsonify({"telegram_sent": send_telegram("✅ Gold AI Bot v6.3.2: test Telegram działa")})


@app.get("/signals")
def signals():
    return jsonify(list_signals(request.args.get("limit", 100), request.args.get("status")))


@app.get("/history")
def history():
    return jsonify(recent_runs(int(request.args.get("limit", 50))))


@app.get("/performance")
def performance():
    return jsonify(performance_report())


@app.get("/validate")
def validate():
    bars = int(request.args.get("bars", 1500))
    return jsonify(run_validation(os.getenv("SYMBOL", "XAU/USD"), bars))


@app.get("/feed-check")
def feed_check():
    broker_price = request.args.get("broker_price", type=float)
    provider_price = fetch_last_price(os.getenv("SYMBOL", "XAU/USD"))
    if broker_price is None:
        return jsonify({"provider_price": provider_price, "usage": "/feed-check?broker_price=4057.28"})
    diff = provider_price - broker_price
    return jsonify({
        "provider_price": round(provider_price, 4), "broker_price": broker_price,
        "difference": round(diff, 4),
        "difference_pct": round(100 * diff / broker_price, 4) if broker_price else None,
        "warning": abs(diff / broker_price) > 0.001 if broker_price else None,
    })


@app.get("/db-info")
def db_info():
    return jsonify({"database": database_info(), "health": db_health()})


@app.get("/daily-report")
@protected
def daily_report():
    analysis = analyze()
    perf = performance_report()
    sent = send_telegram("📊 <b>Raport dzienny GOLD v6.3.2</b>\n\n" + format_signal(analysis, perf.get("overall")))
    return jsonify({"telegram_sent": sent, "analysis": analysis, "performance": perf.get("overall")})


def scheduled_tick():
    try:
        tick()
    except Exception:
        app.logger.exception("scheduled_tick failed")


def scheduled_daily():
    try:
        analysis = analyze()
        perf = performance_report()
        send_telegram("📊 <b>Raport dzienny GOLD v6.3.2</b>\n\n" + format_signal(analysis, perf.get("overall")))
    except Exception:
        app.logger.exception("scheduled_daily failed")


if env_bool("SCHEDULER_ENABLED", False):
    scheduler = BackgroundScheduler(timezone=os.getenv("TIMEZONE", "Europe/Warsaw"))
    scheduler.add_job(
        scheduled_tick,
        IntervalTrigger(minutes=env_int("ANALYZE_INTERVAL_MINUTES", 10)),
        id="v6_3_2_tick", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        scheduled_daily,
        CronTrigger(hour=env_int("DAILY_REPORT_HOUR", 7), minute=0),
        id="v6_3_2_daily", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
