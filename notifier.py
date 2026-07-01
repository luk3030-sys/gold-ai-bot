import os
import requests


def format_signal(result):
    icon = '🟢' if result['signal'] == 'BUY' else '🔴' if result['signal'] == 'SELL' else '⚪'
    lines = [
        f"{icon} GOLD AI BOT v2",
        f"Symbol: {result['symbol']}",
        f"Sygnał: {result['signal']}",
        f"Score: {result['score']}/100",
        f"Cena: {result['price']}",
        "",
        f"Trend H1/H4/D1: {result['trend_h1']} / {result['trend_h4']} / {result['trend_d1']}",
        f"RSI H1: {result['rsi_h1']}",
        f"ATR H1: {result['atr_h1']}",
    ]
    if result['signal'] != 'NO TRADE':
        lines += [
            "",
            f"Entry: {result['entry']}",
            f"SL: {result['sl']}",
            f"TP1: {result['tp1']} | RR: {result['rr1']}",
            f"TP2: {result['tp2']} | RR: {result['rr2']}",
        ]
    lines += ["", "Powody:"] + [f"- {r}" for r in result['reasons']]
    lines += ["", "To nie jest porada inwestycyjna. Ryzykuj maks. 1–2% kapitału."]
    return "\n".join(lines)


def send_telegram(text):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise RuntimeError('Brak TELEGRAM_BOT_TOKEN lub TELEGRAM_CHAT_ID')
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    r = requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=15)
    r.raise_for_status()
    return r.json()
