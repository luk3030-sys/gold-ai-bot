import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify

from data_provider import get_multi_timeframe_data
from notifier import send_telegram
from strategy import analyze_gold

app = Flask(__name__)

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
SEND_NO_TRADE = os.getenv("SEND_NO_TRADE", "false").lower() == "true"
AUTO_RUN = os.getenv("AUTO_RUN", "true").lower() == "true"

_last_signal_key = None
_last_run = None
_last_result = None
_worker_started = False


def run_analysis(send_message: bool = True):
    global _last_signal_key, _last_run, _last_result

    symbol = os.getenv("SYMBOL", "XAU/USD")
    data = get_multi_timeframe_data(symbol)
    result = analyze_gold(symbol, data)

    _last_run = datetime.now(timezone.utc).isoformat()
    _last_result = result

    signal_key = f"{result.get('signal')}:{result.get('entry')}:{result.get('sl')}:{result.get('tp1')}:{result.get('score')}"

    should_send = send_message and (result.get("signal") != "NO TRADE" or SEND_NO_TRADE)
    if should_send and signal_key != _last_signal_key:
        send_telegram(format_signal_message(result))
        _last_signal_key = signal_key

    return result


def format_signal_message(result: dict) -> str:
    lines = [
        f"📊 GOLD AI ANALYST v1",
        f"Sygnał: {result.get('signal')}",
        f"Score: {result.get('score')}/100",
        f"Symbol: {result.get('symbol')}",
        f"Cena: {result.get('price')}",
        "",
        f"Entry: {result.get('entry')}",
        f"SL: {result.get('sl')}",
        f"TP1: {result.get('tp1')}",
        f"TP2: {result.get('tp2')}",
        f"RR TP1: {result.get('rr1')}",
        f"RR TP2: {result.get('rr2')}",
        "",
        "Powody:",
    ]
    for r in result.get("reasons", []):
        lines.append(f"- {r}")
    lines += ["", "Pamiętaj: to alert analityczny, nie gwarancja wyniku. Ryzykuj maks. 1–2% kapitału."]
    return "\n".join(lines)


def worker_loop():
    while True:
        try:
            run_analysis(send_message=True)
        except Exception as e:
            try:
                send_telegram(f"⚠️ Gold AI Bot error: {e}")
            except Exception:
                pass
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


def start_worker_once():
    global _worker_started
    if AUTO_RUN and not _worker_started:
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        _worker_started = True


@app.before_request
def before_request():
    start_worker_once()


@app.get("/")
def home():
    return "Gold AI Bot v1 działa. Użyj /health albo /run-now"


@app.get("/health")
def health():
    return jsonify({"status": "ok", "last_run": _last_run, "auto_run": AUTO_RUN})


@app.get("/run-now")
def run_now():
    try:
        result = run_analysis(send_message=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.get("/last")
def last():
    return jsonify(_last_result or {"status": "no analysis yet"})


if __name__ == "__main__":
    start_worker_once()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
