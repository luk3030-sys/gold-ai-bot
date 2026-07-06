# Gold AI Bot v5 — Performance & Validation

To jest rzeczywista rozbudowa wcześniejszego bota Pro. V5 koncentruje się na **mierzeniu jakości sygnałów**, a nie na dokładaniu kolejnych wskaźników.

## Co dodaje v5

- automatyczny rejestr każdego nowego sygnału BUY/SELL w SQLite,
- lifecycle sygnału: `OPEN -> TP2_HIT / SL_HIT / TIMEOUT / AMBIGUOUS`,
- tracking TP1/TP2/TP3,
- konserwatywna polityka, gdy SL i TP2 są dotknięte w tej samej świecy,
- wynik w jednostkach `R`,
- win rate, expectancy, profit factor, net R, max drawdown,
- wyniki osobno dla BUY/SELL, setupów, reżimów i bucketów score,
- wykrywanie reżimu rynku,
- `USE_CLOSED_CANDLES=true` — sygnały tylko na zamkniętych świecach,
- deduplikacja alertów,
- cooldown sygnałów i cooldown po stracie,
- maksymalna liczba sygnałów dziennie,
- kontrola zgodności feedu z brokerem,
- historyczna walidacja z holdoutem 30%,
- endpoint `/tick` do zewnętrznego cron.

> **Ważne:** score 0–100 jest punktacją regułową, a nie prawdopodobieństwem sukcesu. Dopiero statystyki z zamkniętych sygnałów pokazują rzeczywiste wyniki bota.

## Pliki

- `app.py` — API, panel, scheduler
- `strategy.py` — analiza live, scoring, reżim, setup
- `tracker.py` — outcome engine TP/SL
- `db.py` — SQLite i historia sygnałów
- `performance.py` — statystyki jakości
- `validation.py` — historyczna walidacja
- `performance_service.py` — deduplikacja, cooldown, limity
- `data_provider.py` — Twelve Data + cache + zamknięte świece

## Endpointy

- `/` — panel
- `/health` — status
- `/analyze` — analiza bez zapisu sygnału
- `/run-now` — ręczna analiza + Telegram
- `/tick` — **główny endpoint automatyczny**: tracking + analiza + zapis nowego sygnału + Telegram
- `/track-now` — tylko aktualizacja wyników otwartych sygnałów
- `/signals` — lista sygnałów
- `/performance` — wyniki i breakdown
- `/validate?bars=1500` — walidacja historyczna
- `/feed-check?broker_price=4057.28` — porównanie API z ceną brokera
- `/telegram-test` — test Telegrama
- `/daily-report` — raport dzienny

## Najważniejsza konfiguracja Render

W Render -> Environment ustaw co najmniej:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TWELVEDATA_API_KEY=...
SYMBOL=XAU/USD
MIN_SCORE=80
MIN_RR=2.0
USE_CLOSED_CANDLES=true
MAX_SIGNALS_PER_DAY=3
SIGNAL_COOLDOWN_MINUTES=60
LOSS_COOLDOWN_MINUTES=120
SCHEDULER_ENABLED=true
ANALYZE_INTERVAL_MINUTES=5
TIMEZONE=Europe/Warsaw
```

### Zalecane bezpieczeństwo

Ustaw:

```text
CRON_SECRET=TwojeLosoweDlugieHaslo
```

Wtedy cron wywołuje:

```text
https://TWOJ-BOT.onrender.com/tick?secret=TwojeLosoweDlugieHaslo
```

## Automatyka na Render Free

Render Free usypia usługę, więc wewnętrzny APScheduler nie jest wystarczająco niezawodny.

Ustaw w `cron-job.org` wywołanie co 5 minut:

```text
https://TWOJ-BOT.onrender.com/tick
```

lub z `CRON_SECRET`:

```text
https://TWOJ-BOT.onrender.com/tick?secret=...
```

`/tick` robi w jednym przebiegu:

1. sprawdza otwarte sygnały i TP/SL,
2. zamyka zakończone sygnały,
3. wykonuje nową analizę,
4. stosuje cooldown/limit dzienny/deduplikację,
5. zapisuje nowy sygnał,
6. wysyła Telegram tylko dla nowego BUY/SELL.

## Trwałość historii

Domyślnie baza jest tutaj:

```text
/tmp/gold_ai_bot_v5/gold_ai_bot_v5.db
```

Na Render Free pliki mogą zniknąć po restarcie/redeployu. Do prawdziwej długoterminowej statystyki potrzebujesz:

- Render Persistent Disk (płatny) i `DATABASE_PATH=/var/data/gold_ai_bot_v5.db`, **albo**
- kolejnej wersji z PostgreSQL.

Bez trwałej bazy statystyki po restarcie mogą zacząć się od zera.

## Walidacja

Otwórz:

```text
/validate?bars=1500
```

Silnik:

- pobiera H1,
- buduje H4/D1 przez resampling,
- symuluje sygnały bez nakładania pozycji,
- stosuje konserwatywne założenie dla świecy, która dotyka SL i TP,
- raportuje pierwsze 70% i osobny holdout ostatnich 30%.

### Ograniczenia walidacji

Walidacja nie jest identyczna z live v5, bo nie używa M15 ani DXY. Nie uwzględnia spreadu i poślizgu. To celowo konserwatywne narzędzie diagnostyczne, nie dowód przyszłych zysków.

## Test lokalny outcome engine

```bash
python -m unittest discover -s tests -v
```

## Kolejność pierwszego testu po wdrożeniu

1. `/health`
2. `/telegram-test`
3. `/analyze`
4. `/tick`
5. `/signals`
6. `/performance`
7. `/validate?bars=1000`
8. `/feed-check?broker_price=...`

## Uwaga inwestycyjna

Bot jest narzędziem wspomagania decyzji. Nie gwarantuje zysków i nie powinien samodzielnie składać zleceń bez osobnej warstwy kontroli ryzyka i testów.
