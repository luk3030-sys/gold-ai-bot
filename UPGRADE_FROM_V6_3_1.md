# Upgrade from v6.3.1 to v6.3.2

1. Upload all v6.3.2 files to the same GitHub repository.
2. Keep the same `DATABASE_URL` to preserve PostgreSQL history.
3. Keep:
   - `TWELVEDATA_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `SYMBOL`
4. Set external cron to `/tick` every 10 minutes.
5. Keep `SCHEDULER_ENABLED=false` when using external cron.
6. Add recommended quota/cache environment variables from README.
7. After deploy test:
   - `/health`
   - `/quota-status`
   - `/cache-status`
   - `/market-diagnostics`
   - `/tick`

Database tables are added with `CREATE TABLE IF NOT EXISTS`; existing signal/performance history is preserved.
