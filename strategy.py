from indicators import ema, rsi, atr


def round_price(x):
    return None if x is None else round(float(x), 2)


def recent_high(candles, lookback=12):
    return max(c["high"] for c in candles[-lookback:])


def recent_low(candles, lookback=12):
    return min(c["low"] for c in candles[-lookback:])


def trend_for(candles):
    closes = [c["close"] for c in candles]
    e50 = ema(closes, 50)[-1]
    e200 = ema(closes, 200)[-1] if len(closes) >= 200 else None
    price = closes[-1]
    # Przy 150 świecach używamy EMA100 jako zastępstwa długiego filtra.
    long_ema = e200 if e200 is not None else ema(closes, 100)[-1]
    if e50 is None or long_ema is None:
        return "UNKNOWN", e50, long_ema
    if price > e50 > long_ema:
        return "UP", e50, long_ema
    if price < e50 < long_ema:
        return "DOWN", e50, long_ema
    return "SIDE", e50, long_ema


def rr(entry, sl, tp):
    risk = abs(entry - sl)
    if risk == 0:
        return 0
    return round(abs(tp - entry) / risk, 2)


def analyze_gold(symbol: str, data: dict):
    h1 = data["H1"]
    h4 = data["H4"]
    d1 = data["D1"]
    price = h1[-1]["close"]

    h1_closes = [c["close"] for c in h1]
    h1_rsi = rsi(h1_closes, 14)[-1]
    h1_atr = atr(h1, 14)[-1]
    h1_trend, h1_ema50, h1_ema_long = trend_for(h1)
    h4_trend, _, _ = trend_for(h4)
    d1_trend, _, _ = trend_for(d1)

    score_buy = 0
    score_sell = 0
    reasons_buy = []
    reasons_sell = []

    if d1_trend in ["UP", "SIDE"]:
        score_buy += 15; reasons_buy.append(f"D1 nie blokuje BUY ({d1_trend})")
    if h4_trend == "UP":
        score_buy += 25; reasons_buy.append("H4 trend wzrostowy")
    if h1_trend == "UP":
        score_buy += 20; reasons_buy.append("H1 trend wzrostowy")
    if h1_rsi is not None and 50 <= h1_rsi <= 70:
        score_buy += 15; reasons_buy.append(f"RSI H1 w strefie siły: {round(h1_rsi, 1)}")

    if d1_trend in ["DOWN", "SIDE"]:
        score_sell += 15; reasons_sell.append(f"D1 nie blokuje SELL ({d1_trend})")
    if h4_trend == "DOWN":
        score_sell += 25; reasons_sell.append("H4 trend spadkowy")
    if h1_trend == "DOWN":
        score_sell += 20; reasons_sell.append("H1 trend spadkowy")
    if h1_rsi is not None and 30 <= h1_rsi <= 50:
        score_sell += 15; reasons_sell.append(f"RSI H1 w strefie podaży: {round(h1_rsi, 1)}")

    # Price action: wybicie ostatnich 12 świec z wyłączeniem aktualnej
    prev_h1 = h1[:-1]
    last_close = price
    high_level = recent_high(prev_h1, 12)
    low_level = recent_low(prev_h1, 12)

    if last_close > high_level:
        score_buy += 15; reasons_buy.append(f"Wybicie lokalnego oporu H1: {round_price(high_level)}")
    if last_close < low_level:
        score_sell += 15; reasons_sell.append(f"Wybicie lokalnego wsparcia H1: {round_price(low_level)}")

    if h1_atr:
        score_buy += 10; score_sell += 10
        reasons_buy.append(f"ATR H1 dostępny: {round(h1_atr, 2)}")
        reasons_sell.append(f"ATR H1 dostępny: {round(h1_atr, 2)}")

    min_score = 70
    signal = "NO TRADE"
    score = max(score_buy, score_sell)
    reasons = ["Brak przewagi minimum 70/100"]
    entry = price
    sl = tp1 = tp2 = None

    if score_buy >= min_score and score_buy > score_sell and h1_atr:
        signal = "BUY"
        score = score_buy
        reasons = reasons_buy
        sl = min(recent_low(h1, 10), price - 1.2 * h1_atr)
        risk = price - sl
        tp1 = price + 2 * risk
        tp2 = price + 3 * risk
    elif score_sell >= min_score and score_sell > score_buy and h1_atr:
        signal = "SELL"
        score = score_sell
        reasons = reasons_sell
        sl = max(recent_high(h1, 10), price + 1.2 * h1_atr)
        risk = sl - price
        tp1 = price - 2 * risk
        tp2 = price - 3 * risk

    return {
        "symbol": symbol,
        "signal": signal,
        "score": int(score),
        "price": round_price(price),
        "entry": round_price(entry) if signal != "NO TRADE" else None,
        "sl": round_price(sl),
        "tp1": round_price(tp1),
        "tp2": round_price(tp2),
        "rr1": rr(entry, sl, tp1) if sl and tp1 else None,
        "rr2": rr(entry, sl, tp2) if sl and tp2 else None,
        "trend_h1": h1_trend,
        "trend_h4": h4_trend,
        "trend_d1": d1_trend,
        "rsi_h1": round(h1_rsi, 1) if h1_rsi else None,
        "atr_h1": round(h1_atr, 2) if h1_atr else None,
        "reasons": reasons,
    }
