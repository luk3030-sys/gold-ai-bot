Gold AI Bot v6.5.2 — Telegram Polling Fix

Naprawiono:
- aktywny webhook blokujący getUpdates (HTTP 409)
- automatyczne deleteWebhook przy trybie polling
- natychmiastowy poll po starcie
- diagnostykę ostatniego błędu Telegrama
- endpoint /telegram-status
- endpoint POST /telegram-poll-now
- /health pokazuje rzeczywisty stan pollingu

Wdrożenie:
1. Podmień app.py.
2. Zrób deploy/restart.
3. Sprawdź /health.
4. Sprawdź /telegram-status.
5. Wyślij do bota /start.
6. Poczekaj maksymalnie 1 minutę.

Oczekiwane:
version = 6.5.2-telegram-polling-fix
telegram_last_error = null
telegram_last_success_utc != null
get_me_ok = true
webhook_url = ""