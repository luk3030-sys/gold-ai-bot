# Gold AI Bot v6.3 — Institutional + Persistent Performance

v6.3 łączy warstwę **Institutional Smart Money** z trwałym **Performance & Validation Engine** z v5.1.

## Najważniejsze funkcje

- M15 / H1 / H4 / D1
- EMA 20/50/100/200, RSI, MACD, ATR, ADX, Bollinger
- **BOS / CHOCH**
- **liquidity sweeps** nad swing high i pod swing low
- **Fair Value Gaps (FVG)**
- **displacement + uproszczone Order Blocks**
- **premium / discount range**
- Price Action: pin bar, engulfing, inside bar
- DXY direct/proxy fallback
- BUY / SELL / NO TRADE, Entry zone, SL, TP1/TP2/TP3, RR
- PostgreSQL persistent history
- TP/SL outcome tracking
- performance: win rate, expectancy, profit factor, net R, max drawdown
- deduplication, daily limit, cooldown po stracie
- DB-backed tick lock
- **large candle / fast move alert** na Telegram
- closed candles dla głównych sygnałów

## Kluczowe endpointy

- `/health`
- `/ready`
- `/analyze`
- `/institutional`
- `/tick` — pełny cykl automatyczny
- `/signal` — kompatybilność ze starszym v6
- `/move-watch`
- `/track-now`
- `/signals`
- `/performance`
- `/history`
- `/validate?bars=1500`
- `/feed-check?broker_price=4057.28`
- `/db-info`
- `/daily-report`
- `/telegram-test`

## Rekomendowana automatyka na Render Free

1. `SCHEDULER_ENABLED=false`
2. zewnętrzny cron wywołujący `/tick` co 5 minut
3. najlepiej ustawić `CRON_SECRET` i używać:

```text
https://TWOJ-SERWIS.onrender.com/tick?secret=TWOJE_HASLO
```

`/tick` wykonuje:

1. tracking otwartych sygnałów i TP/SL,
2. alert dużego ruchu świecy, jeśli wystąpi i jest nowy,
3. pełną analizę institutional + technical,
4. blokady duplikatów/cooldown/limit dzienny,
5. zapis nowego BUY/SELL do PostgreSQL,
6. Telegram tylko dla nowego kwalifikowanego sygnału.

## Migracja z v5.1

Baza PostgreSQL jest zgodna z istniejącymi tabelami v5.1. Po podmianie kodu zachowasz historię sygnałów, o ile pozostawisz ten sam `DATABASE_URL`.

## Ustawienia wymagane

```text
SYMBOL=XAU/USD
TWELVEDATA_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DATABASE_URL=postgresql://...
PYTHON_VERSION=3.12.11
USE_CLOSED_CANDLES=true
SCHEDULER_ENABLED=false
MIN_SCORE=80
MIN_RR=2.0
```

## Ważne ograniczenia

- Score 0–100 jest wynikiem regułowym, **nie prawdopodobieństwem**.
- FVG, Order Block, BOS/CHOCH są algorytmicznymi przybliżeniami i wymagają walidacji.
- `/validate` pozostaje uproszczonym testem historycznym; nie odwzorowuje w pełni live institutional engine.
- System nie gwarantuje zysków i nie jest poradą inwestycyjną.
