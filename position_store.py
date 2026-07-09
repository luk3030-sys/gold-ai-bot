"""
Gold AI Bot v6 — Position Manager
PostgreSQL-based open position memory + Telegram command support.

Wymagane ENV:
DATABASE_URL=postgresql://...
"""

import os
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL")


def _conn():
    if not DATABASE_URL:
        raise RuntimeError("Brak DATABASE_URL w zmiennych środowiskowych.")
    return psycopg2.connect(DATABASE_URL)


def init_position_db():
    sql = """
    CREATE TABLE IF NOT EXISTS open_positions (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL DEFAULT 'XAU/USD',
        side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
        entry DOUBLE PRECISION NOT NULL,
        sl DOUBLE PRECISION,
        tp1 DOUBLE PRECISION,
        tp2 DOUBLE PRECISION,
        tp3 DOUBLE PRECISION,
        status TEXT NOT NULL DEFAULT 'OPEN',
        tp1_hit BOOLEAN NOT NULL DEFAULT FALSE,
        tp2_hit BOOLEAN NOT NULL DEFAULT FALSE,
        tp3_hit BOOLEAN NOT NULL DEFAULT FALSE,
        source TEXT DEFAULT 'telegram',
        note TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def add_position(side, entry, sl=None, tp1=None, tp2=None, tp3=None, symbol="XAU/USD", source="telegram", note=None):
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side musi być BUY albo SELL")

    pid = f"{symbol.replace('/','')}_{side}_{entry}_{uuid.uuid4().hex[:6]}"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO open_positions
                (id, symbol, side, entry, sl, tp1, tp2, tp3, source, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *;
            """, (pid, symbol, side, float(entry), sl, tp1, tp2, tp3, source, note))
            return dict(cur.fetchone())


def get_open_positions(symbol="XAU/USD"):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM open_positions
                WHERE symbol=%s AND status='OPEN'
                ORDER BY created_at ASC;
            """, (symbol,))
            return [dict(r) for r in cur.fetchall()]


def close_position(position_id, reason="manual"):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE open_positions
                SET status='CLOSED', note=COALESCE(note,'') || %s, updated_at=NOW()
                WHERE id=%s;
            """, (f"\nClosed: {reason}", position_id))


def mark_tp(position_id, tp_number):
    col = {1: "tp1_hit", 2: "tp2_hit", 3: "tp3_hit"}[tp_number]
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE open_positions
                SET {col}=TRUE, updated_at=NOW()
                WHERE id=%s;
            """, (position_id,))


def evaluate_positions(current_price, symbol="XAU/USD"):
    """
    Zwraca listę alertów tekstowych dla Telegrama.
    Działa dla BUY i SELL.
    """
    price = float(current_price)
    alerts = []
    positions = get_open_positions(symbol)

    for p in positions:
        side = p["side"]
        pid = p["id"]
        entry = float(p["entry"])
        sl = p["sl"]
        tp1, tp2, tp3 = p["tp1"], p["tp2"], p["tp3"]

        profit_points = (price - entry) if side == "BUY" else (entry - price)

        # SL
        if sl is not None:
            if side == "BUY" and price <= float(sl):
                alerts.append(f"🛑 SL HIT / zagrożony BUY\nID: {pid}\nCena: {price:.2f}\nSL: {float(sl):.2f}")
                close_position(pid, "SL hit")
                continue
            if side == "SELL" and price >= float(sl):
                alerts.append(f"🛑 SL HIT / zagrożony SELL\nID: {pid}\nCena: {price:.2f}\nSL: {float(sl):.2f}")
                close_position(pid, "SL hit")
                continue

        # TP logic
        targets = [(1, tp1, p["tp1_hit"]), (2, tp2, p["tp2_hit"]), (3, tp3, p["tp3_hit"])]
        for n, tp, hit in targets:
            if tp is None or hit:
                continue

            reached = (side == "BUY" and price >= float(tp)) or (side == "SELL" and price <= float(tp))
            if reached:
                mark_tp(pid, n)
                if n == 1:
                    alerts.append(
                        f"✅ TP1 osiągnięty — rozważ przesunięcie SL na BE\n"
                        f"Pozycja: {side} {symbol}\nID: {pid}\nEntry: {entry:.2f}\nCena: {price:.2f}\nTP1: {float(tp):.2f}"
                    )
                else:
                    alerts.append(
                        f"✅ TP{n} osiągnięty\nPozycja: {side} {symbol}\nID: {pid}\nCena: {price:.2f}\nTP{n}: {float(tp):.2f}"
                    )

        # informational warning
        if profit_points < 0:
            alerts.append(
                f"⚠️ Pozycja {side} pod presją\nID: {pid}\nEntry: {entry:.2f}\nCena: {price:.2f}\nWynik: {profit_points:.2f} pkt"
            )

    return alerts


def format_positions(symbol="XAU/USD"):
    positions = get_open_positions(symbol)
    if not positions:
        return "Brak otwartych pozycji w pamięci bota."

    lines = ["📌 Otwarte pozycje:"]
    for p in positions:
        lines.append(
            f"\nID: {p['id']}\n"
            f"{p['side']} {p['symbol']}\n"
            f"Entry: {p['entry']}\n"
            f"SL: {p['sl']}\n"
            f"TP1: {p['tp1']} | TP2: {p['tp2']} | TP3: {p['tp3']}\n"
            f"TP hit: {p['tp1_hit']}/{p['tp2_hit']}/{p['tp3_hit']}"
        )
    return "\n".join(lines)