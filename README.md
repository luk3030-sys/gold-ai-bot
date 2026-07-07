# Gold AI Bot v6.3.2 — Quota Guard & Smart Multi-Timeframe Cache

Wersja v6.3.2 rozwija v6.3.1 i zachowuje cały fundament:

- Institutional Smart Money: BOS/CHOCH, liquidity sweeps, FVG, displacement, order blocks, premium/discount
- M15 / H1 / H4 / D1
- PostgreSQL i trwała historia sygnałów
- Performance & Validation Engine
- tracking TP/SL
- DXY direct/proxy fallback
- alert dużego ruchu świecy
- deduplikacja, cooldown, limit sygnałów
- zamknięte świece dla głównych setupów

## Najważniejsza zmiana: koniec z pobieraniem wszystkich interwałów przy każdym ticku

Cron może wywoływać `/tick` **co 10 minut**, ale bot pobiera dane live tylko wtedy, gdy powinien istnieć nowy bucket danych.

Przykładowo:

- M15 — maksymalnie przy nowej zamkniętej świecy M15
- H1 — maksymalnie przy nowej zamkniętej świecy H1
- H4 — maksymalnie przy nowej zamkniętej świecy H4
- D1 — maksymalnie przy nowej zamkniętej świecy D1
- DXY H1 — korzysta z tego samego Smart Cache
- Move Alert — bieżąca świeca ma osobny krótki cache live

Dzięki temu wywołanie `/tick` co 10 minut **nie oznacza** czterech nowych requestów XAU/USD za każdym razem.

---

## Quota Guard

v6.3.2 ma trwały licznik użycia API zapisany w PostgreSQL/SQLite.

Domyślne wartości:

```text
TD_MINUTE_CREDIT_LIMIT=8
TD_DAILY_CREDIT_LIMIT=800
TD_MINUTE_CREDIT_RESERVE=1
TD_DAILY_CREDIT_RESERVE=80
```

Bot blokuje nowe requesty przed wejściem w rezerwę. Jeżeli ma cache, używa cache zamiast wywoływać API.

### HTTP 429

Po `429 Too Many Requests` bot:

1. **nie robi automatycznej serii retry 429**,
2. otwiera circuit breaker,
3. używa stale-cache, jeśli jest wystarczająco świeży,
4. zwraca wynik `degraded`, a nie bezwartościowy błąd 500,
5. zwiększa cooldown po kolejnych 429.

Domyślnie:

```text
TD_429_BASE_COOLDOWN_SECONDS=65
TD_429_MAX_COOLDOWN_SECONDS=1800
```

---

## Smart Multi-Timeframe Cache

Cache ma dwie warstwy:

1. szybki cache w pamięci procesu,
2. **trwały cache w PostgreSQL** (`market_cache`).

Po restarcie lub redeployu bot może ponownie użyć zapisanych ramek danych zamiast natychmiast zużywać API credits.

Dodatkowo większy cache może obsłużyć mniejszy request. Przykład:

- tracker pobrał 500 świec M15,
- strategia potrzebuje 320 świec M15,
- strategia użyje istniejącego cache 500 zamiast robić drugi request.

---

## Automatyka — rekomendacja

Na Render Free:

```text
SCHEDULER_ENABLED=false
```

Zewnętrzny cron:

```text
GET https://TWOJ-SERWIS.onrender.com/tick
```

Rekomendowany harmonogram:

```text
co 10 minut
```

Jeżeli masz `CRON_SECRET`:

```text
https://TWOJ-SERWIS.onrender.com/tick?secret=TWOJE_HASLO
```

Nie publikuj sekretu.

---

## Kluczowe endpointy

### Status

```text
/health
/ready
/db-info
```

### Analiza

```text
/analyze
/institutional
/move-watch
```

### Automat

```text
/tick
/signal
/run-now
/track-now
```

### Performance

```text
/signals
/performance
/history
/validate?bars=1500
```

### Quota i cache — nowe w v6.3.2

```text
/quota-status
/cache-status
```

### Diagnostyka rynku

Domyślnie Smart Cache:

```text
/market-diagnostics
```

Wymuszenie live refresh — używaj ostrożnie, bo zużywa quota:

```text
/market-diagnostics?refresh=1
```

---

## Wymagane zmienne Render

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

## Zalecane nowe zmienne v6.3.2

```text
QUOTA_GUARD_ENABLED=true
TD_MINUTE_CREDIT_LIMIT=8
TD_DAILY_CREDIT_LIMIT=800
TD_MINUTE_CREDIT_RESERVE=1
TD_DAILY_CREDIT_RESERVE=80
TD_429_BASE_COOLDOWN_SECONDS=65
TD_429_MAX_COOLDOWN_SECONDS=1800
CANDLE_CLOSE_GRACE_SECONDS=75
LIVE_CACHE_SECONDS=300
LIVE_STALE_CACHE_SECONDS=1800
API_STALE_CACHE_SECONDS=21600
ANALYZE_INTERVAL_MINUTES=10
```

Wartości limitów ustaw zgodnie z faktycznym planem Twelve Data.

---

## Zachowanie `/tick` przy problemie API

Normalnie:

```json
{
  "status": "ok",
  "analysis": {...},
  "quota": {...}
}
```

Przy braku danych i aktywnym Quota Guard:

```json
{
  "status": "degraded",
  "reason": "market_data_unavailable",
  "analysis": null,
  "telegram_sent": false,
  "quota": {...}
}
```

To celowe: bot ma **nie tworzyć sygnału na niepewnych danych**.

---

## Testy

Projekt zawiera testy jednostkowe warstw:

- PostgreSQL/SQLite Data Layer
- DB tick lock
- DXY fallback
- Institutional Engine
- Move Detector
- TP/SL Tracker
- Quota Guard
- circuit breaker 429
- persistent Smart Cache
- degraded tick zamiast 500

---

## Ważne ograniczenia

- Score 0–100 jest wynikiem regułowym, nie prawdopodobieństwem sukcesu.
- Smart Money concepts są algorytmicznym przybliżeniem.
- Cache zwiększa odporność, ale stare dane obniżają jakość decyzji.
- Bot nie gwarantuje zysków i nie jest poradą inwestycyjną.
