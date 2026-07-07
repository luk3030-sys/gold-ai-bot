# Upgrade z v5.1 do v6.3

1. Rozpakuj ZIP.
2. W GitHub wgraj pliki z katalogu projektu i zatwierdź `Commit changes`.
3. **Nie zmieniaj `DATABASE_URL`** — dzięki temu zachowasz dotychczasową historię PostgreSQL.
4. W Render pozostaw:

```text
PYTHON_VERSION=3.12.11
USE_CLOSED_CANDLES=true
SCHEDULER_ENABLED=false
```

5. Dodaj opcjonalnie:

```text
MOVE_ALERT_ENABLED=true
MOVE_ALERT_INTERVAL=15min
MOVE_ALERT_ATR_MULT=0.90
MOVE_ALERT_RANGE_ATR_MULT=1.20
MOVE_ALERT_BODY_RATIO_MIN=0.55
SMC_WEIGHT_M15=0.30
SMC_WEIGHT_H1=0.55
SMC_WEIGHT_H4=0.75
```

6. Zewnętrzny cron pozostaw na:

```text
https://TWOJ-SERWIS.onrender.com/tick
```

lub z `CRON_SECRET`:

```text
https://TWOJ-SERWIS.onrender.com/tick?secret=TWOJE_HASLO
```

7. Po deployu sprawdź:

```text
/health
/analyze
/institutional
/move-watch
/tick
/performance
```

Oczekiwane `/health`:

```json
{
  "version": "6.3-institutional-persistent-performance",
  "institutional_engine": true,
  "move_alert_enabled": true,
  "database": {
    "backend": "postgresql",
    "persistent": true,
    "ok": true
  }
}
```
