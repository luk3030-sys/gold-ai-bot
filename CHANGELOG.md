# Changelog

## 6.3.0 — Institutional + Persistent Performance

- zachowano PostgreSQL, tracking TP/SL, performance, cooldowny i blokady ticka z v5.1
- dodano Institutional Smart Money Engine:
  - BOS / CHOCH
  - struktura HH/HL i LH/LL
  - buy-side / sell-side liquidity sweeps
  - Fair Value Gaps
  - displacement
  - uproszczone Order Blocks
  - premium / discount range
- dodano scoring SMC dla M15/H1/H4
- dodano strefę Entry
- dodano alert dużego ruchu świecy niezależny od BUY/SELL
- dodano `/institutional` i `/move-watch`
- przywrócono kompatybilny endpoint `/signal`
- `/tick` pozostaje głównym automatycznym cyklem
- podniesiono schema metadata do 6.3 bez zmiany istniejących tabel sygnałów
