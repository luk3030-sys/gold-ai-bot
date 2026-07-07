# Changelog

## 6.3.2 — Quota Guard & Smart Multi-Timeframe Cache

- persistent `api_usage_events` ledger
- persistent provider circuit breaker
- `/quota-status`
- persistent `market_cache` in PostgreSQL/SQLite
- `/cache-status`
- Smart bucket refresh for M15/H1/H4/D1
- reuse larger cached frames for smaller outputsize requests
- 429 removed from automatic HTTP retry list
- exponential circuit breaker after 429
- stale-cache fallback on quota/HTTP/provider errors
- DXY uses Smart Cache and does not negative-cache symbols merely because of global rate limiting
- `/tick` returns `degraded` on provider/quota failures instead of 500
- `/market-diagnostics?refresh=1` for explicit live refresh
- default scheduler interval changed to 10 minutes
- version endpoint updated to `6.3.2-quota-guard-smart-cache`
