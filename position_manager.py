"""
Gold AI Bot v6 — Position Manager with automatic SL/TP

Adds Telegram command:
    /position SELL 4097
    /position BUY 4097

Optional:
    /positions
    /close 1
    /clear_positions

The module stores open positions in positions.json and calculates SL/TP from ATR.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


POSITIONS_FILE = Path(os.getenv("POSITIONS_FILE", "positions.json"))
DEFAULT_ATR = float(os.getenv("DEFAULT_ATR_H1", "12.0"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.5"))


def _load_positions() -> List[Dict[str, Any]]:
    if not POSITIONS_FILE.exists():
        return []
    try:
        data = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_positions(positions: List[Dict[str, Any]]) -> None:
    POSITIONS_FILE.write_text(
        json.dumps(positions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def auto_sl_tp(side: str, entry: float, atr: Optional[float] = None) -> Dict[str, float]:
    """
    Automatic SL/TP calculation based on ATR.

    SELL:
      SL above entry
      TP below entry

    BUY:
      SL below entry
      TP above entry
    """
    side = side.upper().strip()
    atr = float(atr or DEFAULT_ATR)

    if atr <= 0:
        atr = DEFAULT_ATR

    if side == "SELL":
        sl = entry + atr * SL_ATR_MULT
        risk = sl - entry
        tp1 = entry - risk * 1.0
        tp2 = entry - risk * 2.0
        tp3 = entry - risk * 3.0

    elif side == "BUY":
        sl = entry - atr * SL_ATR_MULT
        risk = entry - sl
        tp1 = entry + risk * 1.0
        tp2 = entry + risk * 2.0
        tp3 = entry + risk * 3.0

    else:
        raise ValueError("Side must be BUY or SELL")

    return {
        "entry": round(entry, 2),
        "atr": round(atr, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp3": round(tp3, 2),
        "risk": round(risk, 2),
    }


def get_current_atr_h1(market_state: Optional[Dict[str, Any]] = None) -> float:
    """
    Tries to read ATR H1 from your bot's current market state.
    If unavailable, returns DEFAULT_ATR.
    """
    if not market_state:
        return DEFAULT_ATR

    possible_keys = [
        "atr_h1",
        "ATR_H1",
        "atr",
        "ATR",
    ]

    for key in possible_keys:
        value = market_state.get(key)
        if value is not None:
            try:
                value = float(value)
                return value if value > 0 else DEFAULT_ATR
            except Exception:
                pass

    try:
        value = float(market_state.get("h1", {}).get("atr"))
        return value if value > 0 else DEFAULT_ATR
    except Exception:
        return DEFAULT_ATR


def parse_position_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Accepts:
      /position SELL 4097
      /position BUY 4097.50
      position sell 4097
    """
    text = text.strip()
    pattern = r"^/?position\s+(buy|sell)\s+([0-9]+(?:[.,][0-9]+)?)$"
    match = re.match(pattern, text, flags=re.IGNORECASE)

    if not match:
        return None

    side = match.group(1).upper()
    entry = float(match.group(2).replace(",", "."))

    return {"side": side, "entry": entry}


def add_position(side: str, entry: float, atr: Optional[float] = None) -> Dict[str, Any]:
    calc = auto_sl_tp(side, entry, atr)

    positions = _load_positions()
    position_id = int(time.time())

    position = {
        "id": position_id,
        "symbol": "XAU/USD",
        "side": side.upper(),
        "entry": calc["entry"],
        "sl": calc["sl"],
        "tp1": calc["tp1"],
        "tp2": calc["tp2"],
        "tp3": calc["tp3"],
        "risk": calc["risk"],
        "atr": calc["atr"],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "OPEN",
    }

    positions.append(position)
    _save_positions(positions)

    return position


def format_position(position: Dict[str, Any]) -> str:
    return (
        "📌 ZAPISANO POZYCJĘ\n"
        f"Symbol: {position['symbol']}\n"
        f"Kierunek: {position['side']}\n"
        f"Entry: {position['entry']}\n"
        f"SL: {position['sl']}\n"
        f"TP1: {position['tp1']} | RR 1.0\n"
        f"TP2: {position['tp2']} | RR 2.0\n"
        f"TP3: {position['tp3']} | RR 3.0\n"
        f"ATR: {position['atr']} | Ryzyko: {position['risk']} pkt\n\n"
        "⚠️ Przepisz poziomy SL/TP ręcznie do brokera. "
        "Bot tylko liczy i zapamiętuje pozycję."
    )


def format_positions() -> str:
    positions = [p for p in _load_positions() if p.get("status") == "OPEN"]

    if not positions:
        return "Brak zapisanych otwartych pozycji."

    lines = ["📊 OTWARTE POZYCJE"]
    for idx, p in enumerate(positions, start=1):
        lines.append(
            f"\n{idx}. {p['side']} XAU/USD @ {p['entry']}\n"
            f"SL: {p['sl']} | TP1: {p['tp1']} | TP2: {p['tp2']} | TP3: {p['tp3']}\n"
            f"ATR: {p['atr']} | ID: {p['id']}"
        )

    return "\n".join(lines)


def close_position(index: int) -> str:
    positions = _load_positions()
    open_positions = [p for p in positions if p.get("status") == "OPEN"]

    if index < 1 or index > len(open_positions):
        return "Nie znaleziono pozycji o takim numerze."

    target = open_positions[index - 1]
    for p in positions:
        if p.get("id") == target.get("id"):
            p["status"] = "CLOSED"
            p["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            break

    _save_positions(positions)
    return f"Zamknięto w pamięci bota pozycję {index}: {target['side']} @ {target['entry']}"


def clear_positions() -> str:
    positions = _load_positions()
    for p in positions:
        if p.get("status") == "OPEN":
            p["status"] = "CLOSED"
            p["closed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    _save_positions(positions)
    return "Wszystkie otwarte pozycje oznaczono jako zamknięte."


def handle_position_message(text: str, market_state: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Main handler to plug into your Telegram update loop.

    Returns response text or None if message is not a position command.
    """
    clean = text.strip()

    parsed = parse_position_command(clean)
    if parsed:
        atr = get_current_atr_h1(market_state)
        position = add_position(parsed["side"], parsed["entry"], atr)
        return format_position(position)

    if clean.lower() in {"/positions", "positions"}:
        return format_positions()

    if clean.lower() in {"/clear_positions", "clear_positions"}:
        return clear_positions()

    close_match = re.match(r"^/close\s+([0-9]+)$", clean, flags=re.IGNORECASE)
    if close_match:
        return close_position(int(close_match.group(1)))

    return None
