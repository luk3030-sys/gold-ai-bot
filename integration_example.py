"""
Przyklad integracji z app.py

1. Wgraj market_state.py do folderu z app.py.
2. Dodaj import:
from market_state import Candle, classify_market_state, format_telegram_market_state
3. W miejscu budowania wiadomosci Telegram dodaj kod ponizej.
"""

from market_state import Candle, classify_market_state, format_telegram_market_state


last_candle = Candle(
    open=float(last_open),
    high=float(last_high),
    low=float(last_low),
    close=float(last_close),
)

market_state = classify_market_state(
    price=float(current_price),
    entry=float(entry),
    sl=float(sl),
    signal=str(signal),
    score=int(score),
    atr_h1=float(atr_h1),
    last_candle=last_candle,
    trend_m15=str(trend_m15),
    trend_h1=str(trend_h1),
    trend_h4=str(trend_h4),
    trend_d1=str(trend_d1),
)

telegram_message += format_telegram_market_state(market_state)
