def ema(values, period):
    if not values or len(values) < period:
        return []
    k = 2 / (period + 1)
    out = []
    prev = sum(values[:period]) / period
    out = [None] * (period - 1) + [prev]
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values, period=14):
    if len(values) <= period:
        return []
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out = [None] * period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss else 999
        out.append(100 - (100 / (1 + rs)))
    return out


def atr(candles, period=14):
    if len(candles) <= period:
        return []
    trs = []
    for i in range(1, len(candles)):
        high = candles[i]['high']
        low = candles[i]['low']
        prev_close = candles[i-1]['close']
        trs.append(max(high-low, abs(high-prev_close), abs(low-prev_close)))
    out = [None] * period
    avg = sum(trs[:period]) / period
    out.append(avg)
    for tr in trs[period:]:
        avg = (avg * (period - 1) + tr) / period
        out.append(avg)
    return out


def macd(values, fast=12, slow=26, signal=9):
    ef = ema(values, fast)
    es = ema(values, slow)
    if not ef or not es:
        return [], [], []
    line = []
    for a,b in zip(ef, es):
        line.append(None if a is None or b is None else a-b)
    valid = [x for x in line if x is not None]
    sig_valid = ema(valid, signal)
    sig = [None] * (len(line) - len(sig_valid)) + sig_valid
    hist = [None if a is None or b is None else a-b for a,b in zip(line, sig)]
    return line, sig, hist
