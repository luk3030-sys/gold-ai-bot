import os, json
from flask import Flask, jsonify, render_template_string
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from strategy import analyze
from notifier import send_telegram, format_signal
from storage import add_history, load_history, load_state, save_state

load_dotenv()
app = Flask(__name__)

HTML = """
<!doctype html><html lang='pl'><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Gold AI Bot Pro</title><style>body{font-family:Arial;margin:0;background:#f5f5f5;color:#111}.box{max-width:760px;margin:20px auto;background:white;padding:20px;border-radius:16px;box-shadow:0 2px 18px #0001}button,a.btn{display:inline-block;background:#111;color:#fff;padding:12px 16px;border-radius:10px;text-decoration:none;border:0;margin:6px 4px}.muted{color:#666}pre{white-space:pre-wrap;background:#f0f0f0;padding:12px;border-radius:10px}</style></head>
<body><div class='box'><h1>Gold AI Bot Pro</h1><p class='muted'>Automatyczna analiza XAU/USD: M15/H1/H4/D1, EMA, RSI, MACD, ATR, ADX, Bollinger, Price Action, RR.</p>
<a class='btn' href='/analyze'>Analizuj teraz</a><a class='btn' href='/run-now'>Analizuj i wyślij Telegram</a><a class='btn' href='/daily-report'>Raport dzienny</a><a class='btn' href='/history'>Historia</a>
<p>Status: <b>działa</b></p></div></body></html>
"""

@app.get('/')
def home():
    return HTML

@app.get('/health')
def health():
    return jsonify({"status":"ok", "version":"pro", "scheduler": os.getenv("SCHEDULER_ENABLED","true")})

@app.get('/analyze')
def analyze_endpoint():
    return jsonify(analyze())

@app.get('/run-now')
def run_now():
    result = analyze()
    sent = send_telegram(format_signal(result))
    add_history({"type":"manual", **result, "telegram_sent": sent})
    return jsonify({"telegram_sent": sent, "result": result})

@app.get('/telegram-test')
def telegram_test():
    sent = send_telegram("✅ Gold AI Bot Pro: test Telegram działa")
    return jsonify({"telegram_sent": sent})

@app.get('/history')
def history():
    return jsonify(load_history(50))

@app.get('/daily-report')
def daily_report():
    result = analyze()
    text = "📊 <b>Raport dzienny GOLD</b>\n\n" + format_signal(result)
    sent = send_telegram(text)
    add_history({"type":"daily_report", **result, "telegram_sent": sent})
    return jsonify({"telegram_sent": sent, "result": result})

def scheduled_analysis():
    try:
        result = analyze()
        add_history({"type":"scheduled", **result})
        if result.get("signal") in ["BUY", "SELL"]:
            key = f"{result['signal']}:{result.get('entry')}:{result.get('sl')}:{result.get('tp2')}"
            state = load_state()
            if state.get("last_signal_key") != key:
                sent = send_telegram(format_signal(result))
                state["last_signal_key"] = key
                state["last_sent"] = result
                save_state(state)
                add_history({"type":"sent_signal", **result, "telegram_sent": sent})
    except Exception as e:
        add_history({"type":"error", "error": str(e)})

def scheduled_daily():
    try:
        result = analyze()
        send_telegram("📊 <b>Raport dzienny GOLD</b>\n\n" + format_signal(result))
        add_history({"type":"scheduled_daily", **result})
    except Exception as e:
        add_history({"type":"error_daily", "error": str(e)})

if os.getenv("SCHEDULER_ENABLED", "true").lower() == "true":
    scheduler = BackgroundScheduler(timezone=os.getenv("TIMEZONE", "Europe/Warsaw"))
    scheduler.add_job(scheduled_analysis, IntervalTrigger(minutes=int(os.getenv("ANALYZE_INTERVAL_MINUTES", "5"))), id="analysis", replace_existing=True)
    scheduler.add_job(scheduled_daily, CronTrigger(hour=int(os.getenv("DAILY_REPORT_HOUR", "7")), minute=0), id="daily", replace_existing=True)
    scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')))
