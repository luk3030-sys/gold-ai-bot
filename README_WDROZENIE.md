# Gold AI Bot v6 — Institutional Smart Money

## Pliki
- market_state.py — gotowy moduł do wgrania.
- integration_example.py — przykład wpięcia do app.py.

## Co dodaje
- WAIT
- BUY / SELL
- HIGH VOLATILITY
- BREAKOUT
- SIGNAL INVALIDATED
- Liquidity Sweep / Stop Hunt
- BOS / CHOCH
- FVG
- sugestie prowadzenia pozycji: BE, ciaśniejszy SL, zanegowanie sygnału

## Wdrożenie
1. Wgraj market_state.py do katalogu projektu.
2. W app.py dodaj:
```python
from market_state import Candle, classify_market_state, format_telegram_market_state
```
3. W miejscu generowania wiadomości Telegram użyj przykładu z integration_example.py.
4. Zrób deploy.
