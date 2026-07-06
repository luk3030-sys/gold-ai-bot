import json
import os
from functools import wraps

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from config import env_bool, env_int
from data_provider import fetch_last_price
from db import init_db, list_signals, recent_runs
from notifier import format_signal, send_telegram
from performance import performance_report
from performance_service import manual_run, tick
from strategy import analyze
from tracker import track_open_signals
from validation import run_validation

load_dotenv()
init_db()
app = Flask(__name__)


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


HTML = """
<!doctype html><html lang='pl'><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Gold AI Bot v5</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f4f5f7;color:#111}.box{max-width:920px;margin:20px auto;background:#fff;padding:22px;border-radius:16px;box-shadow:0 2px 18px #0001}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.card{padding:16px;border:1px solid #ddd;border-radius:12px}a.btn{display:inline-block;background:#111;color:#fff;padding:11px 14px;border-radius:9px;text-decoration:none;margin:5px}.muted{color:#666}</style></head>
<body><div class='box'><h1>Gold AI Bot v5 — Performance & Validation</h1>
<p class='muted'>Śledzenie wyników, TP/SL outcome engine, statystyki R, reżim rynku, zamknięte świece, cooldown i walidacja historyczna.</p>
<div class='grid'><div class='card'><b>Live</b><br><a class='btn' href='/analyze'>Analiza</a><a class='btn' href='/performance'>Wyniki</a></div><div class='card'><b>Tracking</b><br><a class='btn' href='/signals'>Sygnały</a><a class='btn' href='/track-now'>Track now</a></div><div class='card'><b>Validation</b><br><a class='btn' href='/validate?bars=1500'>Waliduj 1500 H1</a></div></div>
<p>Automatyka na Render Free: ustaw zewnętrzny cron na <code>/tick</code> co 5 minut.</p></div></body></html>
"""


@app.get("/")
def home():
    return HTML


@app.get("/health")
def health():
    return jsonify({
        "status": "ok", "version": "5.0-performance-validation",
        "scheduler_enabled": env_bool("SCHEDULER_ENABLED", True),
        "closed_candles": env_bool("USE_CLOSED_CANDLES", True),
        "database_path": os.getenv("DATABASE_PATH", os.path.join(os.getenv("DATA_DIR", "/tmp/gold_ai_bot_v5"), "gold_ai_bot_v5.db")),
    })


@app.get("/analyze")
def analyze_endpoint():
    return jsonify(analyze())


@app.get("/run-now")
@protected
def run_now_endpoint():
    return jsonify(manual_run(send_any=True))


@app.get("/tick")
@protected
def tick_endpoint():
    return jsonify(tick())


@app.get("/track-now")
@protected
def track_now():
    return jsonify(track_open_signals())


@app.get("/telegram-test")
def telegram_test():
    return jsonify({"telegram_sent": send_telegram("✅ Gold AI Bot v5: test Telegram działa")})


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


@app.get("/daily-report")
@protected
def daily_report():
    analysis = analyze()
    perf = performance_report()
    sent = send_telegram("📊 <b>Raport dzienny GOLD</b>\n\n" + format_signal(analysis, perf.get("overall")))
    return jsonify({"telegram_sent": sent, "analysis": analysis, "performance": perf.get("overall")})


def scheduled_tick():
    try:
        tick()
    except Exception:
        app.logger.exception("scheduled_tick failed")


def scheduled_daily():
    try:
        analysis = analyze(); perf = performance_report()
        send_telegram("📊 <b>Raport dzienny GOLD</b>\n\n" + format_signal(analysis, perf.get("overall")))
    except Exception:
        app.logger.exception("scheduled_daily failed")


if env_bool("SCHEDULER_ENABLED", True):
    scheduler = BackgroundScheduler(timezone=os.getenv("TIMEZONE", "Europe/Warsaw"))
    scheduler.add_job(
        scheduled_tick,
        IntervalTrigger(minutes=env_int("ANALYZE_INTERVAL_MINUTES", 5)),
        id="v5_tick", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        scheduled_daily,
        CronTrigger(hour=env_int("DAILY_REPORT_HOUR", 7), minute=0),
        id="v5_daily", replace_existing=True, max_instances=1, coalesce=True,
    )
    scheduler.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
