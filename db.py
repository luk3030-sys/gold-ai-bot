import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_DB_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def db_path() -> str:
    explicit = os.getenv("DATABASE_PATH")
    if explicit:
        path = Path(explicit)
    else:
        path = Path(os.getenv("DATA_DIR", "/tmp/gold_ai_bot_v5")) / "gold_ai_bot_v5.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@contextmanager
def connection():
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _DB_LOCK, connection() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                last_checked_at TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                score INTEGER NOT NULL,
                setup_type TEXT,
                regime TEXT,
                entry REAL NOT NULL,
                sl REAL NOT NULL,
                tp1 REAL,
                tp2 REAL,
                tp3 REAL,
                rr_tp1 REAL,
                rr_tp2 REAL,
                rr_tp3 REAL,
                primary_target TEXT NOT NULL DEFAULT 'TP2',
                status TEXT NOT NULL DEFAULT 'OPEN',
                outcome TEXT,
                r_result REAL,
                tp1_hit INTEGER NOT NULL DEFAULT 0,
                tp2_hit INTEGER NOT NULL DEFAULT 0,
                tp3_hit INTEGER NOT NULL DEFAULT 0,
                fingerprint TEXT NOT NULL,
                analysis_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_fingerprint ON signals(fingerprint);

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                price REAL,
                payload_json TEXT,
                FOREIGN KEY(signal_id) REFERENCES signals(id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_signal_id ON events(signal_id);

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                run_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT
            );
            """
        )


def _row_to_dict(row) -> Dict[str, Any]:
    return dict(row) if row is not None else {}


def add_run(run_type: str, status: str, payload: Dict[str, Any]) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO runs(created_at, run_type, status, payload_json) VALUES (?,?,?,?)",
            (utc_now_iso(), run_type, status, json.dumps(payload, ensure_ascii=False, default=str)),
        )


def create_signal(analysis: Dict[str, Any], fingerprint: str, primary_target: str = "TP2") -> Dict[str, Any]:
    signal_id = str(uuid.uuid4())
    now = utc_now_iso()
    values = (
        signal_id, now, analysis["symbol"], analysis["signal"], int(analysis["score"]),
        analysis.get("setup_type"), analysis.get("regime"), float(analysis["entry"]), float(analysis["sl"]),
        analysis.get("tp1"), analysis.get("tp2"), analysis.get("tp3"), analysis.get("rr_tp1"),
        analysis.get("rr_tp2"), analysis.get("rr_tp3"), primary_target, fingerprint,
        json.dumps(analysis, ensure_ascii=False, default=str),
    )
    with connection() as conn:
        conn.execute(
            """INSERT INTO signals(
                id, created_at, symbol, side, score, setup_type, regime, entry, sl,
                tp1, tp2, tp3, rr_tp1, rr_tp2, rr_tp3, primary_target, fingerprint, analysis_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
    add_event(signal_id, "OPENED", analysis.get("entry"), {"score": analysis.get("score")})
    return get_signal(signal_id)


def add_event(signal_id: Optional[str], event_type: str, price: Optional[float], payload: Optional[Dict[str, Any]] = None) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO events(signal_id, created_at, event_type, price, payload_json) VALUES (?,?,?,?,?)",
            (signal_id, utc_now_iso(), event_type, price, json.dumps(payload or {}, ensure_ascii=False, default=str)),
        )


def get_signal(signal_id: str) -> Dict[str, Any]:
    with connection() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    return _row_to_dict(row)


def open_signals() -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM signals WHERE status='OPEN' ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def list_signals(limit: int = 100, status: Optional[str] = None) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with connection() as conn:
        if status:
            rows = conn.execute("SELECT * FROM signals WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def recent_fingerprint_exists(fingerprint: str, since_iso: str) -> bool:
    with connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM signals WHERE fingerprint=? AND created_at>=? LIMIT 1",
            (fingerprint, since_iso),
        ).fetchone()
    return row is not None


def count_signals_since(since_iso: str) -> int:
    with connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM signals WHERE created_at>=?", (since_iso,)).fetchone()
    return int(row["n"])


def last_closed_loss() -> Optional[Dict[str, Any]]:
    with connection() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE status='CLOSED' AND r_result<0 ORDER BY closed_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def update_signal(signal_id: str, **fields) -> None:
    allowed = {
        "closed_at", "last_checked_at", "status", "outcome", "r_result",
        "tp1_hit", "tp2_hit", "tp3_hit",
    }
    clean = {key: value for key, value in fields.items() if key in allowed}
    if not clean:
        return
    sql = ", ".join(f"{key}=?" for key in clean)
    with connection() as conn:
        conn.execute(f"UPDATE signals SET {sql} WHERE id=?", (*clean.values(), signal_id))


def closed_signal_rows() -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM signals WHERE status='CLOSED' AND r_result IS NOT NULL ORDER BY closed_at"
        ).fetchall()
    return [dict(row) for row in rows]


def recent_runs(limit: int = 50) -> List[Dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
    return [dict(row) for row in rows]
