# Gold AI Bot v6.3.1 — Institutional Endpoint Hotfix

Naprawia diagnostykę błędów `500 Internal Server Error` dla `/institutional` i `/analyze`.

## Zmiany
- `/institutional` i `/analyze` zwracają czytelny JSON z typem błędu zamiast ogólnej strony HTML 500.
- błędy są logowane przez `app.logger.exception(...)` do Render Logs.
- nowy chroniony endpoint `/market-diagnostics` testuje osobno M15/H1/H4/D1 i pokazuje, który interwał/dostawca danych zawodzi.
- wersja `/health`: `6.3.1-institutional-hotfix`.

## Test po deployu
1. `/health`
2. `/market-diagnostics` (z `?secret=...`, jeśli ustawiono `CRON_SECRET`)
3. `/institutional`
4. `/tick`
