import os, requests

def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=20)
    return r.ok

def format_signal(a: dict) -> str:
    lines = [
        f"{'🟢' if a['signal']=='BUY' else '🔴' if a['signal']=='SELL' else '⚪'} <b>GOLD AI BOT PRO</b>",
        f"Symbol: {a.get('symbol')}",
        f"Sygnał: <b>{a.get('signal')}</b>",
        f"Score: {a.get('score')}/100",
        f"Cena: {a.get('price')}",
        "",
        f"Trend M15/H1/H4/D1: {a.get('trend_m15')} / {a.get('trend_h1')} / {a.get('trend_h4')} / {a.get('trend_d1')}",
        f"RSI H1: {a.get('rsi_h1')} | ADX H1: {a.get('adx_h1')} | ATR H1: {a.get('atr_h1')}",
    ]
    if a.get('entry'):
        lines += ["", f"Entry: {a['entry']}", f"SL: {a['sl']}", f"TP1: {a['tp1']}", f"TP2: {a['tp2']}", f"TP3: {a['tp3']}", f"RR TP2: {a['rr_tp2']}"]
    lines += ["", "Powody:"] + [f"- {r}" for r in a.get("reasons", [])]
    if a.get("watch_plan"):
        lines += ["", "Plan obserwacji:"] + [f"- {x}" for x in a["watch_plan"]]
    lines += ["", "To nie jest porada inwestycyjna. Ryzykuj maks. 1–2% kapitału."]
    return "\n".join(lines)
