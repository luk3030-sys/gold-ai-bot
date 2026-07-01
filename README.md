# Gold AI Bot v1

Automatyczny bot do analizy XAU/USD i wysyłania sygnałów BUY/SELL/NO TRADE na Telegram.

## Endpointy
- `/health` — status aplikacji
- `/run-now` — uruchamia analizę teraz i wysyła alert na Telegram, jeśli jest sygnał
- `/last` — ostatni wynik analizy

## Zmienne Render
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TWELVEDATA_API_KEY`
- `SYMBOL=XAU/USD`
- `CHECK_INTERVAL_MINUTES=60`
- `AUTO_RUN=true`
- `SEND_NO_TRADE=false`

## Render
Build Command:
`pip install -r requirements.txt`

Start Command:
`gunicorn app:app`
