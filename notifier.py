import os
import requests


def _line_price(label, value):
    return f"{label}: {value}" if value is not None else f"{label}: brak"


def format_signal(result):
    icon = '🟢' if result['signal'] == 'BUY' else '🔴' if result['signal'] == 'SELL' else '⚪'
    lines = [
        f"{icon} GOLD AI BOT v2.1",
        f"Symbol: {result['symbol']}",
        f"Sygnał: {result['signal']}",
        f"Score: {result['score']}/100 (min. {result.get('min_score', 70)})",
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
    else:
        wp = result.get('watch_plan', {})
        lines += [
            "",
            "Plan obserwacji:",
            _line_price("Wsparcie", wp.get('support')),
            _line_price("Opór", wp.get('resistance')),
            "",
            "Warunkowy BUY:",
            f"BUY dopiero powyżej: {wp.get('buy_above')}",
            f"SL: {wp.get('buy_sl')}",
            f"TP1: {wp.get('buy_tp1')}",
            f"TP2: {wp.get('buy_tp2')}",
            "",
            "Warunkowy SELL:",
            f"SELL dopiero poniżej: {wp.get('sell_below')}",
            f"SL: {wp.get('sell_sl')}",
            f"TP1: {wp.get('sell_tp1')}",
            f"TP2: {wp.get('sell_tp2')}",
            "",
            f"Komentarz: {wp.get('comment')}",
        ]
    lines += ["", "Powody:"] + [f"- {r}" for r in result['reasons']]
    lines += ["", "To nie jest porada inwestycyjna. Ryzykuj maks. 1–2% kapitału."]
    return "\n".join(lines)


def format_daily_report(result):
    wp = result.get('watch_plan', {})
    lines = [
        "📋 GOLD AI BOT — RAPORT DZIENNY",
        f"Symbol: {result['symbol']}",
        f"Cena: {result['price']}",
        f"Trend H1/H4/D1: {result['trend_h1']} / {result['trend_h4']} / {result['trend_d1']}",
        f"RSI H1: {result['rsi_h1']} | ATR H1: {result['atr_h1']}",
        "",
        f"Najbliższe wsparcie: {wp.get('support')}",
        f"Najbliższy opór: {wp.get('resistance')}",
        "",
        f"Scenariusz BUY: powyżej {wp.get('buy_above')}, SL {wp.get('buy_sl')}, TP1 {wp.get('buy_tp1')}, TP2 {wp.get('buy_tp2')}",
        f"Scenariusz SELL: poniżej {wp.get('sell_below')}, SL {wp.get('sell_sl')}, TP1 {wp.get('sell_tp1')}, TP2 {wp.get('sell_tp2')}",
        "",
        f"Aktualny sygnał: {result['signal']} ({result['score']}/100)",
        f"Komentarz: {wp.get('comment')}",
        "",
        "Uwaga: przed CPI, NFP, FOMC i wystąpieniami Powella ogranicz ryzyko albo nie handluj.",
    ]
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
