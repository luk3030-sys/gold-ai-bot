# Gold AI Bot v2

Automatyczny bot do analizy XAU/USD i wysyłania sygnałów na Telegram.

## Funkcje

- analiza H1/H4/D1,
- EMA 50/200,
- RSI 14,
- MACD,
- ATR,
- sygnały BUY / SELL / NO TRADE,
- Entry, SL, TP1, TP2, RR,
- Telegram,
- endpointy testowe na Render.

## Pliki

- `app.py` — aplikacja Flask,
- `data_provider.py` — pobieranie danych z TwelveData,
- `indicators.py` — wskaźniki,
- `strategy.py` — logika sygnałów,
- `notifier.py` — Telegram,
- `scheduler.py` — automatyczna analiza,
- `requirements.txt` — biblioteki,
- `render.yaml` — konfiguracja Render.

## Zmienne Render

Dodaj w Render → Environment:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TWELVEDATA_API_KEY=...
SYMBOL=XAU/USD
CHECK_INTERVAL_MINUTES=15
MIN_SCORE=70
SEND_NO_TRADE=false
ENABLE_SCHEDULER=true
```

## Endpointy

- `/` — panel startowy,
- `/health` — test działania,
- `/analyze` — analiza bez wysyłki,
- `/run-now` — analiza + Telegram,
- `/telegram-test` — test wiadomości Telegram.

## Ważne

To narzędzie edukacyjne. Nie jest poradą inwestycyjną i nie gwarantuje zysków. Przed użyciem na realnym kapitale testuj na demo i stosuj kontrolę ryzyka.


## v2.1 — dodane funkcje

- NO TRADE pokazuje teraz plan obserwacji: wsparcie, opór, warunkowy BUY i warunkowy SELL.
- Sygnały BUY/SELL są blokowane, jeśli score jest poniżej `MIN_SCORE`.
- Dodano raport poranny `/daily-report` i automatyczny raport o 7:00 czasu PL.
- Nowe zmienne opcjonalne:
  - `MIN_SCORE=70`
  - `ENABLE_DAILY_REPORT=true`
  - `DAILY_REPORT_HOUR=7`
  - `SEND_NO_TRADE=false`
