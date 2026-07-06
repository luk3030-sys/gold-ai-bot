# Gold AI Bot v5.1 — Stability & Data Layer

V5.1 rozwija działające v5 **Performance & Validation**. Priorytetem nie są nowe wskaźniki, tylko niezawodność, trwałość historii i odporność na awarie danych.

## Najważniejsze zmiany względem v5

### 1. Trwała baza PostgreSQL

Bot automatycznie wybiera backend:

- jeśli `DATABASE_URL` zaczyna się od `postgresql://` lub `postgres://` → używa PostgreSQL,
- w przeciwnym razie → używa SQLite.

Endpoint `/health` pokazuje aktywny backend.

**Rekomendacja produkcyjna:** ustaw `DATABASE_URL` do trwałej bazy PostgreSQL. Dzięki temu historia sygnałów, TP/SL, statystyki i performance nie znikną po restarcie lub redeployu web service.

### 2. Blokada równoległych ticków

`/tick` używa blokady zapisanej w bazie danych. Jeżeli cron i scheduler wywołają analizę równocześnie, drugi proces zwróci:

```json
{
  "status": "skipped",
  "reason": "tick_already_running"
}
```

To chroni przed podwójnymi sygnałami i duplikowaniem zapisów.

### 3. Odporniejszy provider danych

Dodano:

- retry HTTP dla 429/5xx,
- cache świeżych danych,
- opcjonalny stale-cache przy chwilowej awarii API,
- timeout konfigurowalny przez env,
- endpoint `/data-health`.

### 4. DXY fallback

Bot nie zakłada już, że jeden symbol DXY zawsze istnieje.

Próbuje kandydatów z:

```text
DXY_SYMBOLS=DXY,DX
```

Opcjonalnie można ustawić jawny proxy:

```text
DXY_PROXY_SYMBOL=...
```

Proxy jest oznaczane jako `PROXY` i dostaje mniejszą wagę niż bezpośredni DXY. Jeżeli dane USD są niedostępne, bot obniża `data_quality_score` zamiast udawać, że filtr działa.

### 5. Diagnostyka gotowości

Nowe endpointy:

- `/health` — wersja, DB, scheduler, closed candles,
- `/ready` — DB + test danych rynkowych,
- `/data-health` — diagnostyka feedu,
- `/db-info` — backend i stan bazy.

## Zachowane funkcje v5

- M15 / H1 / H4 / D1,
- BUY / SELL / NO TRADE,
- score regułowy,
- Entry / SL / TP1 / TP2 / TP3,
- RR,
- outcome engine TP/SL,
- tracking otwartych sygnałów,
- performance w jednostkach R,
- breakdown BUY/SELL/setup/regime/score bucket,
- walidacja historyczna z holdout 30%,
- closed candles,
- deduplikacja,
- cooldown po sygnale i po stracie,
- Telegram,
- `/tick` do automatyki.

---

## Wymagane zmienne środowiskowe

```text
SYMBOL=XAU/USD
TWELVEDATA_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TIMEZONE=Europe/Warsaw
```

## PostgreSQL — rekomendowane

Dodaj:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
```

Nie wpisuj `DATABASE_URL` do GitHub. Trzymaj go tylko w Environment/Secrets hostingu.

Po restarcie aplikacji `/health` powinno pokazać:

```json
{
  "version": "5.1-stability-data-layer",
  "database": {
    "ok": true,
    "backend": "postgresql",
    "persistent": true
  }
}
```

## Zalecana konfiguracja sygnałów

```text
MIN_SCORE=80
MIN_RR=2.0
USE_CLOSED_CANDLES=true
MAX_SIGNALS_PER_DAY=3
SIGNAL_COOLDOWN_MINUTES=60
LOSS_COOLDOWN_MINUTES=120
PRIMARY_TARGET=TP2
MAX_SIGNAL_AGE_HOURS=72
AMBIGUOUS_POLICY=conservative
TRACK_INTERVAL=15min
VALIDATION_MIN_SCORE=80
```

## Automatyka

Dla hostingu, który może usypiać web service, zalecany jest zewnętrzny cron:

```text
GET https://TWOJ-BOT.onrender.com/tick?secret=TWOJ_SECRET
```

co 5 minut.

Wtedy ustaw:

```text
SCHEDULER_ENABLED=false
CRON_SECRET=TwojeDlugieLosoweHaslo
```

Wewnętrzny scheduler może być używany na hostingu działającym stale:

```text
SCHEDULER_ENABLED=true
ANALYZE_INTERVAL_MINUTES=5
```

Blokada DB chroni przed przypadkowym nakładaniem wywołań.

## Odporność danych

```text
API_CACHE_SECONDS=45
API_STALE_CACHE_SECONDS=900
USE_STALE_CACHE_ON_ERROR=true
HTTP_RETRIES=3
HTTP_TIMEOUT_SECONDS=25
```

Stale-cache jest używany tylko wtedy, gdy wcześniejsze dane istnieją w pamięci procesu. Po restarcie procesu cache zaczyna się od zera.

## DXY

```text
DXY_ENABLED=true
DXY_SYMBOLS=DXY,DX
DXY_REQUIRED=false
DXY_WEIGHT=5
DXY_PROXY_WEIGHT=2
DXY_MISSING_PENALTY=5
DXY_FAILURE_CACHE_SECONDS=900
```

Opcjonalny proxy:

```text
DXY_PROXY_SYMBOL=...
```

Nie ustawiaj losowego proxy bez sprawdzenia, czy rzeczywiście reprezentuje zachowanie USD w sposób akceptowalny dla Twojej strategii.

## Python i zależności

Rekomendowane:

```text
PYTHON_VERSION=3.12.11
```

V5.1 używa:

```text
pandas==2.2.3
psycopg2-binary==2.9.10
```

To usuwa wcześniejszy problem z buildem `pandas==2.2.2` w niektórych runtime'ach.

---

## Endpointy

### Stan

```text
/health
/ready
/data-health
/db-info
```

### Analiza i automatyka

```text
/analyze
/run-now
/tick
/track-now
/daily-report
/telegram-test
```

### Wyniki

```text
/signals
/history
/performance
/validate?bars=1500
/feed-check?broker_price=4057.28
```

---

## Kolejność testu po wdrożeniu

1. `/health`
2. sprawdź `version = 5.1-stability-data-layer`
3. sprawdź `database.backend`
4. `/ready`
5. `/telegram-test`
6. `/analyze`
7. `/tick`
8. `/signals`
9. `/performance`
10. `/validate?bars=1000`

## Migracja starego SQLite do PostgreSQL

W folderze `scripts` jest:

```text
migrate_sqlite_to_postgres.py
```

Uruchomienie:

```bash
SOURCE_SQLITE_PATH=/sciezka/gold_ai_bot_v5.db \
DATABASE_URL=postgresql://... \
python scripts/migrate_sqlite_to_postgres.py
```

Uwaga: sygnały są idempotentne po `id`, ale `events` i `runs` nie powinny być importowane wielokrotnie, bo mogą powstać duplikaty audytowe.

## Testy

```bash
python -m unittest discover -s tests -v
```

W paczce są testy:

- outcome engine,
- blokada job lock,
- health SQLite,
- fallback DXY.

## Ograniczenia

- `score` nadal jest punktacją regułową, nie prawdopodobieństwem.
- DXY zależy od dostępności symbolu u dostawcy danych.
- walidacja historyczna nie jest identyczna z egzekucją live,
- spread, slippage i różnice feedu brokera muszą być dalej kontrolowane,
- bot nie gwarantuje zysków i nie składa zleceń u brokera.
