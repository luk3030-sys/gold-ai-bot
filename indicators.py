from typing import List, Dict, Optional, Tuple


def sma(values: List[float], period: int) -> List[Optional[float]]:
    out = []
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(values[i+1-period:i+1]) / period)
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    if not values:
        return []
    k = 2 / (period + 1)
    out: List[Optional[float]] = []
    prev = None
    for i, v in enumerate(values):
        if i + 1 < period:
            out.append(None)
            continue
        if prev is None:
            prev = sum(values[i+1-period:i+1]) / period
        else:
            prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        ch = values[i] - values[i-1]
        gains.append(max(ch, 0))
        losses.append(abs(min(ch, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    out[period] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        ch = values[i] - values[i-1]
        gain = max(ch, 0)
        loss = abs(min(ch, 0))
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def atr(candles: List[Dict], period: int = 14) -> List[Optional[float]]:
    trs = []
    prev_close = None
    for c in candles:
        high, low, close = c['high'], c['low'], c['close']
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
        prev_close = close
    out = [None] * len(candles)
    if len(trs) < period:
        return out
    val = sum(trs[:period]) / period
    out[period - 1] = val
    for i in range(period, len(trs)):
        val = (val * (period - 1) + trs[i]) / period
        out[i] = val
    return out


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    ef = ema(values, fast)
    es = ema(values, slow)
    macd_line = [(a - b) if a is not None and b is not None else None for a, b in zip(ef, es)]
    valid = [x for x in macd_line if x is not None]
    sig_valid = ema(valid, signal) if valid else []
    sig: List[Optional[float]] = []
    j = 0
    for x in macd_line:
        if x is None:
            sig.append(None)
        else:
            sig.append(sig_valid[j] if j < len(sig_valid) else None)
            j += 1
    hist = [(m - s) if m is not None and s is not None else None for m, s in zip(macd_line, sig)]
    return macd_line, sig, hist


def bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    out_mid, out_upper, out_lower, out_width = [], [], [], []
    for i in range(len(values)):
        if i + 1 < period:
            out_mid.append(None); out_upper.append(None); out_lower.append(None); out_width.append(None)
            continue
        window = values[i+1-period:i+1]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        sd = var ** 0.5
        upper = mean + mult * sd
        lower = mean - mult * sd
        out_mid.append(mean); out_upper.append(upper); out_lower.append(lower)
        out_width.append((upper - lower) / mean if mean else None)
    return out_mid, out_upper, out_lower, out_width


def adx(candles: List[Dict], period: int = 14) -> List[Optional[float]]:
    if len(candles) < period + 2:
        return [None] * len(candles)
    trs, plus_dm, minus_dm = [0.0], [0.0], [0.0]
    for i in range(1, len(candles)):
        cur, prev = candles[i], candles[i-1]
        up = cur['high'] - prev['high']
        down = prev['low'] - cur['low']
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(cur['high'] - cur['low'], abs(cur['high'] - prev['close']), abs(cur['low'] - prev['close'])))
    out = [None] * len(candles)
    tr14 = sum(trs[1:period+1])
    pdm14 = sum(plus_dm[1:period+1])
    mdm14 = sum(minus_dm[1:period+1])
    dxs = []
    for i in range(period, len(candles)):
        if i > period:
            tr14 = tr14 - (tr14 / period) + trs[i]
            pdm14 = pdm14 - (pdm14 / period) + plus_dm[i]
            mdm14 = mdm14 - (mdm14 / period) + minus_dm[i]
        pdi = 100 * (pdm14 / tr14) if tr14 else 0
        mdi = 100 * (mdm14 / tr14) if tr14 else 0
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0
        dxs.append(dx)
        if len(dxs) == period:
            out[i] = sum(dxs) / period
        elif len(dxs) > period:
            prev_adx = out[i-1] if out[i-1] is not None else sum(dxs[-period-1:-1]) / period
            out[i] = (prev_adx * (period - 1) + dx) / period
    return out


def candle_pattern(candles: List[Dict]) -> str:
    if len(candles) < 3:
        return 'NONE'
    p = candles[-2]
    c = candles[-1]
    p_body = abs(p['close'] - p['open'])
    c_body = abs(c['close'] - c['open'])
    c_range = max(c['high'] - c['low'], 0.0001)
    upper = c['high'] - max(c['open'], c['close'])
    lower = min(c['open'], c['close']) - c['low']
    if c['close'] > c['open'] and p['close'] < p['open'] and c['close'] >= p['open'] and c['open'] <= p['close']:
        return 'BULLISH_ENGULFING'
    if c['close'] < c['open'] and p['close'] > p['open'] and c['open'] >= p['close'] and c['close'] <= p['open']:
        return 'BEARISH_ENGULFING'
    if lower > 2 * c_body and upper < 0.35 * c_range:
        return 'PIN_BAR_BULLISH'
    if upper > 2 * c_body and lower < 0.35 * c_range:
        return 'PIN_BAR_BEARISH'
    if c['high'] < p['high'] and c['low'] > p['low']:
        return 'INSIDE_BAR'
    return 'NONE'
