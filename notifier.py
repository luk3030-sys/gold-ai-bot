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


def _smc_lines(a: dict) -> list[str]:
    inst = a.get("institutional") or {}
    lines = []
    for tf in ["h4", "h1", "m15"]:
        ctx = inst.get(tf) or {}
        structure = ctx.get("structure") or {}
        sweep = ctx.get("liquidity_sweep") or {}
        nearest_fvg = ctx.get("nearest_fvg")
        event = structure.get("event", "NONE")
        bias = structure.get("bias", "UNKNOWN")
        sweep_type = sweep.get("type", "NONE")
        fvg_text = nearest_fvg.get("type") if isinstance(nearest_fvg, dict) else "NONE"
        lines.append(f"{tf.upper()}: {bias} | {event} | Sweep {sweep_type} | FVG {fvg_text}")
    return lines


def format_signal(a: dict, performance: Optional[dict] = None) -> str:
    icon = "🟢" if a.get("signal") == "BUY" else "🔴" if a.get("signal") == "SELL" else "⚪"
    lines = [
        f"{icon} <b>GOLD AI BOT v6.3.2 — QUOTA GUARD + SMART CACHE</b>",
        f"Symbol: {a.get('symbol')}",
        f"Sygnał: <b>{a.get('signal')}</b>",
        f"Score regułowy: {a.get('score')}/100 (nie jest prawdopodobieństwem)",
        f"Setup: {a.get('setup_type')} | Reżim: {a.get('regime')}",
        f"Cena: {a.get('price')}",
        "",
        f"Trend M15/H1/H4/D1: {a.get('trend_m15')} / {a.get('trend_h1')} / {a.get('trend_h4')} / {a.get('trend_d1')}",
        f"RSI H1: {a.get('rsi_h1')} | ADX H1/H4: {a.get('adx_h1')} / {a.get('adx_h4')} | ATR H1: {a.get('atr_h1')}",
        f"DXY: {a.get('dxy_status')} | Jakość danych: {a.get('data_quality_score')}/100",
        "",
        "🏦 <b>Institutional Smart Money</b>",
    ]
    lines += _smc_lines(a)

    if a.get("entry") is not None:
        lines += [
            "", f"Entry: {a.get('entry')} | Strefa {a.get('entry_zone_low')}–{a.get('entry_zone_high')}", f"SL: {a.get('sl')}",
            f"TP1: {a.get('tp1')} | RR {a.get('rr_tp1')}",
            f"TP2: {a.get('tp2')} | RR {a.get('rr_tp2')}",
            f"TP3: {a.get('tp3')} | RR {a.get('rr_tp3')}",
        ]
    if a.get("pattern_notes"):
        lines += ["", "Price Action:"] + [f"- {x}" for x in a["pattern_notes"]]
    lines += ["", "Powody:"] + [f"- {r}" for r in a.get("reasons", [])[:14]]

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


def format_move_alert(move: dict) -> str:
    icon = "🚀" if move.get("direction") == "UP" else "💥"
    direction = "MOCNY RUCH W GÓRĘ" if move.get("direction") == "UP" else "MOCNY RUCH W DÓŁ"
    return "\n".join([
        f"{icon} <b>GOLD MOVE ALERT — {direction}</b>",
        f"Symbol: {move.get('symbol')} | Interwał: {move.get('interval')}",
        f"Poziom: {move.get('close')} | Zmiana świecy: {move.get('move_points')} pkt",
        f"Body/ATR: {move.get('body_atr')} | Range/ATR: {move.get('range_atr')}",
        f"Jakość ruchu: {move.get('severity')} | Body ratio: {move.get('body_ratio')}",
        "",
        "⚠️ To jest alert zmienności, nie automatyczny sygnał BUY/SELL.",
    ])
