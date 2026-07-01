import os
from indicators import ema, rsi, atr, macd, adx, bollinger, candle_pattern


def last_valid(items):
    for x in reversed(items):
        if x is not None:
            return x
    return None


def round_price(x):
    return round(float(x), 2) if x is not None else None


def rr(entry, sl, tp):
    risk = abs(entry - sl)
    return round(abs(tp - entry) / risk, 2) if risk else None


def trend_from_emas(candles):
    closes = [c['close'] for c in candles]
    e20 = last_valid(ema(closes, 20)); e50 = last_valid(ema(closes, 50)); e200 = last_valid(ema(closes, 200))
    price = closes[-1]
    if not e20 or not e50 or not e200:
        return 'UNKNOWN'
    if price > e20 > e50 > e200:
        return 'STRONG_UP'
    if price > e50 > e200:
        return 'UP'
    if price < e20 < e50 < e200:
        return 'STRONG_DOWN'
    if price < e50 < e200:
        return 'DOWN'
    return 'NEUTRAL'


def recent_structure(candles, lookback=36):
    recent = candles[-lookback:]
    highs = [c['high'] for c in recent]
    lows = [c['low'] for c in recent]
    return {'local_high': max(highs), 'local_low': min(lows), 'last_high': recent[-1]['high'], 'last_low': recent[-1]['low']}


def dxy_bias(dxy_h1):
    if not dxy_h1 or isinstance(dxy_h1, dict):
        return {'bias': 'UNKNOWN', 'comment': 'DXY niedostępny'}
    closes = [c['close'] for c in dxy_h1]
    e20 = last_valid(ema(closes, 20)); e50 = last_valid(ema(closes, 50))
    if not e20 or not e50:
        return {'bias': 'UNKNOWN', 'comment': 'Za mało danych DXY'}
    if closes[-1] > e20 > e50:
        return {'bias': 'USD_STRONG', 'comment': 'DXY wzrostowy — presja na złoto'}
    if closes[-1] < e20 < e50:
        return {'bias': 'USD_WEAK', 'comment': 'DXY spadkowy — wsparcie dla złota'}
    return {'bias': 'NEUTRAL', 'comment': 'DXY neutralny'}


def macro_block_active():
    # Prosty przełącznik ręczny. Ustaw MACRO_BLOCK=true w Render przed CPI/FOMC/NFP.
    return os.getenv('MACRO_BLOCK', 'false').lower() == 'true'


def build_watch_plan(price, h1_atr, struct, h1_trend, h4_trend, d1_trend):
    if not h1_atr:
        h1_atr = max(price * 0.004, 10)
    resistance = struct['local_high']; support = struct['local_low']
    buffer = max(0.18 * h1_atr, 3)
    buy_trigger = resistance + buffer; sell_trigger = support - buffer
    buy_sl = max(support - 0.35 * h1_atr, buy_trigger - 1.5 * h1_atr)
    sell_sl = min(resistance + 0.35 * h1_atr, sell_trigger + 1.5 * h1_atr)
    buy_risk = buy_trigger - buy_sl; sell_risk = sell_sl - sell_trigger
    return {
        'support': round_price(support), 'resistance': round_price(resistance),
        'buy_above': round_price(buy_trigger), 'buy_sl': round_price(buy_sl),
        'buy_tp1': round_price(buy_trigger + 2 * buy_risk), 'buy_tp2': round_price(buy_trigger + 3 * buy_risk),
        'sell_below': round_price(sell_trigger), 'sell_sl': round_price(sell_sl),
        'sell_tp1': round_price(sell_trigger - 2 * sell_risk), 'sell_tp2': round_price(sell_trigger - 3 * sell_risk),
        'comment': watch_comment(h1_trend, h4_trend, d1_trend),
    }


def watch_comment(h1_trend, h4_trend, d1_trend):
    if 'DOWN' in d1_trend and 'UP' not in h4_trend:
        return 'Preferuj SELL po wybiciu wsparcia/reteście. BUY tylko po mocnym wybiciu oporu i utrzymaniu H1.'
    if 'UP' in d1_trend and 'DOWN' not in h4_trend:
        return 'Preferuj BUY po wybiciu oporu/reteście. SELL tylko po utracie wsparcia.'
    return 'Brak pełnej zgodności trendów. Najlepsze jest czekanie na wybicie, retest i zamknięcie świecy.'


def analyze(snapshot):
    symbol = snapshot['symbol']; m15 = snapshot['m15']; h1 = snapshot['h1']; h4 = snapshot['h4']; d1 = snapshot['d1']
    closes = [c['close'] for c in h1]; price = closes[-1]
    h1_rsi = last_valid(rsi(closes, 14)); h1_atr = last_valid(atr(h1, 14))
    macd_line, sig_line, hist = macd(closes); macd_hist = last_valid(hist)
    h1_adx = last_valid(adx(h1, 14))
    _, bb_u, bb_l, bb_w = bollinger(closes, 20, 2)
    h1_bb_width = last_valid(bb_w)
    pattern_h1 = candle_pattern(h1); pattern_m15 = candle_pattern(m15)
    h1_trend = trend_from_emas(h1); h4_trend = trend_from_emas(h4); d1_trend = trend_from_emas(d1)
    struct = recent_structure(h1)
    dxy = dxy_bias(snapshot.get('dxy_h1'))

    buy_score = 0; sell_score = 0; buy_reasons = []; sell_reasons = []
    def add_buy(points, reason):
        nonlocal buy_score; buy_score += points; buy_reasons.append(reason)
    def add_sell(points, reason):
        nonlocal sell_score; sell_score += points; sell_reasons.append(reason)

    if d1_trend in ['UP', 'STRONG_UP']: add_buy(18, f'D1 {d1_trend}')
    if d1_trend in ['DOWN', 'STRONG_DOWN']: add_sell(18, f'D1 {d1_trend}')
    if h4_trend in ['UP', 'STRONG_UP']: add_buy(22, f'H4 {h4_trend}')
    if h4_trend in ['DOWN', 'STRONG_DOWN']: add_sell(22, f'H4 {h4_trend}')
    if h1_trend in ['UP', 'STRONG_UP']: add_buy(15, f'H1 {h1_trend}')
    if h1_trend in ['DOWN', 'STRONG_DOWN']: add_sell(15, f'H1 {h1_trend}')

    if h1_rsi and 50 <= h1_rsi <= 68: add_buy(10, f'RSI H1 wspiera BUY ({h1_rsi:.1f})')
    if h1_rsi and 32 <= h1_rsi <= 50: add_sell(10, f'RSI H1 wspiera SELL ({h1_rsi:.1f})')
    if macd_hist and macd_hist > 0: add_buy(8, 'MACD dodatni')
    if macd_hist and macd_hist < 0: add_sell(8, 'MACD ujemny')
    if h1_adx and h1_adx >= 20:
        if h1_trend in ['UP', 'STRONG_UP']: add_buy(8, f'ADX potwierdza trend ({h1_adx:.1f})')
        if h1_trend in ['DOWN', 'STRONG_DOWN']: add_sell(8, f'ADX potwierdza trend ({h1_adx:.1f})')
    if price > struct['local_high'] * 0.998: add_buy(8, 'Cena blisko wybicia oporu H1')
    if price < struct['local_low'] * 1.002: add_sell(8, 'Cena blisko wybicia wsparcia H1')

    if pattern_h1 in ['BULLISH_ENGULFING', 'PIN_BAR_BULLISH']: add_buy(8, f'Price Action H1: {pattern_h1}')
    if pattern_h1 in ['BEARISH_ENGULFING', 'PIN_BAR_BEARISH']: add_sell(8, f'Price Action H1: {pattern_h1}')
    if pattern_m15 in ['BULLISH_ENGULFING', 'PIN_BAR_BULLISH']: add_buy(4, f'Potwierdzenie M15: {pattern_m15}')
    if pattern_m15 in ['BEARISH_ENGULFING', 'PIN_BAR_BEARISH']: add_sell(4, f'Potwierdzenie M15: {pattern_m15}')

    if dxy['bias'] == 'USD_WEAK': add_buy(6, dxy['comment'])
    if dxy['bias'] == 'USD_STRONG': add_sell(6, dxy['comment'])
    if h1_atr: add_buy(4, 'ATR dostępny do SL/TP'); add_sell(4, 'ATR dostępny do SL/TP')
    if macro_block_active():
        buy_score -= 25; sell_score -= 25
        buy_reasons.append('Blokada makro aktywna — brak nowych wejść')
        sell_reasons.append('Blokada makro aktywna — brak nowych wejść')

    min_score = int(os.getenv('MIN_SCORE', '80'))
    signal = 'NO TRADE'; score = max(buy_score, sell_score); reasons = ['Brak wystarczającej przewagi']
    entry = sl = tp1 = tp2 = tp3 = None
    setup_quality = 'LOW'

    if buy_score >= min_score and buy_score > sell_score and h1_atr and not macro_block_active():
        signal = 'BUY'; score = buy_score; reasons = buy_reasons; entry = price
        sl = min(struct['local_low'], price - 1.35 * h1_atr); risk = entry - sl
        tp1 = entry + 2 * risk; tp2 = entry + 3 * risk; tp3 = entry + 4 * risk
    elif sell_score >= min_score and sell_score > buy_score and h1_atr and not macro_block_active():
        signal = 'SELL'; score = sell_score; reasons = sell_reasons; entry = price
        sl = max(struct['local_high'], price + 1.35 * h1_atr); risk = sl - entry
        tp1 = entry - 2 * risk; tp2 = entry - 3 * risk; tp3 = entry - 4 * risk

    if score >= 85: setup_quality = 'HIGH'
    elif score >= 70: setup_quality = 'MEDIUM'

    watch_plan = build_watch_plan(price, h1_atr, struct, h1_trend, h4_trend, d1_trend)
    return {
        'version': 'v3', 'symbol': symbol, 'signal': signal, 'score': max(0, min(100, int(score))), 'min_score': min_score,
        'setup_quality': setup_quality, 'price': round_price(price), 'entry': round_price(entry), 'sl': round_price(sl),
        'tp1': round_price(tp1), 'tp2': round_price(tp2), 'tp3': round_price(tp3),
        'rr1': rr(entry, sl, tp1) if entry and sl and tp1 else None,
        'rr2': rr(entry, sl, tp2) if entry and sl and tp2 else None,
        'rr3': rr(entry, sl, tp3) if entry and sl and tp3 else None,
        'trend_m15': trend_from_emas(m15), 'trend_h1': h1_trend, 'trend_h4': h4_trend, 'trend_d1': d1_trend,
        'rsi_h1': round(h1_rsi, 1) if h1_rsi else None, 'atr_h1': round(h1_atr, 2) if h1_atr else None,
        'adx_h1': round(h1_adx, 1) if h1_adx else None, 'macd_hist_h1': round(macd_hist, 4) if macd_hist else None,
        'bollinger_width_h1': round(h1_bb_width, 4) if h1_bb_width else None,
        'pattern_h1': pattern_h1, 'pattern_m15': pattern_m15, 'dxy_bias': dxy['bias'], 'dxy_comment': dxy['comment'],
        'macro_block': macro_block_active(), 'reasons': reasons, 'watch_plan': watch_plan,
    }
