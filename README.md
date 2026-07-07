# Gold AI Bot v6.2 — Institutional Smart Money + Large Candle Alerts

Bot dla XAU/USD z alertami Telegram.

## Funkcje
- BOS / CHOCH
- liquidity sweep
- fair value gap
- order block
- trend M15/H1/H4/D1
- Entry, SL, TP1, TP2, TP3
- alert Telegram przy mocnym sygnale
- dodatkowy alert Telegram, gdy zamknięta świeca M15 lub H1 ma duży ruch w górę albo w dół

## Nowe zmienne ENV dla dużych świec

```text
LARGE_CANDLE_ALERT_ENABLED=true
LARGE_CANDLE_INTERVALS=15min,1h
LARGE_CANDLE_ATR_MULTIPLIER=1.2
LARGE_CANDLE_MIN_POINTS=20
LARGE_CANDLE_BODY_RATIO=0.55
```

Znaczenie:
- `LARGE_CANDLE_INTERVALS` — interwały monitorowane pod duże świece.
- `LARGE_CANDLE_MIN_POINTS` — minimalny korpus świecy w punktach/cenie złota.
- `LARGE_CANDLE_ATR_MULTIPLIER` — korpus musi być większy niż ATR × ten mnożnik.
- `LARGE_CANDLE_BODY_RATIO` — korpus musi stanowić minimum podaną część całego zakresu świecy, aby nie alertować samych knotów.

Alert dużej świecy nie jest automatycznym sygnałem wejścia. To informacja o silnym impulsie i zmienności.

## Endpointy
- `/health`
- `/signal`
- `/last`


## v6.2 — alert na duży ruch świecy ogólnie

Bot wykrywa teraz nie tylko mocny korpus świecy, ale też duży całkowity zakres świecy HIGH–LOW. Dzięki temu Telegram może wysłać alert, gdy świeca zrobiła duży ruch, nawet jeśli zamknięcie wróciło blisko otwarcia, np. długi knot po danych makro.

Nowe zmienne ENV:

- `LARGE_CANDLE_MODE=ANY` — domyślnie; alert dla mocnego korpusu LUB dużego zakresu świecy.
- `LARGE_CANDLE_MODE=BODY` — tylko mocny kierunkowy korpus.
- `LARGE_CANDLE_MODE=RANGE` — tylko duży zakres HIGH–LOW.
- `LARGE_CANDLE_RANGE_ATR_MULTIPLIER=1.5` — alert, gdy zakres świecy jest co najmniej 1.5x ATR14.
- `LARGE_CANDLE_MIN_POINTS=20` — minimalny ruch w punktach.

Przykład: jeśli świeca M15 ma zakres 28 pkt, a ATR14 wynosi 15 pkt, to zakres/ATR = 1.87 i bot wyśle alert w trybie ANY/RANGE.
