# Gold AI Bot v3

Wersja v3 dodaje bardziej profesjonalny silnik analityczny:

- M15 / H1 / H4 / D1
- EMA 20/50/200
- RSI, MACD, ATR, ADX
- Bollinger Bands
- Price Action: engulfing, pin bar, inside bar
- opcjonalny filtr DXY
- ręczna blokada makro `MACRO_BLOCK=true`
- TP1/TP2/TP3, SL i RR
- Telegram
- raport dzienny `/daily-report`

## Endpointy

- `/health`
- `/analyze`
- `/run-now`
- `/telegram-test`
- `/daily-report`

## Render — zmienne środowiskowe

W Render ustaw:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TWELVEDATA_API_KEY=...
SYMBOL=XAU/USD
DXY_SYMBOL=DXY
ENABLE_DXY=true
MIN_SCORE=80
CHECK_INTERVAL_MINUTES=15
SEND_NO_TRADE=false
ENABLE_DAILY_REPORT=true
DAILY_REPORT_HOUR=7
MACRO_BLOCK=false
ENABLE_SCHEDULER=true
```

Jeżeli DXY nie działa w Twoim planie TwelveData, ustaw:

```text
ENABLE_DXY=false
```

## Komendy Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
gunicorn app:app
```

## Uwaga

To narzędzie edukacyjne i analityczne. Nie jest poradą inwestycyjną i nie gwarantuje zysków.
