import os
from typing import Optional

import requests


def send_telegram(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=20)
    return response.ok


def format_signal(a: dict, performance: Optional[dict] = None) -> str:
    icon = "🟢" if a.get("signal") == "BUY" else "🔴" if a.get("signal") == "SELL" else "⚪"
    lines = [
        f"{icon} <b>GOLD AI BOT v5 — PERFORMANCE</b>",
        f"Symbol: {a.get('symbol')}",
        f"Sygnał: <b>{a.get('signal')}</b>",
        f"Score regułowy: {a.get('score')}/100 (to nie jest prawdopodobieństwo)",
        f"Setup: {a.get('setup_type')} | Reżim: {a.get('regime')}",
        f"Cena: {a.get('price')}",
        "",
        f"Trend M15/H1/H4/D1: {a.get('trend_m15')} / {a.get('trend_h1')} / {a.get('trend_h4')} / {a.get('trend_d1')}",
        f"RSI H1: {a.get('rsi_h1')} | ADX H1/H4: {a.get('adx_h1')} / {a.get('adx_h4')} | ATR H1: {a.get('atr_h1')}",
        f"DXY: {a.get('dxy_status')} | Jakość danych: {a.get('data_quality_score')}/100",
    ]
    if a.get("entry") is not None:
        lines += [
            "", f"Entry: {a.get('entry')}", f"SL: {a.get('sl')}",
            f"TP1: {a.get('tp1')} | RR {a.get('rr_tp1')}",
            f"TP2: {a.get('tp2')} | RR {a.get('rr_tp2')}",
            f"TP3: {a.get('tp3')} | RR {a.get('rr_tp3')}",
        ]
    if a.get("pattern_notes"):
        lines += ["", "Price Action:"] + [f"- {x}" for x in a["pattern_notes"]]
    lines += ["", "Powody:"] + [f"- {r}" for r in a.get("reasons", [])]

    if performance and performance.get("trades", 0) > 0:
        lines += [
            "", "📈 <b>Zweryfikowana historia bota</b>",
            f"Transakcje zamknięte: {performance.get('trades')}",
            f"Win rate: {performance.get('win_rate_pct')}%",
            f"Expectancy: {performance.get('expectancy_r')}R/trade",
            f"Net: {performance.get('net_r')}R | Max DD: {performance.get('max_drawdown_r')}R",
        ]
    else:
        lines += ["", "📈 Historia: za mało zamkniętych sygnałów do wiarygodnych statystyk."]

    if a.get("watch_plan"):
        lines += ["", "Plan obserwacji:"] + [f"- {x}" for x in a["watch_plan"]]
    lines += [
        "", "⚠️ Wyniki historyczne nie gwarantują przyszłych rezultatów.",
        "To nie jest porada inwestycyjna. Ryzykuj maks. 1–2% kapitału.",
    ]
    return "\n".join(lines)
