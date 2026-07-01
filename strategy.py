import os
from indicators import ema, rsi, atr, macd


def last_valid(items):
    for x in reversed(items):
        if x is not None:
            return x
    return None


def trend_from_emas(candles):
    closes = [c['close'] for c in candles]
    e50 = last_valid(ema(closes, 50))
    e200 = last_valid(ema(closes, 200))
    price = closes[-1]
    if not e50 or not e200:
        return 'UNKNOWN'
    if price > e50 > e200:
        return 'UP'
    if price < e50 < e200:
        return 'DOWN'
    return 'NEUTRAL'


def recent_structure(candles, lookback=24):
    recent = candles[-lookback:]
    highs = [c['high'] for c in recent]
    lows = [c['low'] for c in recent]
    return {
        'local_high': max(highs),
        'local_low': min(lows),
        'last_high': recent[-1]['high'],
        'last_low': recent[-1]['low'],
    }


def rr(entry, sl, tp):
    risk = abs(entry - sl)
    return round(abs(tp - entry) / risk, 2) if risk else None


def round_price(x):
    return round(float(x), 2) if x is not None else None


def build_watch_plan(price, h1_atr, struct, h1_trend, h4_trend, d1_trend):
    """Warunkowy plan obserwacji, także przy NO TRADE."""
    if not h1_atr:
        h1_atr = max(price * 0.004, 10)

    resistance = struct['local_high']
    support = struct['local_low']
    buffer = max(0.15 * h1_atr, 3)

    buy_trigger = resistance + buffer
    sell_trigger = support - buffer

    buy_sl = max(support - 0.35 * h1_atr, buy_trigger - 1.5 * h1_atr)
    sell_sl = min(resistance + 0.35 * h1_atr, sell_trigger + 1.5 * h1_atr)

    buy_risk = buy_trigger - buy_sl
    sell_risk = sell_sl - sell_trigger

    return {
        'support': round_price(support),
        'resistance': round_price(resistance),
        'buy_above': round_price(buy_trigger),
        'buy_sl': round_price(buy_sl),
        'buy_tp1': round_price(buy_trigger + 2 * buy_risk),
        'buy_tp2': round_price(buy_trigger + 3 * buy_risk),
        'sell_below': round_price(sell_trigger),
        'sell_sl': round_price(sell_sl),
        'sell_tp1': round_price(sell_trigger - 2 * sell_risk),
        'sell_tp2': round_price(sell_trigger - 3 * sell_risk),
        'comment': _watch_comment(h1_trend, h4_trend, d1_trend),
    }


def _watch_comment(h1_trend, h4_trend, d1_trend):
    if d1_trend == 'DOWN' and h4_trend != 'UP':
        return 'Preferowany jest SELL po wybiciu wsparcia albo retest oporu. BUY tylko po wyraźnym wybiciu oporu.'
    if d1_trend == 'UP' and h4_trend != 'DOWN':
        return 'Preferowany jest BUY po wybiciu oporu albo obronie wsparcia. SELL tylko po utracie wsparcia.'
    return 'Brak zgodności trendów. Czekaj na wybicie wsparcia/oporu i retest.'


def analyze(snapshot):
    symbol = snapshot['symbol']
    h1, h4, d1 = snapshot['h1'], snapshot['h4'], snapshot['d1']
    closes = [c['close'] for c in h1]
    price = closes[-1]
    h1_rsi = last_valid(rsi(closes, 14))
    h1_atr = last_valid(atr(h1, 14))
    _, _, hist = macd(closes)
    macd_hist = last_valid(hist)
    h1_trend = trend_from_emas(h1)
    h4_trend = trend_from_emas(h4)
    d1_trend = trend_from_emas(d1)
    struct = recent_structure(h1)

    buy_score = 0
    sell_score = 0
    buy_reasons = []
    sell_reasons = []

    if d1_trend == 'UP':
        buy_score += 20; buy_reasons.append('D1 trend wzrostowy')
    if h4_trend == 'UP':
        buy_score += 25; buy_reasons.append('H4 trend wzrostowy')
    if h1_trend == 'UP':
        buy_score += 15; buy_reasons.append('H1 trend wzrostowy')
    if h1_rsi and 50 <= h1_rsi <= 70:
        buy_score += 15; buy_reasons.append(f'RSI H1 wspiera BUY ({h1_rsi:.1f})')
    if macd_hist and macd_hist > 0:
        buy_score += 10; buy_reasons.append('MACD momentum dodatnie')
    if price > struct['local_high'] * 0.998:
        buy_score += 10; buy_reasons.append('Cena blisko wybicia lokalnego oporu')
    if h1_atr:
        buy_score += 5; buy_reasons.append('ATR dostępny do SL/TP')

    if d1_trend == 'DOWN':
        sell_score += 20; sell_reasons.append('D1 trend spadkowy')
    if h4_trend == 'DOWN':
        sell_score += 25; sell_reasons.append('H4 trend spadkowy')
    if h1_trend == 'DOWN':
        sell_score += 15; sell_reasons.append('H1 trend spadkowy')
    if h1_rsi and 30 <= h1_rsi <= 50:
        sell_score += 15; sell_reasons.append(f'RSI H1 wspiera SELL ({h1_rsi:.1f})')
    if macd_hist and macd_hist < 0:
        sell_score += 10; sell_reasons.append('MACD momentum ujemne')
    if price < struct['local_low'] * 1.002:
        sell_score += 10; sell_reasons.append('Cena blisko wybicia lokalnego wsparcia')
    if h1_atr:
        sell_score += 5; sell_reasons.append('ATR dostępny do SL/TP')

    min_score = int(os.getenv('MIN_SCORE', '70'))
    signal = 'NO TRADE'
    score = max(buy_score, sell_score)
    reasons = ['Brak wystarczającej przewagi']
    entry = sl = tp1 = tp2 = None

    if buy_score >= min_score and buy_score > sell_score and h1_atr:
        signal = 'BUY'; score = buy_score; reasons = buy_reasons
        entry = price
        sl = min(struct['local_low'], price - 1.4 * h1_atr)
        risk = entry - sl
        tp1 = entry + 2 * risk
        tp2 = entry + 3 * risk
    elif sell_score >= min_score and sell_score > buy_score and h1_atr:
        signal = 'SELL'; score = sell_score; reasons = sell_reasons
        entry = price
        sl = max(struct['local_high'], price + 1.4 * h1_atr)
        risk = sl - entry
        tp1 = entry - 2 * risk
        tp2 = entry - 3 * risk

    watch_plan = build_watch_plan(price, h1_atr, struct, h1_trend, h4_trend, d1_trend)

    return {
        'symbol': symbol,
        'signal': signal,
        'score': int(score),
        'min_score': min_score,
        'price': round_price(price),
        'entry': round_price(entry),
        'sl': round_price(sl),
        'tp1': round_price(tp1),
        'tp2': round_price(tp2),
        'rr1': rr(entry, sl, tp1) if entry and sl and tp1 else None,
        'rr2': rr(entry, sl, tp2) if entry and sl and tp2 else None,
        'trend_h1': h1_trend,
        'trend_h4': h4_trend,
        'trend_d1': d1_trend,
        'rsi_h1': round(h1_rsi, 1) if h1_rsi else None,
        'atr_h1': round(h1_atr, 2) if h1_atr else None,
        'reasons': reasons,
        'watch_plan': watch_plan,
    }
