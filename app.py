import os
from flask import Flask, jsonify, render_template_string
from dotenv import load_dotenv
from data_provider import fetch_market_snapshot
from strategy import analyze
from notifier import send_telegram, format_signal
from scheduler import start_scheduler, run_analysis

load_dotenv()
app = Flask(__name__)
scheduler = None

HTML = """
<!doctype html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Gold AI Bot v2</title>
<style>body{font-family:Arial;margin:24px;max-width:760px} .card{border:1px solid #ddd;border-radius:14px;padding:18px;margin:12px 0;box-shadow:0 2px 10px #eee}.buy{color:green}.sell{color:#b00020}.no{color:#555}button{font-size:18px;padding:12px 18px;border-radius:10px;border:0;background:#111;color:white} pre{white-space:pre-wrap}</style>
</head><body><h1>Gold AI Bot v2</h1><div class='card'><b>Status:</b> działa ✅<br><b>Symbol:</b> {{symbol}}<br><b>Interwał:</b> co {{interval}} min</div><p>Endpointy: <code>/health</code>, <code>/analyze</code>, <code>/run-now</code>, <code>/telegram-test</code></p><button onclick="location.href='/run-now'">Analizuj teraz i wyślij Telegram</button><div class='card'><p>Uwaga: bot edukacyjny, nie gwarantuje zysków.</p></div></body></html>
"""

@app.before_request
def ensure_scheduler():
    global scheduler
    if scheduler is None and os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true':
        scheduler = start_scheduler()

@app.get('/')
def home():
    return render_template_string(HTML, symbol=os.getenv('SYMBOL','XAU/USD'), interval=os.getenv('CHECK_INTERVAL_MINUTES','15'))

@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'app': 'Gold AI Bot v2'})

@app.get('/analyze')
def analyze_now():
    snapshot = fetch_market_snapshot()
    return jsonify(analyze(snapshot))

@app.get('/run-now')
def run_now():
    result = run_analysis(send_no_trade=True)
    return '<pre>' + format_signal(result) + '</pre>'

@app.get('/telegram-test')
def telegram_test():
    send_telegram('✅ Gold AI Bot v2: test Telegram działa')
    return jsonify({'status': 'sent'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
