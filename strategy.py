import os, math
from data_provider import fetch_ohlc
from indicators import enrich
from patterns import candle_patterns

INTERVALS = {"m15": "15min", "h1": "1h", "h4": "4h", "d1": "1day"}

def trend(row):
    if row.close > row.ema50 > row.ema200:
        return "UP"
    if row.close < row.ema50 < row.ema200:
        return "DOWN"
    return "NEUTRAL"

def levels(df, lookback=40):
    sub = df.tail(lookback)
    return float(sub.low.min()), float(sub.high.max())

def rr(entry, sl, tp):
    risk = abs(entry - sl)
    return None if risk == 0 else round(abs(tp-entry)/risk, 2)

def roundp(x):
    return round(float(x), 2) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None

def analyze():
    symbol = os.getenv("SYMBOL", "XAU/USD")
    min_score = int(os.getenv("MIN_SCORE", "80"))
    min_rr = float(os.getenv("MIN_RR", "2.0"))
    macro_block = os.getenv("MACRO_BLOCK", "false").lower() == "true"

    dfs = {k: enrich(fetch_ohlc(symbol, interval, 240)) for k, interval in INTERVALS.items()}
    last = {k: v.iloc[-1] for k, v in dfs.items()}
    tr = {k: trend(last[k]) for k in last}
    price = float(last["h1"].close)
    atr = float(last["h1"].atr14) if not math.isnan(float(last["h1"].atr14)) else max(price*0.004, 10)
    support, resistance = levels(dfs["h1"])
    pats = candle_patterns(dfs["h1"])

    buy_score = 0; sell_score = 0; buy_reasons=[]; sell_reasons=[]
    if tr["d1"] == "UP": buy_score += 15; buy_reasons.append("D1 trend wzrostowy")
    if tr["d1"] == "DOWN": sell_score += 15; sell_reasons.append("D1 trend spadkowy")
    if tr["h4"] == "UP": buy_score += 20; buy_reasons.append("H4 trend wzrostowy")
    if tr["h4"] == "DOWN": sell_score += 20; sell_reasons.append("H4 trend spadkowy")
    if tr["h1"] == "UP": buy_score += 20; buy_reasons.append("H1 trend wzrostowy")
    if tr["h1"] == "DOWN": sell_score += 20; sell_reasons.append("H1 trend spadkowy")
    if last["m15"].close > last["m15"].ema20: buy_score += 5; buy_reasons.append("M15 powyżej EMA20")
    if last["m15"].close < last["m15"].ema20: sell_score += 5; sell_reasons.append("M15 poniżej EMA20")

    rsi = float(last["h1"].rsi14); adx = float(last["h1"].adx14); macdh = float(last["h1"].macd_hist)
    if 45 <= rsi <= 68: buy_score += 10; buy_reasons.append(f"RSI H1 korzystny dla BUY: {rsi:.1f}")
    if 32 <= rsi <= 55: sell_score += 10; sell_reasons.append(f"RSI H1 korzystny dla SELL: {rsi:.1f}")
    if macdh > 0: buy_score += 10; buy_reasons.append("MACD histogram dodatni")
    if macdh < 0: sell_score += 10; sell_reasons.append("MACD histogram ujemny")
    if adx >= 18:
        buy_score += 5; sell_score += 5
    if "bullish_engulfing" in pats or "pin_bar_bullish" in pats:
        buy_score += 10; buy_reasons.append("Price Action wspiera BUY")
    if "bearish_engulfing" in pats or "pin_bar_bearish" in pats:
        sell_score += 10; sell_reasons.append("Price Action wspiera SELL")

    # DXY simplified: if available, rising DXY weakens BUY and supports SELL
    try:
        dxy_symbol = os.getenv("DXY_SYMBOL", "DXY")
        dxy = enrich(fetch_ohlc(dxy_symbol, "1h", 120))
        dxy_last = dxy.iloc[-1]
        if dxy_last.close > dxy_last.ema50:
            sell_score += 5; sell_reasons.append("DXY powyżej EMA50 — presja na złoto")
        else:
            buy_score += 5; buy_reasons.append("DXY poniżej EMA50 — wsparcie dla złota")
    except Exception:
        pass

    if macro_block:
        buy_score -= 30; sell_score -= 30
        buy_reasons.append("MACRO_BLOCK aktywny")
        sell_reasons.append("MACRO_BLOCK aktywny")

    if buy_score > sell_score:
        sig, score, reasons = "BUY", max(0, min(100, buy_score)), buy_reasons
        entry = price
        sl = min(support, price - 1.3*atr)
        tp1 = price + 2*abs(price-sl); tp2 = price + 3*abs(price-sl); tp3 = price + 4*abs(price-sl)
    elif sell_score > buy_score:
        sig, score, reasons = "SELL", max(0, min(100, sell_score)), sell_reasons
        entry = price
        sl = max(resistance, price + 1.3*atr)
        tp1 = price - 2*abs(sl-price); tp2 = price - 3*abs(sl-price); tp3 = price - 4*abs(sl-price)
    else:
        sig, score, reasons = "NO TRADE", 0, ["Brak przewagi jednej strony"]
        entry=sl=tp1=tp2=tp3=None

    rr2 = rr(entry, sl, tp2) if entry else None
    if sig != "NO TRADE" and (score < min_score or rr2 is None or rr2 < min_rr):
        reasons.append(f"Sygnał zablokowany: score {score} < {min_score} lub RR {rr2} < {min_rr}")
        sig = "NO TRADE"

    watch_plan = [
        f"BUY dopiero po wybiciu i utrzymaniu powyżej {roundp(resistance)}",
        f"SELL dopiero po utracie i retestcie poniżej {roundp(support)}",
        f"Strefa neutralna: {roundp(support)}–{roundp(resistance)}",
    ]
    return {
        "symbol": symbol, "signal": sig, "score": score, "price": roundp(price),
        "trend_m15": tr["m15"], "trend_h1": tr["h1"], "trend_h4": tr["h4"], "trend_d1": tr["d1"],
        "rsi_h1": round(rsi,1), "adx_h1": roundp(adx), "atr_h1": roundp(atr),
        "support": roundp(support), "resistance": roundp(resistance),
        "entry": roundp(entry), "sl": roundp(sl), "tp1": roundp(tp1), "tp2": roundp(tp2), "tp3": roundp(tp3), "rr_tp2": rr2,
        "patterns_h1": pats, "reasons": reasons or ["Brak wystarczającej przewagi"], "watch_plan": watch_plan,
    }
