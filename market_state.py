"""
Gold AI Bot v6 — Institutional Smart Money
Modul: market_state.py
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float


def candle_range(c: Candle) -> float:
    return max(c.high - c.low, 0.0)


def candle_body(c: Candle) -> float:
    return c.close - c.open


def body_ratio(c: Candle) -> float:
    r = candle_range(c)
    return abs(candle_body(c)) / r if r > 0 else 0.0


def atr_multiple(c: Candle, atr: float) -> float:
    r = candle_range(c)
    return r / atr if atr and atr > 0 else 0.0


def detect_high_volatility(c: Candle, atr: float, threshold: float = 1.20) -> Optional[str]:
    mult = atr_multiple(c, atr)
    if mult >= threshold:
        direction = "UP" if c.close > c.open else "DOWN"
        return f"⚡ HIGH VOLATILITY {direction}: świeca {mult:.2f}x ATR"
    return None


def detect_breakout(c: Candle, atr: float, threshold_atr: float = 0.80, threshold_body: float = 0.65) -> Optional[str]:
    mult = atr_multiple(c, atr)
    br = body_ratio(c)
    if mult >= threshold_atr and br >= threshold_body:
        direction = "UP" if c.close > c.open else "DOWN"
        return f"🚨 BREAKOUT {direction}: body {br:.0%}, range {mult:.2f}x ATR"
    return None


def detect_liquidity_sweep(last: Candle, prev_high: float, prev_low: float) -> Optional[str]:
    if last.high > prev_high and last.close < prev_high:
        return "🧲 Liquidity sweep nad oporem — możliwe odrzucenie wzrostów"
    if last.low < prev_low and last.close > prev_low:
        return "🧲 Liquidity sweep pod wsparciem — możliwe odrzucenie spadków"
    return None


def detect_bos_choch(last: Candle, swing_high: float, swing_low: float, previous_trend: str) -> Optional[str]:
    if last.close > swing_high:
        if previous_trend == "DOWN":
            return "🔄 CHOCH UP — możliwa zmiana kierunku na wzrostowy"
        return "📈 BOS UP — kontynuacja struktury wzrostowej"

    if last.close < swing_low:
        if previous_trend == "UP":
            return "🔄 CHOCH DOWN — możliwa zmiana kierunku na spadkowy"
        return "📉 BOS DOWN — kontynuacja struktury spadkowej"

    return None


def detect_fvg(c1: Candle, c2: Candle, c3: Candle) -> Optional[str]:
    if c3.low > c1.high:
        return f"🟩 Bullish FVG: {c1.high:.2f}–{c3.low:.2f}"
    if c3.high < c1.low:
        return f"🟥 Bearish FVG: {c3.high:.2f}–{c1.low:.2f}"
    return None


def suggest_trade_management(signal: str, entry: float, price: float, sl: float, atr_h1: float) -> str:
    if signal == "SELL":
        profit_points = entry - price
        risk_points = sl - entry
        if price > sl:
            return "❌ SELL zanegowany — cena przekroczyła SL"
        if profit_points > risk_points:
            return f"🛡️ SELL: rozważ SL na BE / lekki zysk: {entry:.2f}"
        if atr_h1 and profit_points > 0.75 * atr_h1:
            return "🔒 SELL: rozważ ciaśniejszy SL nad ostatnim H1 high albo BE"
        return "⏳ SELL aktywny, ale bez przewagi do agresywnego prowadzenia"

    if signal == "BUY":
        profit_points = price - entry
        risk_points = entry - sl
        if price < sl:
            return "❌ BUY zanegowany — cena spadła poniżej SL"
        if profit_points > risk_points:
            return f"🛡️ BUY: rozważ SL na BE / lekki zysk: {entry:.2f}"
        if atr_h1 and profit_points > 0.75 * atr_h1:
            return "🔒 BUY: rozważ ciaśniejszy SL pod ostatnim H1 low albo BE"
        return "⏳ BUY aktywny, ale bez przewagi do agresywnego prowadzenia"

    return "Brak aktywnego kierunku do prowadzenia pozycji"


def classify_market_state(
    price: float,
    entry: float,
    sl: float,
    signal: str,
    score: int,
    atr_h1: float,
    last_candle: Candle,
    trend_m15: str,
    trend_h1: str,
    trend_h4: str,
    trend_d1: str,
    prev_high: Optional[float] = None,
    prev_low: Optional[float] = None,
    swing_high: Optional[float] = None,
    swing_low: Optional[float] = None,
    previous_trend: str = "NEUTRAL",
    last_3_candles: Optional[List[Candle]] = None,
) -> Dict[str, Any]:

    messages = []

    for detector in (
        detect_high_volatility(last_candle, atr_h1),
        detect_breakout(last_candle, atr_h1),
    ):
        if detector:
            messages.append(detector)

    if prev_high is not None and prev_low is not None:
        sweep = detect_liquidity_sweep(last_candle, prev_high, prev_low)
        if sweep:
            messages.append(sweep)

    if swing_high is not None and swing_low is not None:
        structure = detect_bos_choch(last_candle, swing_high, swing_low, previous_trend)
        if structure:
            messages.append(structure)

    if last_3_candles and len(last_3_candles) >= 3:
        fvg = detect_fvg(last_3_candles[-3], last_3_candles[-2], last_3_candles[-1])
        if fvg:
            messages.append(fvg)

    if signal == "SELL" and price > sl:
        state = "SIGNAL_INVALIDATED"
        messages.append("❌ SELL INVALIDATED — cena powyżej SL")
    elif signal == "BUY" and price < sl:
        state = "SIGNAL_INVALIDATED"
        messages.append("❌ BUY INVALIDATED — cena poniżej SL")
    elif score < 70:
        state = "WAIT"
        messages.append(f"🟡 WAIT — score {score}/100 za niski")
    elif trend_h1 == "NEUTRAL" or trend_h4 == "NEUTRAL":
        state = "WAIT"
        messages.append(f"🟡 WAIT — trend H1/H4 niejednoznaczny: {trend_h1}/{trend_h4}")
    elif signal in ["BUY", "SELL"]:
        state = signal
        messages.append(f"✅ {signal} aktywny | Score {score}/100")
    else:
        state = "WAIT"
        messages.append("🟡 WAIT — brak czystego sygnału")

    messages.append(suggest_trade_management(signal, entry, price, sl, atr_h1))

    return {
        "state": state,
        "message": "\n".join(messages),
        "score": score,
        "price": price,
        "entry": entry,
        "sl": sl,
    }


def format_telegram_market_state(result: Dict[str, Any]) -> str:
    return (
        "\n\n━━━━━━━━━━━━━━\n"
        "🧠 GOLD AI BOT v6 — MARKET STATE\n"
        f"Status: {result['state']}\n"
        f"Cena: {result['price']:.2f}\n"
        f"Entry: {result['entry']:.2f}\n"
        f"SL: {result['sl']:.2f}\n\n"
        f"{result['message']}"
    )
