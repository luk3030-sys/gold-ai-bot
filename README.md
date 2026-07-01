# Gold AI Bot Pro

Automatyczny bot do analizy XAU/USD i wysyłki alertów Telegram.

## Endpointy
- `/` panel WWW
- `/health` status
- `/analyze` analiza bez wysyłki
- `/run-now` analiza + Telegram
- `/telegram-test` test Telegrama
- `/daily-report` raport dzienny + Telegram
- `/history` historia zdarzeń

## Zmienne Render
W Render -> Environment ustaw:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TWELVEDATA_API_KEY`
- `SYMBOL=XAU/USD`
- `MIN_SCORE=80`
- `MIN_RR=2.0`
- `SCHEDULER_ENABLED=true`
- `ANALYZE_INTERVAL_MINUTES=5`
- `TIMEZONE=Europe/Warsaw`
- `MACRO_BLOCK=false`

## Uwaga
Render Free może usypiać usługę. Dla realnego 24/7 wybierz płatny Render/Railway/VPS albo użyj zewnętrznego pingera.

To narzędzie wspomaga analizę. Nie jest poradą inwestycyjną.
