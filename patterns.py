def candle_patterns(df):
    if len(df) < 3:
        return []
    prev = df.iloc[-2]
    cur = df.iloc[-1]
    body = abs(cur.close - cur.open)
    rng = max(cur.high - cur.low, 1e-9)
    upper = cur.high - max(cur.open, cur.close)
    lower = min(cur.open, cur.close) - cur.low
    out = []
    if body / rng < 0.35 and lower > body * 2:
        out.append("pin_bar_bullish")
    if body / rng < 0.35 and upper > body * 2:
        out.append("pin_bar_bearish")
    if cur.close > cur.open and prev.close < prev.open and cur.close >= prev.open and cur.open <= prev.close:
        out.append("bullish_engulfing")
    if cur.close < cur.open and prev.close > prev.open and cur.open >= prev.close and cur.close <= prev.open:
        out.append("bearish_engulfing")
    if cur.high < prev.high and cur.low > prev.low:
        out.append("inside_bar")
    return out


def interpret_patterns(patterns):
    mapping = {
        "inside_bar": "Inside Bar — konsolidacja; czekaj na potwierdzone wybicie",
        "pin_bar_bullish": "Byczy Pin Bar — odrzucenie niższych cen",
        "pin_bar_bearish": "Niedźwiedzi Pin Bar — odrzucenie wyższych cen",
        "bullish_engulfing": "Bycze objęcie — krótkoterminowa przewaga popytu",
        "bearish_engulfing": "Niedźwiedzie objęcie — krótkoterminowa przewaga podaży",
    }
    return [mapping[p] for p in patterns if p in mapping]
