import os
from apscheduler.schedulers.background import BackgroundScheduler
from data_provider import fetch_market_snapshot
from strategy import analyze
from notifier import send_telegram, format_signal

_last_sent = {'key': None}


def run_analysis(send_no_trade=False):
    snapshot = fetch_market_snapshot()
    result = analyze(snapshot)
    should_send = result['signal'] != 'NO TRADE' or send_no_trade
    key = f"{result['signal']}:{result.get('entry')}:{result.get('sl')}:{result.get('tp1')}"
    if should_send and key != _last_sent.get('key'):
        send_telegram(format_signal(result))
        _last_sent['key'] = key
    return result


def start_scheduler():
    interval = int(os.getenv('CHECK_INTERVAL_MINUTES', '15'))
    scheduler = BackgroundScheduler(timezone='Europe/Warsaw')
    scheduler.add_job(lambda: run_analysis(os.getenv('SEND_NO_TRADE', 'false').lower() == 'true'), 'interval', minutes=interval, id='gold_analysis', replace_existing=True)
    scheduler.start()
    return scheduler
