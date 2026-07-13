import os
import json
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler

APP_VERSION = "6.5.6-entry-exit-signal-engine"

def env_bool(name: str, default: bool = False) -> bool:
    """
    Robust parser for environment booleans.
    Accepts: true/1/yes/on/y/t (case-insensitive, surrounding spaces ignored).
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().strip('"').strip("'").lower() in {
        "1", "true", "yes", "on", "y", "t"
    }

SYMBOL = os.getenv("SYMBOL", "XAU/USD")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLE_TELEGRAM = env_bool("ENABLE_TELEGRAM", True)
SCHEDULER_ENABLED = env_bool("SCHEDULER_ENABLED", True)
CLOSED_CANDLES_ONLY = env_bool("CLOSED_CANDLES_ONLY", True)
RUN_INTERVAL_MINUTES = int(os.getenv("RUN_INTERVAL_MINUTES", "15"))
MIN_SCORE_TO_ALERT = int(os.getenv("MIN_SCORE_TO_ALERT", "75"))
MAX_SPREAD_POINTS = float(os.getenv("MAX_SPREAD_POINTS", "2.0"))

# Position manager settings
POSITIONS_FILE = os.getenv("POSITIONS_FILE", "positions.json")
TELEGRAM_OFFSET_FILE = os.getenv("TELEGRAM_OFFSET_FILE", "telegram_offset.json")
POSITION_CHECK_INTERVAL_MINUTES = int(os.getenv("POSITION_CHECK_INTERVAL_MINUTES", "5"))
TELEGRAM_POLL_INTERVAL_MINUTES = int(os.getenv("TELEGRAM_POLL_INTERVAL_MINUTES", "1"))
TELEGRAM_POLLING_ENABLED = env_bool("TELEGRAM_POLLING_ENABLED", True)
DEFAULT_POSITION_VOLUME = float(os.getenv("DEFAULT_POSITION_VOLUME", "0.003"))
AUTO_RISK_ATR_MULTIPLIER = float(os.getenv("AUTO_RISK_ATR_MULTIPLIER", "1.4"))
AUTO_RISK_MIN_POINTS = float(os.getenv("AUTO_RISK_MIN_POINTS", "18"))
DEFAULT_ATR_H1 = float(os.getenv("DEFAULT_ATR_H1", "12.0"))
TP1_RR = float(os.getenv("TP1_RR", "1.5"))
TP2_RR = float(os.getenv("TP2_RR", "2.5"))
TP3_RR = float(os.getenv("TP3_RR", "3.5"))
BE_TRIGGER_RR = float(os.getenv("BE_TRIGGER_RR", "1.0"))
SL_WARNING_DISTANCE_ATR = float(os.getenv("SL_WARNING_DISTANCE_ATR", "0.35"))
TP_WARNING_DISTANCE_ATR = float(os.getenv("TP_WARNING_DISTANCE_ATR", "0.35"))

# Big candle / volatility alerts
MOVE_ALERT_ENABLED = env_bool("MOVE_ALERT_ENABLED", True)
MOVE_ALERT_INTERVALS = [x.strip() for x in os.getenv("MOVE_ALERT_INTERVALS", "5min,15min,1h").split(",") if x.strip()]
MOVE_BODY_ATR_MIN = float(os.getenv("MOVE_BODY_ATR_MIN", "0.85"))
MOVE_RANGE_ATR_MIN = float(os.getenv("MOVE_RANGE_ATR_MIN", "1.00"))
MOVE_BODY_RATIO_MIN = float(os.getenv("MOVE_BODY_RATIO_MIN", "0.55"))


# Smart Multi-Timeframe Cache / Quota Guard
CACHE_ENABLED = env_bool("CACHE_ENABLED", True)
CACHE_ALLOW_STALE = env_bool("CACHE_ALLOW_STALE", True)
CACHE_FILE = os.getenv("CACHE_FILE", "ohlc_cache.json")

CACHE_TTL_SECONDS = {
    "5min": int(os.getenv("CACHE_TTL_5MIN_SECONDS", "300")),
    "15min": int(os.getenv("CACHE_TTL_15MIN_SECONDS", "900")),
    "1h": int(os.getenv("CACHE_TTL_1H_SECONDS", "3600")),
    "4h": int(os.getenv("CACHE_TTL_4H_SECONDS", "14400")),
    "1day": int(os.getenv("CACHE_TTL_1DAY_SECONDS", "86400")),
}

QUOTA_GUARD_ENABLED = env_bool("QUOTA_GUARD_ENABLED", True)
QUOTA_BACKOFF_SECONDS = int(os.getenv("QUOTA_BACKOFF_SECONDS", "60"))
QUOTA_BACKOFF_MAX_SECONDS = int(os.getenv("QUOTA_BACKOFF_MAX_SECONDS", "3600"))
QUOTA_STALE_MAX_AGE_SECONDS = int(os.getenv("QUOTA_STALE_MAX_AGE_SECONDS", "172800"))


# Fast Check / Low Quota Mode
FAST_CHECK_ENABLED = env_bool("FAST_CHECK_ENABLED", True)
FAST_CHECK_INTERVAL_MINUTES = int(os.getenv("FAST_CHECK_INTERVAL_MINUTES", "1"))
MOVE_ALERT_CHECK_INTERVAL_MINUTES = int(os.getenv("MOVE_ALERT_CHECK_INTERVAL_MINUTES", "1"))

# Cache housekeeping
CACHE_MAX_ROWS_PER_INTERVAL = int(os.getenv("CACHE_MAX_ROWS_PER_INTERVAL", "400"))
CACHE_CLEANUP_INTERVAL_MINUTES = int(os.getenv("CACHE_CLEANUP_INTERVAL_MINUTES", "60"))
CACHE_MAX_FILE_AGE_SECONDS = int(os.getenv("CACHE_MAX_FILE_AGE_SECONDS", "604800"))  # 7 days


# Entry / Exit Signal Engine
ENTRY_SIGNAL_ENABLED = env_bool("ENTRY_SIGNAL_ENABLED", True)
EXIT_SIGNAL_ENABLED = env_bool("EXIT_SIGNAL_ENABLED", True)
ENTRY_SIGNAL_CHECK_INTERVAL_MINUTES = int(os.getenv("ENTRY_SIGNAL_CHECK_INTERVAL_MINUTES", "1"))
MIN_ENTRY_SCORE = int(os.getenv("MIN_ENTRY_SCORE", str(MIN_SCORE_TO_ALERT)))
MIN_RR_TO_ALERT = float(os.getenv("MIN_RR_TO_ALERT", "1.5"))
ENTRY_SIGNAL_COOLDOWN_MINUTES = int(os.getenv("ENTRY_SIGNAL_COOLDOWN_MINUTES", "45"))
EXIT_SIGNAL_COOLDOWN_MINUTES = int(os.getenv("EXIT_SIGNAL_COOLDOWN_MINUTES", "15"))
EXIT_ON_OPPOSITE_SIGNAL = env_bool("EXIT_ON_OPPOSITE_SIGNAL", True)
EXIT_ON_H1_INVALIDATION = env_bool("EXIT_ON_H1_INVALIDATION", True)
OPPOSITE_SIGNAL_MIN_SCORE = int(os.getenv("OPPOSITE_SIGNAL_MIN_SCORE", str(MIN_ENTRY_SCORE)))
MOVE_SL_TO_BE_AT_RR = float(os.getenv("MOVE_SL_TO_BE_AT_RR", str(BE_TRIGGER_RR)))
PARTIAL_TP_ALERT = env_bool("PARTIAL_TP_ALERT", True)
NEAR_SL_EXIT_ATR_MULTIPLIER = float(os.getenv("NEAR_SL_EXIT_ATR_MULTIPLIER", str(SL_WARNING_DISTANCE_ATR)))

app = Flask(__name__)
LAST_SIGNAL: Dict[str, Any] = {"status": "starting", "version": APP_VERSION}
LAST_ALERT_KEY: Optional[str] = None
scheduler = None
TELEGRAM_STATUS: Dict[str, Any] = {
    "enabled": TELEGRAM_POLLING_ENABLED,
    "last_run_utc": None,
    "last_success_utc": None,
    "last_error": None,
    "last_http_status": None,
    "last_updates_count": 0,
    "last_update_id": None,
    "webhook_deleted": False,
    "bot_username": None,
}
LAST_MOVE_ALERT_KEYS: set = set()

LAST_ENTRY_ALERT_KEY: Optional[str] = None
LAST_ENTRY_ALERT_TS: float = 0.0
LAST_EXIT_ALERT_KEYS: Dict[str, float] = {}
LAST_ENTRY_EXIT_STATUS: Dict[str, Any] = {
    "version": APP_VERSION,
    "last_run_utc": None,
    "last_success_utc": None,
    "last_error": None,
    "last_entry_signal": None,
    "last_exit_events_count": 0,
}


CACHE_LOCK = threading.RLock()
OHLC_CACHE: Dict[str, Dict[str, Any]] = {}

API_RUNTIME: Dict[str, Any] = {
    "requests_total": 0,
    "requests_success": 0,
    "cache_hits_fresh": 0,
    "cache_hits_stale": 0,
    "cache_misses": 0,
    "http_429_count": 0,
    "consecutive_429": 0,
    "blocked_until_ts": 0.0,
    "last_request_utc": None,
    "last_success_utc": None,
    "last_error": None,
    "last_http_status": None,
    "last_interval": None,
    "last_retry_after_seconds": None,
    "api_credits_used": None,
    "api_credits_left": None,
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def load_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_positions() -> List[Dict[str, Any]]:
    data = load_json(POSITIONS_FILE, {"positions": []})
    if isinstance(data, list):
        return data
    return data.get("positions", []) if isinstance(data, dict) else []


def save_positions(positions: List[Dict[str, Any]]) -> None:
    save_json(POSITIONS_FILE, {"version": APP_VERSION, "updated_utc": now_utc(), "positions": positions})


def next_position_id(positions: List[Dict[str, Any]]) -> int:
    ids = [int(p.get("id", 0)) for p in positions if str(p.get("id", "")).isdigit()]
    return max(ids, default=0) + 1



def _utc_ts() -> float:
    return time.time()


def _iso_from_ts(ts: float) -> Optional[str]:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _cache_ttl(interval: str) -> int:
    return int(CACHE_TTL_SECONDS.get(interval, 900))


def _serialize_df(df: pd.DataFrame) -> List[Dict[str, Any]]:
    records = df.copy()
    if "datetime" in records.columns:
        records["datetime"] = records["datetime"].astype(str)
    return records.to_dict(orient="records")


def _deserialize_df(records: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(records or [])
    if df.empty:
        return df
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)


def load_ohlc_cache() -> None:
    if not CACHE_ENABLED:
        return
    raw = load_json(CACHE_FILE, {"items": {}})
    items = raw.get("items", {}) if isinstance(raw, dict) else {}
    with CACHE_LOCK:
        for interval, payload in items.items():
            try:
                df = _deserialize_df(payload.get("records", []))
                if df.empty:
                    continue
                OHLC_CACHE[interval] = {
                    "df": df,
                    "fetched_ts": float(payload.get("fetched_ts", 0) or 0),
                    "outputsize": int(payload.get("outputsize", len(df)) or len(df)),
                    "source": payload.get("source", "disk"),
                }
            except Exception:
                continue


def save_ohlc_cache() -> None:
    if not CACHE_ENABLED:
        return
    with CACHE_LOCK:
        payload = {"version": APP_VERSION, "updated_utc": now_utc(), "items": {}}
        for interval, item in OHLC_CACHE.items():
            df = item.get("df")
            if df is None or getattr(df, "empty", True):
                continue
            payload["items"][interval] = {
                "fetched_ts": float(item.get("fetched_ts", 0) or 0),
                "outputsize": int(item.get("outputsize", len(df)) or len(df)),
                "source": item.get("source", "memory"),
                "records": _serialize_df(df),
            }
    try:
        save_json(CACHE_FILE, payload)
    except Exception as e:
        API_RUNTIME["last_error"] = f"cache_save: {type(e).__name__}: {e}"


def _cache_get(interval: str, outputsize: int, allow_stale: bool = False) -> Tuple[Optional[pd.DataFrame], Optional[Dict[str, Any]]]:
    if not CACHE_ENABLED:
        return None, None
    now_ts = _utc_ts()
    with CACHE_LOCK:
        item = OHLC_CACHE.get(interval)
        if not item:
            API_RUNTIME["cache_misses"] += 1
            return None, None
        df = item.get("df")
        if df is None or getattr(df, "empty", True):
            API_RUNTIME["cache_misses"] += 1
            return None, None
        age = max(0.0, now_ts - float(item.get("fetched_ts", 0) or 0))
        fresh = age <= _cache_ttl(interval)

        # Twelve Data zwraca `outputsize` rekordów, ale przy CLOSED_CANDLES_ONLY
        # usuwamy ostatnią, niedomkniętą świecę. Dlatego cache z 19 rekordami
        # jest prawidłowy dla zapytania outputsize=20.
        requested_rows = min(max(int(outputsize), 1), 200)
        closed_candle_adjustment = 1 if CLOSED_CANDLES_ONLY and requested_rows > 1 else 0
        min_required_rows = max(1, requested_rows - closed_candle_adjustment)
        enough_rows = len(df) >= min_required_rows

        if fresh and enough_rows:
            API_RUNTIME["cache_hits_fresh"] += 1
            return df.tail(outputsize).copy(), {
                "age_seconds": age,
                "fresh": True,
                "rows": len(df),
                "min_required_rows": min_required_rows,
            }

        # Dla stale fallback stosujemy tę samą logikę closed-candle.
        # Nie wymagamy sztywno 20 rekordów, bo prawidłowy cache może mieć 19.
        stale_min_required = max(1, min(min_required_rows, 20))
        if allow_stale and age <= QUOTA_STALE_MAX_AGE_SECONDS and len(df) >= stale_min_required:
            API_RUNTIME["cache_hits_stale"] += 1
            return df.tail(outputsize).copy(), {
                "age_seconds": age,
                "fresh": False,
                "rows": len(df),
                "min_required_rows": stale_min_required,
            }
        API_RUNTIME["cache_misses"] += 1
        return None, {"age_seconds": age, "fresh": fresh}


def _cache_put(interval: str, df: pd.DataFrame, outputsize: int, source: str = "api") -> None:
    if not CACHE_ENABLED or df is None or df.empty:
        return

    capped_df = df.tail(max(20, CACHE_MAX_ROWS_PER_INTERVAL)).copy()

    with CACHE_LOCK:
        current = OHLC_CACHE.get(interval)

        # Gdy aktualny cache ma więcej danych niż nowa odpowiedź API,
        # zachowujemy większy zestaw, ale odświeżamy timestamp.
        if current and len(current.get("df", [])) > len(capped_df):
            if source == "api":
                current["fetched_ts"] = _utc_ts()
                current["source"] = source
            # Ogranicz maksymalny rozmiar również dla istniejącego cache.
            current_df = current.get("df")
            if current_df is not None and not current_df.empty:
                current["df"] = current_df.tail(max(20, CACHE_MAX_ROWS_PER_INTERVAL)).copy()
            save_ohlc_cache()
            return

        OHLC_CACHE[interval] = {
            "df": capped_df,
            "fetched_ts": _utc_ts(),
            "outputsize": max(int(outputsize), len(capped_df)),
            "source": source,
        }

    save_ohlc_cache()


def cleanup_cache_job() -> None:
    """
    Ogranicza rozmiar pamięci cache i usuwa bardzo stare wpisy.
    Nie wykonuje żadnych zapytań do API.
    """
    if not CACHE_ENABLED:
        return

    now_ts = _utc_ts()
    changed = False

    with CACHE_LOCK:
        to_delete = []

        for interval, item in list(OHLC_CACHE.items()):
            df = item.get("df")
            fetched_ts = float(item.get("fetched_ts", 0) or 0)
            age = max(0.0, now_ts - fetched_ts)

            if age > CACHE_MAX_FILE_AGE_SECONDS:
                to_delete.append(interval)
                continue

            if df is not None and not df.empty and len(df) > CACHE_MAX_ROWS_PER_INTERVAL:
                item["df"] = df.tail(CACHE_MAX_ROWS_PER_INTERVAL).copy()
                changed = True

        for interval in to_delete:
            OHLC_CACHE.pop(interval, None)
            changed = True

    if changed:
        save_ohlc_cache()


def quota_guard_active() -> bool:
    if not QUOTA_GUARD_ENABLED:
        return False
    return _utc_ts() < float(API_RUNTIME.get("blocked_until_ts", 0) or 0)


def quota_guard_remaining_seconds() -> int:
    return max(0, int(float(API_RUNTIME.get("blocked_until_ts", 0) or 0) - _utc_ts()))


def _activate_quota_guard(retry_after_seconds: Optional[int] = None) -> int:
    API_RUNTIME["http_429_count"] += 1
    API_RUNTIME["consecutive_429"] += 1
    consecutive = max(1, int(API_RUNTIME["consecutive_429"]))
    backoff = retry_after_seconds or min(
        QUOTA_BACKOFF_MAX_SECONDS,
        QUOTA_BACKOFF_SECONDS * (2 ** (consecutive - 1)),
    )
    backoff = max(1, int(backoff))
    API_RUNTIME["blocked_until_ts"] = _utc_ts() + backoff
    API_RUNTIME["last_retry_after_seconds"] = backoff
    return backoff


def _update_api_headers(headers: Dict[str, Any]) -> None:
    # Capture the most useful provider/rate headers when present.
    lowered = {str(k).lower(): v for k, v in headers.items()}
    for key in ("api-credits-used", "x-api-credits-used"):
        if key in lowered:
            API_RUNTIME["api_credits_used"] = lowered[key]
            break
    for key in ("api-credits-left", "x-api-credits-left", "x-ratelimit-remaining"):
        if key in lowered:
            API_RUNTIME["api_credits_left"] = lowered[key]
            break


def api_runtime_snapshot() -> Dict[str, Any]:
    result = dict(API_RUNTIME)
    result["quota_guard_active"] = quota_guard_active()
    result["quota_guard_remaining_seconds"] = quota_guard_remaining_seconds()
    result["blocked_until_utc"] = _iso_from_ts(float(API_RUNTIME.get("blocked_until_ts", 0) or 0))
    result["cache_enabled"] = CACHE_ENABLED
    result["cache_allow_stale"] = CACHE_ALLOW_STALE
    return result


def fast_check_status_snapshot() -> Dict[str, Any]:
    return {
        "enabled": FAST_CHECK_ENABLED,
        "fast_check_interval_minutes": FAST_CHECK_INTERVAL_MINUTES,
        "move_alert_check_interval_minutes": MOVE_ALERT_CHECK_INTERVAL_MINUTES,
        "cache_ttl_seconds": dict(CACHE_TTL_SECONDS),
        "cache_max_rows_per_interval": CACHE_MAX_ROWS_PER_INTERVAL,
        "entry_signal_enabled": ENTRY_SIGNAL_ENABLED,
        "exit_signal_enabled": EXIT_SIGNAL_ENABLED,
        "entry_signal_check_interval_minutes": ENTRY_SIGNAL_CHECK_INTERVAL_MINUTES,
        "min_entry_score": MIN_ENTRY_SCORE,
        "min_rr_to_alert": MIN_RR_TO_ALERT,
        "last_entry_exit_error": LAST_ENTRY_EXIT_STATUS.get("last_error"),
        "last_entry_exit_success_utc": LAST_ENTRY_EXIT_STATUS.get("last_success_utc"),
        "cache_cleanup_interval_minutes": CACHE_CLEANUP_INTERVAL_MINUTES,
    }


def cache_status_snapshot() -> Dict[str, Any]:
    now_ts = _utc_ts()
    out: Dict[str, Any] = {}
    with CACHE_LOCK:
        for interval, item in OHLC_CACHE.items():
            df = item.get("df")
            fetched_ts = float(item.get("fetched_ts", 0) or 0)
            age = max(0.0, now_ts - fetched_ts)
            rows_count = len(df) if df is not None else 0
            stored_outputsize = int(item.get("outputsize", rows_count) or rows_count or 1)
            requested_rows = min(max(stored_outputsize, 1), 200)
            closed_candle_adjustment = 1 if CLOSED_CANDLES_ONLY and requested_rows > 1 else 0
            min_required_rows = max(1, requested_rows - closed_candle_adjustment)

            out[interval] = {
                "rows": rows_count,
                "age_seconds": round(age, 1),
                "ttl_seconds": _cache_ttl(interval),
                "fresh": age <= _cache_ttl(interval),
                "fetched_utc": _iso_from_ts(fetched_ts),
                "source": item.get("source"),
                "stored_outputsize": stored_outputsize,
                "min_required_rows": min_required_rows,
                "usable_for_stored_outputsize": rows_count >= min_required_rows,
            }
    return out


def fetch_ohlc(interval: str, outputsize: int = 300, force_refresh: bool = False) -> pd.DataFrame:
    """
    Smart MTF fetch:
    - fresh cache first,
    - quota guard blocks repeated API calls after 429,
    - stale cache fallback during provider/rate failures,
    - shared cache between signals, position monitor and move alerts.
    """
    if not TWELVE_DATA_API_KEY:
        stale_df, _ = _cache_get(interval, outputsize, allow_stale=True)
        if stale_df is not None:
            return stale_df
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")

    if not force_refresh:
        cached_df, _ = _cache_get(interval, outputsize, allow_stale=False)
        if cached_df is not None:
            return cached_df

    if quota_guard_active():
        stale_df, meta = _cache_get(interval, outputsize, allow_stale=CACHE_ALLOW_STALE)
        if stale_df is not None:
            return stale_df
        raise RuntimeError(
            f"Quota Guard active for {quota_guard_remaining_seconds()}s; no usable cache for {interval}"
        )

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
        "timezone": os.getenv("TIMEZONE", "Europe/Warsaw"),
    }

    API_RUNTIME["requests_total"] += 1
    API_RUNTIME["last_request_utc"] = now_utc()
    API_RUNTIME["last_interval"] = interval

    try:
        r = requests.get(url, params=params, timeout=20)
        API_RUNTIME["last_http_status"] = r.status_code
        _update_api_headers(r.headers)

        if r.status_code == 429:
            retry_after_raw = r.headers.get("Retry-After")
            retry_after = None
            try:
                retry_after = int(float(retry_after_raw)) if retry_after_raw else None
            except Exception:
                retry_after = None
            backoff = _activate_quota_guard(retry_after)
            API_RUNTIME["last_error"] = f"HTTP 429 Too Many Requests; Quota Guard {backoff}s"

            stale_df, _ = _cache_get(interval, outputsize, allow_stale=CACHE_ALLOW_STALE)
            if stale_df is not None:
                return stale_df
            raise RuntimeError(f"HTTP 429 Too Many Requests; Quota Guard active {backoff}s")

        r.raise_for_status()
        data = r.json()
        if "values" not in data:
            raise RuntimeError(f"Bad TwelveData response: {data}")

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().sort_values("datetime").reset_index(drop=True)
        if CLOSED_CANDLES_ONLY and len(df) > 2:
            df = df.iloc[:-1].copy()

        API_RUNTIME["requests_success"] += 1
        API_RUNTIME["consecutive_429"] = 0
        API_RUNTIME["blocked_until_ts"] = 0.0
        API_RUNTIME["last_success_utc"] = now_utc()
        API_RUNTIME["last_error"] = None

        _cache_put(interval, df, outputsize, source="api")
        return df.tail(outputsize).copy()

    except Exception as e:
        if "429" not in str(e):
            API_RUNTIME["last_error"] = f"{type(e).__name__}: {e}"

        stale_df, _ = _cache_get(interval, outputsize, allow_stale=CACHE_ALLOW_STALE)
        if stale_df is not None:
            return stale_df
        raise


def ema(s: pd.Series, period: int) -> pd.Series:
    return s.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/period, adjust=False).mean()
    ma_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema20"] = ema(out["close"], 20)
    out["ema50"] = ema(out["close"], 50)
    out["ema200"] = ema(out["close"], 200)
    out["rsi14"] = rsi(out["close"], 14)
    out["atr14"] = atr(out, 14)
    return out


def swing_points(df: pd.DataFrame, left: int = 2, right: int = 2) -> Dict[str, List[Dict[str, float]]]:
    highs, lows = [], []
    for i in range(left, len(df) - right):
        window = df.iloc[i-left:i+right+1]
        row = df.iloc[i]
        if row.high == window.high.max():
            highs.append({"i": i, "price": float(row.high)})
        if row.low == window.low.min():
            lows.append({"i": i, "price": float(row.low)})
    return {"highs": highs[-10:], "lows": lows[-10:]}


def market_structure(df: pd.DataFrame) -> Dict[str, Any]:
    sp = swing_points(df)
    highs, lows = sp["highs"], sp["lows"]
    close = float(df.close.iloc[-1])
    direction = "NEUTRAL"
    bos = None
    choch = None
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1]["price"] > highs[-2]["price"]
        hl = lows[-1]["price"] > lows[-2]["price"]
        lh = highs[-1]["price"] < highs[-2]["price"]
        ll = lows[-1]["price"] < lows[-2]["price"]
        if hh and hl:
            direction = "UP"
        elif lh and ll:
            direction = "DOWN"
        last_high = highs[-1]["price"]
        last_low = lows[-1]["price"]
        if close > last_high:
            bos = "BULLISH_BOS"
        elif close < last_low:
            bos = "BEARISH_BOS"
        if direction == "DOWN" and close > last_high:
            choch = "BULLISH_CHOCH"
        elif direction == "UP" and close < last_low:
            choch = "BEARISH_CHOCH"
    return {"direction": direction, "bos": bos, "choch": choch, "swings": sp}


def liquidity_sweep(df: pd.DataFrame) -> Dict[str, Any]:
    sp = swing_points(df)
    last = df.iloc[-1]
    result = {"bullish_sweep": False, "bearish_sweep": False, "level": None}
    if sp["lows"]:
        prev_low = sp["lows"][-1]["price"]
        if last.low < prev_low and last.close > prev_low:
            result = {"bullish_sweep": True, "bearish_sweep": False, "level": prev_low}
    if sp["highs"]:
        prev_high = sp["highs"][-1]["price"]
        if last.high > prev_high and last.close < prev_high:
            result = {"bullish_sweep": False, "bearish_sweep": True, "level": prev_high}
    return result


def fair_value_gap(df: pd.DataFrame) -> Dict[str, Any]:
    gaps = []
    for i in range(2, len(df)):
        c1 = df.iloc[i-2]
        c3 = df.iloc[i]
        if c1.high < c3.low:
            gaps.append({"type": "BULLISH_FVG", "low": float(c1.high), "high": float(c3.low), "i": i})
        if c1.low > c3.high:
            gaps.append({"type": "BEARISH_FVG", "low": float(c3.high), "high": float(c1.low), "i": i})
    return {"latest": gaps[-1] if gaps else None, "count": len(gaps)}


def order_block(df: pd.DataFrame) -> Dict[str, Any]:
    a = atr(df, 14)
    latest = None
    for i in range(5, len(df)):
        prev = df.iloc[i-1]
        cur = df.iloc[i]
        impulse = abs(cur.close - cur.open) > float(a.iloc[i]) * 1.2
        if not impulse:
            continue
        if cur.close > cur.open and prev.close < prev.open:
            latest = {"type": "BULLISH_OB", "low": float(prev.low), "high": float(prev.high), "i": i-1}
        elif cur.close < cur.open and prev.close > prev.open:
            latest = {"type": "BEARISH_OB", "low": float(prev.low), "high": float(prev.high), "i": i-1}
    return {"latest": latest}


def trend(df: pd.DataFrame) -> str:
    last = df.iloc[-1]
    if last.close > last.ema20 > last.ema50:
        return "UP"
    if last.close < last.ema20 < last.ema50:
        return "DOWN"
    return "NEUTRAL"


def current_price_and_atr() -> Tuple[float, float]:
    """
    Fast price + H1 volatility:
    - price from last closed 5min candle when available,
    - ATR from H1 for stable SL/TP sizing.
    Cache keeps this low-quota.
    """
    h1 = add_indicators(fetch_ohlc("1h", 120))
    atr_value = float(h1.atr14.iloc[-1])

    try:
        m5 = add_indicators(fetch_ohlc("5min", 80))
        price = float(m5.close.iloc[-1])
    except Exception:
        price = float(h1.close.iloc[-1])

    return price, atr_value


def risk_plan_for_position(side: str, entry: float, atr_value: Optional[float] = None) -> Dict[str, float]:
    if atr_value is None:
        _, atr_value = current_price_and_atr()
    distance = max(float(atr_value) * AUTO_RISK_ATR_MULTIPLIER, AUTO_RISK_MIN_POINTS)
    side = side.upper()
    if side == "SELL":
        sl = entry + distance
        tp1 = entry - distance * TP1_RR
        tp2 = entry - distance * TP2_RR
        tp3 = entry - distance * TP3_RR
    elif side == "BUY":
        sl = entry - distance
        tp1 = entry + distance * TP1_RR
        tp2 = entry + distance * TP2_RR
        tp3 = entry + distance * TP3_RR
    else:
        raise ValueError("side must be BUY or SELL")
    return {"entry": round(entry, 2), "sl": round(sl, 2), "tp1": round(tp1, 2), "tp2": round(tp2, 2), "tp3": round(tp3, 2), "risk_distance": round(distance, 2)}


def build_signal() -> Dict[str, Any]:
    frames = {tf: add_indicators(fetch_ohlc(tf)) for tf in ["15min", "1h", "4h", "1day"]}
    m15, h1, h4, d1 = frames["15min"], frames["1h"], frames["4h"], frames["1day"]
    price = float(h1.close.iloc[-1])
    atr_h1 = float(h1.atr14.iloc[-1])
    trends = {"M15": trend(m15), "H1": trend(h1), "H4": trend(h4), "D1": trend(d1)}
    ms_h1, ms_h4 = market_structure(h1), market_structure(h4)
    sweep = liquidity_sweep(h1)
    fvg = fair_value_gap(h1)
    ob = order_block(h1)

    score_sell = 0
    score_buy = 0
    reasons = []

    for tf in ["H4", "D1"]:
        if trends[tf] == "DOWN":
            score_sell += 15; reasons.append(f"{tf} trend DOWN")
        if trends[tf] == "UP":
            score_buy += 15; reasons.append(f"{tf} trend UP")
    if trends["H1"] == "DOWN": score_sell += 10
    if trends["H1"] == "UP": score_buy += 10
    if ms_h1["bos"] == "BEARISH_BOS": score_sell += 15; reasons.append("H1 bearish BOS")
    if ms_h1["bos"] == "BULLISH_BOS": score_buy += 15; reasons.append("H1 bullish BOS")
    if ms_h4["direction"] == "DOWN": score_sell += 10
    if ms_h4["direction"] == "UP": score_buy += 10
    if sweep["bearish_sweep"]: score_sell += 15; reasons.append("liquidity sweep above highs")
    if sweep["bullish_sweep"]: score_buy += 15; reasons.append("liquidity sweep below lows")
    if fvg["latest"] and fvg["latest"]["type"] == "BEARISH_FVG": score_sell += 10
    if fvg["latest"] and fvg["latest"]["type"] == "BULLISH_FVG": score_buy += 10
    if ob["latest"] and ob["latest"]["type"] == "BEARISH_OB": score_sell += 10
    if ob["latest"] and ob["latest"]["type"] == "BULLISH_OB": score_buy += 10

    if score_sell >= score_buy + 15 and score_sell >= MIN_SCORE_TO_ALERT:
        side = "SELL"; score = score_sell
        rp = risk_plan_for_position("SELL", price, atr_h1)
    elif score_buy >= score_sell + 15 and score_buy >= MIN_SCORE_TO_ALERT:
        side = "BUY"; score = score_buy
        rp = risk_plan_for_position("BUY", price, atr_h1)
    else:
        side = "NO_TRADE"; score = max(score_buy, score_sell)
        rp = {"entry": round(price, 2), "sl": None, "tp1": None, "tp2": None, "tp3": None, "risk_distance": None}

    return {
        "version": APP_VERSION,
        "status": "ok",
        "symbol": SYMBOL,
        "time_utc": now_utc(),
        "signal": side,
        "score": int(score),
        "price": round(price, 2),
        "trend": trends,
        "institutional": {
            "market_structure_h1": ms_h1,
            "market_structure_h4": ms_h4,
            "liquidity_sweep_h1": sweep,
            "fair_value_gap_h1": fvg,
            "order_block_h1": ob,
        },
        "risk_plan": rp | {"risk_note": "Risk max 1-2% capital. Signal is rule score, not probability."},
        "reasons": reasons,
        "closed_candles": CLOSED_CANDLES_ONLY,
    }


def detect_big_move(interval: str) -> Optional[Dict[str, Any]]:
    df = add_indicators(fetch_ohlc(interval, 80))
    if len(df) < 20:
        return None
    last = df.iloc[-1]
    body = float(last.close - last.open)
    rng = float(last.high - last.low)
    atr_value = float(last.atr14)
    if atr_value <= 0 or rng <= 0:
        return None
    body_atr = abs(body) / atr_value
    range_atr = rng / atr_value
    body_ratio = abs(body) / rng
    if body_atr >= MOVE_BODY_ATR_MIN or (range_atr >= MOVE_RANGE_ATR_MIN and body_ratio >= MOVE_BODY_RATIO_MIN):
        direction = "GÓRĘ" if body > 0 else "DÓŁ"
        quality = "EXTREME" if body_atr >= 1.4 or range_atr >= 1.6 else "ELEVATED"
        return {
            "interval": interval,
            "direction": direction,
            "price": round(float(last.close), 2),
            "candle_change": round(body, 2),
            "body_atr": round(body_atr, 2),
            "range_atr": round(range_atr, 2),
            "body_ratio": round(body_ratio, 2),
            "quality": quality,
            "datetime": str(last.datetime),
        }
    return None


def format_move_alert(m: Dict[str, Any]) -> str:
    return (
        f"💥 GOLD MOVE ALERT — MOCNY RUCH W {m['direction']}\n"
        f"Symbol: {SYMBOL} | Interwał: {m['interval']}\n"
        f"Poziom: {m['price']} | Zmiana świecy: {m['candle_change']} pkt\n"
        f"Body/ATR: {m['body_atr']} | Range/ATR: {m['range_atr']}\n"
        f"Jakość ruchu: {m['quality']} | Body ratio: {m['body_ratio']}\n\n"
        f"⚠️ To jest alert zmienności, nie automatyczny sygnał BUY/SELL."
    )


def check_move_alerts() -> None:
    global LAST_MOVE_ALERT_KEYS
    if not MOVE_ALERT_ENABLED:
        return
    for interval in MOVE_ALERT_INTERVALS:
        try:
            move = detect_big_move(interval)
            if not move:
                continue
            key = f"{interval}:{move['datetime']}:{move['direction']}"
            if key not in LAST_MOVE_ALERT_KEYS:
                send_telegram(format_move_alert(move))
                LAST_MOVE_ALERT_KEYS.add(key)
                LAST_MOVE_ALERT_KEYS = set(list(LAST_MOVE_ALERT_KEYS)[-50:])
        except Exception as e:
            print(f"MOVE ALERT ERROR {interval}: {e}")


def format_signal(s: Dict[str, Any]) -> str:
    rp = s["risk_plan"]
    inst = s["institutional"]
    return (
        f"🟣 GOLD AI BOT v6.5 — SMART POSITION MANAGER\n"
        f"Symbol: {s['symbol']}\nSygnał: {s['signal']}\nScore regułowy: {s['score']}/100\n"
        f"Cena: {s['price']}\nTrend M15/H1/H4/D1: {s['trend']['M15']} / {s['trend']['H1']} / {s['trend']['H4']} / {s['trend']['D1']}\n\n"
        f"Market Structure H1: {inst['market_structure_h1']['direction']} | BOS: {inst['market_structure_h1']['bos']} | CHOCH: {inst['market_structure_h1']['choch']}\n"
        f"Liquidity Sweep H1: {inst['liquidity_sweep_h1']}\n"
        f"FVG H1: {inst['fair_value_gap_h1']['latest']}\n"
        f"Order Block H1: {inst['order_block_h1']['latest']}\n\n"
        f"Entry: {rp['entry']}\nSL: {rp['sl']}\nTP1: {rp['tp1']}\nTP2: {rp['tp2']}\nTP3: {rp['tp3']}\n\n"
        f"Komendy: /position SELL {rp['entry']} albo /position BUY {rp['entry']}\n"
        f"Zasady: ryzyko max 1–2%, nie przesuwaj SL dalej od wejścia, nie dokładaj do straty."
    )


def send_telegram(text: str, chat_id: Optional[str] = None) -> None:
    if not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Telegram wyłączony albo brak TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        raise RuntimeError("Brak TELEGRAM_CHAT_ID i brak chat_id z wiadomości")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": target_chat_id, "text": text}, timeout=15)
    TELEGRAM_STATUS["last_http_status"] = r.status_code
    r.raise_for_status()
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram sendMessage error: {payload}")



def format_position(p: Dict[str, Any], price: Optional[float] = None) -> str:
    side = p["side"]
    entry = float(p["entry"])
    sl = p.get("sl")
    tp1 = p.get("tp1")
    tp2 = p.get("tp2")
    tp3 = p.get("tp3")
    pnl_points = None
    rr = None
    if price is not None:
        pnl_points = (entry - price) if side == "SELL" else (price - entry)
        risk = abs(float(sl) - entry) if sl else None
        rr = pnl_points / risk if risk else None
    status = ""
    if pnl_points is not None:
        status = f"\nAktualnie: {round(price, 2)} | PnL pkt: {round(pnl_points, 2)} | RR: {round(rr, 2) if rr is not None else '-'}"
    return (
        f"#{p['id']} {side} {entry} | wolumen {p.get('volume', DEFAULT_POSITION_VOLUME)}\n"
        f"SL: {sl} | TP1: {tp1} | TP2: {tp2} | TP3: {tp3}{status}"
    )


def add_position(side: str, entry: float, volume: Optional[float] = None, chat_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Dodaje pozycję nawet wtedy, gdy Twelve Data chwilowo nie odpowiada.
    SL/TP liczone są na podstawie H1 ATR, a przy awarii używany jest DEFAULT_ATR_H1.
    """
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("Użyj BUY albo SELL")

    atr_value = None
    atr_source = "twelve_data_h1"

    try:
        _, atr_value = current_price_and_atr()
    except Exception as market_error:
        atr_value = DEFAULT_ATR_H1
        atr_source = "default_env"

    rp = risk_plan_for_position(side, entry, atr_value)
    positions = load_positions()
    p = {
        "id": next_position_id(positions),
        "symbol": SYMBOL,
        "side": side,
        "entry": round(entry, 2),
        "volume": float(volume or DEFAULT_POSITION_VOLUME),
        "sl": rp["sl"],
        "tp1": rp["tp1"],
        "tp2": rp["tp2"],
        "tp3": rp["tp3"],
        "risk_distance": rp["risk_distance"],
        "atr_used": round(float(atr_value), 2),
        "atr_source": atr_source,
        "created_utc": now_utc(),
        "status": "OPEN",
        "alerts_sent": [],
        "chat_id": str(chat_id or TELEGRAM_CHAT_ID or ""),
        "note": (
            "SL/TP calculated automatically from H1 ATR. "
            "If market data was unavailable, fallback ATR was used. "
            "Update broker manually unless you connect broker API."
        ),
    }
    positions.append(p)
    save_positions(positions)
    return p


def close_position(position_id: int) -> bool:
    positions = load_positions()
    new_positions = [p for p in positions if int(p.get("id", -1)) != int(position_id)]
    save_positions(new_positions)
    return len(new_positions) != len(positions)


def update_position(position_id: int, **updates: Any) -> Optional[Dict[str, Any]]:
    positions = load_positions()
    updated = None
    for p in positions:
        if int(p.get("id", -1)) == int(position_id):
            for k, v in updates.items():
                if v is not None:
                    p[k] = v
            p["updated_utc"] = now_utc()
            updated = p
            break
    save_positions(positions)
    return updated


def position_monitor_job() -> None:
    try:
        positions = load_positions()
        # Zero positions = zero market-data requests.
        if not positions:
            return
        price, atr_value = current_price_and_atr()
        changed = False
        for p in positions:
            side = p.get("side")
            entry = float(p.get("entry"))
            sl = safe_float(p.get("sl"))
            tp1 = safe_float(p.get("tp1"))
            tp2 = safe_float(p.get("tp2"))
            tp3 = safe_float(p.get("tp3"))
            alerts = set(p.get("alerts_sent", []))
            risk = abs(sl - entry) if sl is not None else None
            pnl_points = (entry - price) if side == "SELL" else (price - entry)
            rr = pnl_points / risk if risk else 0
            chat_id = p.get("chat_id") or TELEGRAM_CHAT_ID

            def alert_once(key: str, text: str):
                nonlocal changed
                if key not in alerts:
                    send_telegram(text, chat_id=chat_id)
                    alerts.add(key)
                    p["alerts_sent"] = sorted(alerts)
                    changed = True

            if risk and rr >= BE_TRIGGER_RR:
                alert_once(
                    f"BE_{BE_TRIGGER_RR}",
                    f"🛡️ Pozycja #{p['id']} {side}: osiągnięto około RR {round(rr, 2)}. Rozważ przesunięcie SL na BE: {entry}.\nCena: {round(price, 2)}",
                )
            for tp_key, tp_value in [("TP1", tp1), ("TP2", tp2), ("TP3", tp3)]:
                if tp_value is None:
                    continue
                hit = price <= tp_value if side == "SELL" else price >= tp_value
                near = abs(price - tp_value) <= atr_value * TP_WARNING_DISTANCE_ATR
                if hit:
                    alert_once(f"HIT_{tp_key}", f"🎯 Pozycja #{p['id']} {side}: osiągnięto {tp_key} {tp_value}. Aktualna cena: {round(price, 2)}")
                elif near:
                    alert_once(f"NEAR_{tp_key}", f"⏳ Pozycja #{p['id']} {side}: cena blisko {tp_key} {tp_value}. Aktualna cena: {round(price, 2)}")
            if sl is not None:
                sl_hit = price >= sl if side == "SELL" else price <= sl
                sl_near = abs(price - sl) <= atr_value * SL_WARNING_DISTANCE_ATR
                if sl_hit:
                    alert_once("HIT_SL", f"🛑 Pozycja #{p['id']} {side}: cena dotknęła/przebiła SL {sl}. Aktualna cena: {round(price, 2)}")
                elif sl_near:
                    alert_once("NEAR_SL", f"⚠️ Pozycja #{p['id']} {side}: cena blisko SL {sl}. Aktualna cena: {round(price, 2)}")
        if changed:
            save_positions(positions)
    except Exception as e:
        print(f"POSITION MONITOR ERROR: {e}")



def opposite_side(side: str) -> str:
    side = str(side).upper()
    return "BUY" if side == "SELL" else "SELL"


def rr_for_plan(side: str, entry: float, sl: float, tp: float) -> Optional[float]:
    try:
        risk = abs(float(entry) - float(sl))
        if risk <= 0:
            return None
        reward = (float(tp) - float(entry)) if side == "BUY" else (float(entry) - float(tp))
        return reward / risk
    except Exception:
        return None


def evaluate_entry_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "enabled": ENTRY_SIGNAL_ENABLED,
        "valid": False,
        "status": "no_trade",
        "reason": None,
        "signal": None,
    }

    if not ENTRY_SIGNAL_ENABLED:
        result.update({"status": "disabled", "reason": "ENTRY_SIGNAL_ENABLED=false"})
        return result

    if not signal or signal.get("status") == "error":
        result.update({"status": "error", "reason": signal.get("error") if isinstance(signal, dict) else "missing signal"})
        return result

    side = str(signal.get("signal", "NO_TRADE")).upper()
    score = int(signal.get("score", 0) or 0)
    rp = signal.get("risk_plan") or {}

    if side not in ("BUY", "SELL"):
        result.update({"status": "no_trade", "reason": "main signal is NO_TRADE", "score": score})
        return result

    entry = safe_float(rp.get("entry"))
    sl = safe_float(rp.get("sl"))
    tp1 = safe_float(rp.get("tp1"))
    tp2 = safe_float(rp.get("tp2"))
    tp3 = safe_float(rp.get("tp3"))
    risk_distance = safe_float(rp.get("risk_distance"))

    if entry is None or sl is None or tp1 is None or not risk_distance:
        result.update({"status": "invalid_plan", "reason": "missing entry/sl/tp/risk"})
        return result

    rr_tp1 = rr_for_plan(side, entry, sl, tp1)

    valid = (
        score >= MIN_ENTRY_SCORE
        and rr_tp1 is not None
        and rr_tp1 >= MIN_RR_TO_ALERT
    )

    result.update({
        "valid": valid,
        "status": "entry_signal" if valid else "filtered",
        "reason": None if valid else f"score/rr filter not met: score={score}, rr_tp1={round(rr_tp1, 2) if rr_tp1 is not None else None}",
        "signal": side,
        "score": score,
        "entry": round(entry, 2),
        "sl": round(sl, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2) if tp2 is not None else None,
        "tp3": round(tp3, 2) if tp3 is not None else None,
        "risk_distance": round(risk_distance, 2),
        "rr_to_tp1": round(rr_tp1, 2) if rr_tp1 is not None else None,
        "trend": signal.get("trend"),
        "reasons": signal.get("reasons", []),
        "time_utc": now_utc(),
    })
    return result


def format_entry_signal_alert(e: Dict[str, Any]) -> str:
    side = e.get("signal")
    emoji = "🟢" if side == "BUY" else "🔴"
    return (
        f"{emoji} GOLD ENTRY SIGNAL — {side}\n\n"
        f"Symbol: {SYMBOL}\n"
        f"Score regułowy: {e.get('score')}/100\n"
        f"RR do TP1: {e.get('rr_to_tp1')}\n\n"
        f"Entry: {e.get('entry')}\n"
        f"SL: {e.get('sl')}\n"
        f"TP1: {e.get('tp1')}\n"
        f"TP2: {e.get('tp2')}\n"
        f"TP3: {e.get('tp3')}\n\n"
        f"Trend M15/H1/H4/D1: "
        f"{(e.get('trend') or {}).get('M15')} / {(e.get('trend') or {}).get('H1')} / "
        f"{(e.get('trend') or {}).get('H4')} / {(e.get('trend') or {}).get('D1')}\n"
        f"Powody: {', '.join(e.get('reasons') or []) or '-'}\n\n"
        f"Zasady: ryzyko max 1–2%, nie dokładaj do straty, SL wpisz ręcznie u brokera."
    )


def should_send_entry_alert(entry_signal: Dict[str, Any]) -> bool:
    global LAST_ENTRY_ALERT_KEY, LAST_ENTRY_ALERT_TS
    if not entry_signal.get("valid"):
        return False

    key = (
        f"{entry_signal.get('signal')}:"
        f"{entry_signal.get('entry')}:"
        f"{entry_signal.get('sl')}:"
        f"{entry_signal.get('score')}"
    )
    now_ts = _utc_ts()
    cooldown = max(60, ENTRY_SIGNAL_COOLDOWN_MINUTES * 60)

    if key == LAST_ENTRY_ALERT_KEY and (now_ts - LAST_ENTRY_ALERT_TS) < cooldown:
        return False

    LAST_ENTRY_ALERT_KEY = key
    LAST_ENTRY_ALERT_TS = now_ts
    return True


def latest_h1_invalidation(signal: Optional[Dict[str, Any]], side: str) -> Optional[float]:
    try:
        inst = (signal or {}).get("institutional") or {}
        swings = ((inst.get("market_structure_h1") or {}).get("swings") or {})
        if side == "SELL":
            highs = swings.get("highs") or []
            return safe_float(highs[-1].get("price")) if highs else None
        if side == "BUY":
            lows = swings.get("lows") or []
            return safe_float(lows[-1].get("price")) if lows else None
    except Exception:
        return None
    return None


def evaluate_exit_signals(current_signal: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not EXIT_SIGNAL_ENABLED:
        return events

    positions = load_positions()
    if not positions:
        return events

    price, atr_value = current_price_and_atr()
    signal_side = str((current_signal or {}).get("signal", "NO_TRADE")).upper()
    signal_score = int((current_signal or {}).get("score", 0) or 0)

    for p in positions:
        try:
            position_id = int(p.get("id"))
            side = str(p.get("side")).upper()
            entry = float(p.get("entry"))
            sl = safe_float(p.get("sl"))
            tp1 = safe_float(p.get("tp1"))
            tp2 = safe_float(p.get("tp2"))
            tp3 = safe_float(p.get("tp3"))
            risk = abs(float(sl) - entry) if sl is not None else None
            pnl_points = (entry - price) if side == "SELL" else (price - entry)
            rr = pnl_points / risk if risk and risk > 0 else None
            opposite = opposite_side(side)

            base = {
                "position_id": position_id,
                "side": side,
                "entry": round(entry, 2),
                "price": round(float(price), 2),
                "sl": round(sl, 2) if sl is not None else None,
                "tp1": round(tp1, 2) if tp1 is not None else None,
                "tp2": round(tp2, 2) if tp2 is not None else None,
                "tp3": round(tp3, 2) if tp3 is not None else None,
                "pnl_points": round(float(pnl_points), 2),
                "rr": round(rr, 2) if rr is not None else None,
                "atr_h1": round(float(atr_value), 2),
                "time_utc": now_utc(),
            }

            # 1) SL hit / near SL
            if sl is not None:
                sl_hit = price >= sl if side == "SELL" else price <= sl
                sl_near = abs(price - sl) <= atr_value * NEAR_SL_EXIT_ATR_MULTIPLIER
                if sl_hit:
                    events.append(base | {
                        "type": "EXIT_NOW_SL_HIT",
                        "priority": "HIGH",
                        "dedupe_key": f"{position_id}:EXIT_NOW_SL_HIT",
                        "message": f"Cena dotknęła/przebiła SL {round(sl, 2)}.",
                    })
                elif sl_near:
                    events.append(base | {
                        "type": "EXIT_RISK_NEAR_SL",
                        "priority": "MEDIUM",
                        "dedupe_key": f"{position_id}:EXIT_RISK_NEAR_SL",
                        "message": f"Cena jest blisko SL {round(sl, 2)}.",
                    })

            # 2) Opposite signal
            if (
                EXIT_ON_OPPOSITE_SIGNAL
                and signal_side == opposite
                and signal_score >= OPPOSITE_SIGNAL_MIN_SCORE
            ):
                events.append(base | {
                    "type": "EXIT_OR_REDUCE_OPPOSITE_SIGNAL",
                    "priority": "HIGH",
                    "dedupe_key": f"{position_id}:OPPOSITE:{signal_side}:{signal_score}",
                    "message": f"Pojawił się przeciwny sygnał {signal_side} z wynikiem {signal_score}/100.",
                })

            # 3) H1 structural invalidation
            invalidation = latest_h1_invalidation(current_signal, side) if EXIT_ON_H1_INVALIDATION else None
            if invalidation is not None:
                invalidated = price >= invalidation if side == "SELL" else price <= invalidation
                if invalidated:
                    events.append(base | {
                        "type": "EXIT_INVALIDATION_H1",
                        "priority": "HIGH",
                        "dedupe_key": f"{position_id}:H1_INVALIDATION:{round(invalidation, 2)}",
                        "invalidation_level": round(invalidation, 2),
                        "message": f"Poziom zanegowania H1 {round(invalidation, 2)} został naruszony.",
                    })

            # 4) BE management
            if rr is not None and rr >= MOVE_SL_TO_BE_AT_RR:
                events.append(base | {
                    "type": "MOVE_SL_TO_BE",
                    "priority": "MEDIUM",
                    "dedupe_key": f"{position_id}:MOVE_SL_TO_BE:{MOVE_SL_TO_BE_AT_RR}",
                    "message": f"Pozycja osiągnęła ok. RR {round(rr, 2)}. Rozważ SL na BE: {round(entry, 2)}.",
                })

            # 5) Partial TP management
            if PARTIAL_TP_ALERT and tp1 is not None:
                tp1_hit = price <= tp1 if side == "SELL" else price >= tp1
                if tp1_hit:
                    events.append(base | {
                        "type": "TAKE_PARTIAL_TP1",
                        "priority": "MEDIUM",
                        "dedupe_key": f"{position_id}:TAKE_PARTIAL_TP1",
                        "message": f"TP1 {round(tp1, 2)} osiągnięty. Rozważ częściowe zamknięcie lub SL na BE.",
                    })

        except Exception as e:
            events.append({
                "type": "EXIT_ENGINE_POSITION_ERROR",
                "priority": "LOW",
                "position_id": p.get("id"),
                "dedupe_key": f"{p.get('id')}:POSITION_ERROR",
                "message": f"Błąd oceny pozycji: {type(e).__name__}: {e}",
                "time_utc": now_utc(),
            })

    return events


def format_exit_event_alert(e: Dict[str, Any]) -> str:
    priority = e.get("priority", "MEDIUM")
    icon = "🚨" if priority == "HIGH" else "🟡"
    return (
        f"{icon} GOLD EXIT / MANAGEMENT SIGNAL — {e.get('type')}\n\n"
        f"Pozycja #{e.get('position_id')} {e.get('side')}\n"
        f"Entry: {e.get('entry')} | Aktualna cena: {e.get('price')}\n"
        f"SL: {e.get('sl')} | TP1: {e.get('tp1')} | TP2: {e.get('tp2')} | TP3: {e.get('tp3')}\n"
        f"PnL pkt: {e.get('pnl_points')} | RR: {e.get('rr')}\n\n"
        f"Powód: {e.get('message')}\n\n"
        f"To jest sygnał zarządzania pozycją. Bot nie zamyka pozycji u brokera automatycznie."
    )


def should_send_exit_alert(event: Dict[str, Any]) -> bool:
    key = str(event.get("dedupe_key") or f"{event.get('position_id')}:{event.get('type')}")
    now_ts = _utc_ts()
    cooldown = max(60, EXIT_SIGNAL_COOLDOWN_MINUTES * 60)
    last_ts = float(LAST_EXIT_ALERT_KEYS.get(key, 0) or 0)

    if now_ts - last_ts < cooldown:
        return False

    LAST_EXIT_ALERT_KEYS[key] = now_ts

    # Keep memory bounded.
    if len(LAST_EXIT_ALERT_KEYS) > 200:
        oldest = sorted(LAST_EXIT_ALERT_KEYS.items(), key=lambda x: x[1])[:50]
        for old_key, _ in oldest:
            LAST_EXIT_ALERT_KEYS.pop(old_key, None)

    return True


def entry_exit_signal_job() -> None:
    global LAST_SIGNAL, LAST_ENTRY_EXIT_STATUS

    LAST_ENTRY_EXIT_STATUS["last_run_utc"] = now_utc()

    try:
        current_signal = build_signal()
        LAST_SIGNAL = current_signal

        entry_signal = evaluate_entry_signal(current_signal)
        entry_sent = False
        if entry_signal.get("valid") and should_send_entry_alert(entry_signal):
            send_telegram(format_entry_signal_alert(entry_signal))
            entry_sent = True

        exit_events = evaluate_exit_signals(current_signal)
        exit_sent_count = 0
        for event in exit_events:
            if should_send_exit_alert(event):
                send_telegram(format_exit_event_alert(event), chat_id=None)
                exit_sent_count += 1

        LAST_ENTRY_EXIT_STATUS.update({
            "last_success_utc": now_utc(),
            "last_error": None,
            "last_entry_signal": entry_signal,
            "last_entry_sent": entry_sent,
            "last_exit_events_count": len(exit_events),
            "last_exit_sent_count": exit_sent_count,
        })

    except Exception as e:
        LAST_ENTRY_EXIT_STATUS.update({
            "last_error": f"{type(e).__name__}: {e}",
            "last_success_utc": None,
        })
        print(f"ENTRY/EXIT ENGINE ERROR: {type(e).__name__}: {e}")


def command_help() -> str:
    return (
        "Komendy Gold AI Bot v6.5:\n"
        "/position SELL 4097 — dodaj pozycję SELL i automatycznie wylicz SL/TP\n"
        "/position BUY 4097 — dodaj pozycję BUY i automatycznie wylicz SL/TP\n"
        "/positions — pokaż otwarte pozycje\n"
        "/close 1 — usuń pozycję #1 z pamięci bota\n"
        "/setsl 1 4202 — zmień SL pozycji #1\n"
        "/settp 1 3969 3892 3814 — zmień TP1/TP2/TP3 pozycji #1\n"
        "/signal — wygeneruj aktualny sygnał\n"
        "/entry — pokaż aktualny sygnał wejścia BUY/SELL\n"
        "/exit — pokaż sygnały wyjścia/prowadzenia pozycji\n"
        "/signal-now — pełna diagnostyka entry + exit\n"
        "/price — aktualna cena M5 i ATR H1\n"
        "Uwaga: bot nie składa zleceń u brokera. SL/TP trzeba wpisać ręcznie w aplikacji brokera, chyba że podłączysz API brokera."
    )


def handle_command(text: str, chat_id: str) -> str:
    raw = text.strip()
    parts = raw.split()
    if not parts:
        return command_help()
    cmd = parts[0].lower().split("@")[0]

    # Accept plain "SELL 4097" and "BUY 4097" as shortcut.
    if cmd in ("buy", "sell") and len(parts) >= 2:
        side = cmd.upper()
        entry = safe_float(parts[1])
        if entry is None:
            return "Nie rozumiem ceny wejścia. Przykład: SELL 4097"
        p = add_position(side, entry, chat_id=chat_id)
        return "✅ Dodano pozycję do pamięci bota:\n" + format_position(p)

    if cmd in ("/start", "/help"):
        return command_help()

    if cmd == "/position":
        if len(parts) < 3:
            return "Format: /position SELL 4097 albo /position BUY 4097"
        side = parts[1].upper()
        entry = safe_float(parts[2])
        volume = safe_float(parts[3]) if len(parts) >= 4 else None
        if side not in ("BUY", "SELL") or entry is None:
            return "Format: /position SELL 4097 albo /position BUY 4097"
        p = add_position(side, entry, volume, chat_id=chat_id)
        return "✅ Dodano pozycję do pamięci bota:\n" + format_position(p)

    if cmd == "/positions":
        positions = load_positions()
        if not positions:
            return "Brak otwartych pozycji w pamięci bota."
        try:
            price, _ = current_price_and_atr()
        except Exception:
            price = None
        return "📌 Otwarte pozycje:\n\n" + "\n\n".join(format_position(p, price) for p in positions)

    if cmd == "/close":
        if len(parts) < 2 or not parts[1].isdigit():
            return "Format: /close 1"
        ok = close_position(int(parts[1]))
        return "✅ Usunięto pozycję z pamięci bota." if ok else "Nie znaleziono pozycji o takim ID."

    if cmd == "/setsl":
        if len(parts) < 3 or not parts[1].isdigit():
            return "Format: /setsl 1 4202"
        sl = safe_float(parts[2])
        if sl is None:
            return "Nie rozumiem poziomu SL."
        p = update_position(int(parts[1]), sl=round(sl, 2))
        return "✅ Zmieniono SL:\n" + format_position(p) if p else "Nie znaleziono pozycji."

    if cmd == "/settp":
        if len(parts) < 3 or not parts[1].isdigit():
            return "Format: /settp 1 3969 3892 3814"
        updates = {}
        for idx, name in enumerate(["tp1", "tp2", "tp3"], start=2):
            if len(parts) > idx:
                value = safe_float(parts[idx])
                if value is not None:
                    updates[name] = round(value, 2)
        p = update_position(int(parts[1]), **updates)
        return "✅ Zmieniono TP:\n" + format_position(p) if p else "Nie znaleziono pozycji."

    if cmd == "/signal":
        s = build_signal()
        return format_signal(s)

    if cmd == "/entry":
        s = build_signal()
        e = evaluate_entry_signal(s)
        if e.get("valid"):
            return format_entry_signal_alert(e)
        return "Brak aktualnego sygnału wejścia. Status: " + str(e.get("status")) + "\nPowód: " + str(e.get("reason"))

    if cmd == "/exit":
        s = build_signal() if EXIT_ON_OPPOSITE_SIGNAL or EXIT_ON_H1_INVALIDATION else None
        events = evaluate_exit_signals(s)
        if not events:
            return "Brak aktywnych sygnałów wyjścia/prowadzenia pozycji."
        return "📌 Sygnały wyjścia/prowadzenia:\n\n" + "\n\n".join(format_exit_event_alert(e) for e in events[:5])

    if cmd == "/signal-now":
        s = build_signal()
        e = evaluate_entry_signal(s)
        events = evaluate_exit_signals(s)
        return (
            format_signal(s)
            + "\n\n--- ENTRY ENGINE ---\n"
            + (format_entry_signal_alert(e) if e.get("valid") else f"Brak entry. Status: {e.get('status')} | Powód: {e.get('reason')}")
            + "\n\n--- EXIT ENGINE ---\n"
            + ("Brak aktywnych sygnałów exit." if not events else "\n\n".join(format_exit_event_alert(x) for x in events[:5]))
        )

    if cmd == "/price":
        price, atr_value = current_price_and_atr()
        return f"Cena {SYMBOL}: {round(price, 2)}\nATR H1: {round(atr_value, 2)}"

    return "Nieznana komenda.\n\n" + command_help()


def telegram_api_get(method: str, params: Optional[Dict[str, Any]] = None, timeout: int = 12) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    r = requests.get(url, params=params or {}, timeout=timeout)
    TELEGRAM_STATUS["last_http_status"] = r.status_code
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} error: {data}")
    return data


def ensure_telegram_polling_mode() -> None:
    if not TELEGRAM_POLLING_ENABLED or not ENABLE_TELEGRAM or not TELEGRAM_BOT_TOKEN:
        return

    me = telegram_api_get("getMe")
    TELEGRAM_STATUS["bot_username"] = (me.get("result") or {}).get("username")

    webhook = telegram_api_get("getWebhookInfo")
    webhook_url = str((webhook.get("result") or {}).get("url") or "")
    if webhook_url:
        telegram_api_get("deleteWebhook", {"drop_pending_updates": "false"})
        TELEGRAM_STATUS["webhook_deleted"] = True
    TELEGRAM_STATUS["last_error"] = None


def telegram_poll_job() -> None:
    """
    Pobiera update'y z Telegrama.
    Pojedyncza błędna komenda nie blokuje całej kolejki i offset jest przesuwany dalej.
    """
    TELEGRAM_STATUS["last_run_utc"] = now_utc()
    TELEGRAM_STATUS["last_updates_count"] = 0

    if not TELEGRAM_POLLING_ENABLED:
        TELEGRAM_STATUS["last_error"] = "TELEGRAM_POLLING_ENABLED=false"
        return
    if not ENABLE_TELEGRAM:
        TELEGRAM_STATUS["last_error"] = "ENABLE_TELEGRAM=false"
        return
    if not TELEGRAM_BOT_TOKEN:
        TELEGRAM_STATUS["last_error"] = "Brak TELEGRAM_BOT_TOKEN"
        return

    state = load_json(TELEGRAM_OFFSET_FILE, {"offset": None})
    params: Dict[str, Any] = {
        "timeout": 0,
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }
    if state.get("offset") is not None:
        params["offset"] = int(state["offset"])

    command_errors: List[str] = []

    try:
        webhook = telegram_api_get("getWebhookInfo")
        webhook_url = str((webhook.get("result") or {}).get("url") or "")
        if webhook_url:
            telegram_api_get("deleteWebhook", {"drop_pending_updates": "false"})
            TELEGRAM_STATUS["webhook_deleted"] = True

        data = telegram_api_get("getUpdates", params=params, timeout=12)
        updates = data.get("result", [])
        TELEGRAM_STATUS["last_updates_count"] = len(updates)

        max_update_id = None
        for update in updates:
            update_id = update.get("update_id")
            if update_id is not None:
                update_id = int(update_id)
                max_update_id = update_id if max_update_id is None else max(max_update_id, update_id)
                TELEGRAM_STATUS["last_update_id"] = update_id

            message = update.get("message") or update.get("edited_message") or {}
            text_value = message.get("text") or ""
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", ""))

            if not text_value or not chat_id:
                continue

            try:
                response = handle_command(text_value, chat_id)
                send_telegram(response, chat_id=chat_id)
            except Exception as command_error:
                err = f"update_id={update_id}: {type(command_error).__name__}: {command_error}"
                command_errors.append(err)
                try:
                    send_telegram(
                        f"❌ Błąd obsługi komendy: {type(command_error).__name__}: {command_error}",
                        chat_id=chat_id,
                    )
                except Exception:
                    pass
                continue

        if max_update_id is not None:
            save_json(
                TELEGRAM_OFFSET_FILE,
                {"offset": int(max_update_id) + 1, "updated_utc": now_utc()},
            )

        TELEGRAM_STATUS["last_success_utc"] = now_utc()
        TELEGRAM_STATUS["last_error"] = " | ".join(command_errors[-3:]) if command_errors else None

    except Exception as e:
        TELEGRAM_STATUS["last_error"] = f"{type(e).__name__}: {e}"
        print(f"TELEGRAM POLL ERROR: {type(e).__name__}: {e}")


def job() -> None:
    global LAST_SIGNAL, LAST_ALERT_KEY
    try:
        signal = build_signal()
        LAST_SIGNAL = signal
        key = f"{signal['signal']}:{signal['risk_plan']['entry']}:{signal['score']}"
        if signal["signal"] != "NO_TRADE" and key != LAST_ALERT_KEY:
            send_telegram(format_signal(signal))
            LAST_ALERT_KEY = key
    except Exception as e:
        LAST_SIGNAL = {"status": "error", "version": APP_VERSION, "error": str(e), "time_utc": now_utc()}


@app.get("/")
def root():
    return jsonify({"app": "Gold AI Bot v6.5", "version": APP_VERSION, "status": "ok"})


@app.get("/health")
def health():
    scheduler_running = bool(scheduler is not None and getattr(scheduler, "running", False))
    scheduler_jobs = []
    if scheduler_running:
        try:
            scheduler_jobs = [job.id for job in scheduler.get_jobs()]
        except Exception:
            scheduler_jobs = []

    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "scheduler_enabled": SCHEDULER_ENABLED,
        "scheduler_running": scheduler_running,
        "scheduler_jobs": scheduler_jobs,
        "scheduler_env_raw": os.getenv("SCHEDULER_ENABLED"),
        "run_interval_minutes": RUN_INTERVAL_MINUTES,
        "position_check_interval_minutes": POSITION_CHECK_INTERVAL_MINUTES,
        "closed_candles": CLOSED_CANDLES_ONLY,
        "telegram_polling": ENABLE_TELEGRAM and bool(TELEGRAM_BOT_TOKEN),
        "telegram_polling_enabled": TELEGRAM_POLLING_ENABLED,
        "telegram_last_run_utc": TELEGRAM_STATUS.get("last_run_utc"),
        "telegram_last_success_utc": TELEGRAM_STATUS.get("last_success_utc"),
        "telegram_last_error": TELEGRAM_STATUS.get("last_error"),
        "telegram_last_updates_count": TELEGRAM_STATUS.get("last_updates_count"),
        "telegram_bot_username": TELEGRAM_STATUS.get("bot_username"),
        "telegram_webhook_deleted": TELEGRAM_STATUS.get("webhook_deleted"),
        "positions_count": len(load_positions()),
        "move_alert_enabled": MOVE_ALERT_ENABLED,
        "move_alert_intervals": MOVE_ALERT_INTERVALS,
        "cache_enabled": CACHE_ENABLED,
        "cache_items": len(OHLC_CACHE),
        "quota_guard_enabled": QUOTA_GUARD_ENABLED,
        "quota_guard_active": quota_guard_active(),
        "quota_guard_remaining_seconds": quota_guard_remaining_seconds(),
        "api_requests_total": API_RUNTIME.get("requests_total"),
        "api_http_429_count": API_RUNTIME.get("http_429_count"),
        "fast_check_enabled": FAST_CHECK_ENABLED,
        "fast_check_interval_minutes": FAST_CHECK_INTERVAL_MINUTES,
        "move_alert_check_interval_minutes": MOVE_ALERT_CHECK_INTERVAL_MINUTES,
        "cache_cleanup_interval_minutes": CACHE_CLEANUP_INTERVAL_MINUTES,
        "cache_max_rows_per_interval": CACHE_MAX_ROWS_PER_INTERVAL,
    })


@app.get("/telegram-status")
def telegram_status_endpoint():
    result = dict(TELEGRAM_STATUS)
    result.update({
        "enabled": ENABLE_TELEGRAM,
        "polling_enabled": TELEGRAM_POLLING_ENABLED,
        "token_present": bool(TELEGRAM_BOT_TOKEN),
        "configured_chat_id_present": bool(TELEGRAM_CHAT_ID),
        "poll_interval_minutes": TELEGRAM_POLL_INTERVAL_MINUTES,
    })
    if TELEGRAM_BOT_TOKEN:
        try:
            me = telegram_api_get("getMe")
            result["get_me_ok"] = True
            result["bot_username"] = (me.get("result") or {}).get("username")
        except Exception as e:
            result["get_me_ok"] = False
            result["get_me_error"] = f"{type(e).__name__}: {e}"
        try:
            wh = telegram_api_get("getWebhookInfo")
            whr = wh.get("result") or {}
            result["webhook_url"] = whr.get("url") or ""
            result["webhook_pending_update_count"] = whr.get("pending_update_count")
            result["webhook_last_error_message"] = whr.get("last_error_message")
        except Exception as e:
            result["webhook_check_error"] = f"{type(e).__name__}: {e}"
    return jsonify(result)


@app.post("/telegram-poll-now")
def telegram_poll_now_endpoint():
    telegram_poll_job()
    return jsonify(dict(TELEGRAM_STATUS))


@app.get("/cache-status")
def cache_status_endpoint():
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "cache": cache_status_snapshot(),
        "fast_check": fast_check_status_snapshot(),
        "runtime": {
            "fresh_hits": API_RUNTIME.get("cache_hits_fresh"),
            "stale_hits": API_RUNTIME.get("cache_hits_stale"),
            "misses": API_RUNTIME.get("cache_misses"),
        },
    })


@app.get("/fast-check-status")
def fast_check_status_endpoint():
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "fast_check": fast_check_status_snapshot(),
        "cache": cache_status_snapshot(),
        "api_runtime": api_runtime_snapshot(),
        "positions_count": len(load_positions()),
    })


@app.get("/quota-status")
def quota_status_endpoint():
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "api_runtime": api_runtime_snapshot(),
    })


@app.post("/quota-reset")
def quota_reset_endpoint():
    API_RUNTIME["blocked_until_ts"] = 0.0
    API_RUNTIME["consecutive_429"] = 0
    API_RUNTIME["last_error"] = None
    return jsonify({"status": "ok", "message": "Local Quota Guard reset", "version": APP_VERSION})


@app.get("/tick")
def tick_endpoint():
    """
    Runtime market-data diagnostic.
    Default: smart fetch through cache + Quota Guard.
    Optional query params:
      ?interval=1h
      ?outputsize=20
      ?force=1   -> wymusza próbę odświeżenia z API (używać ostrożnie)
    """
    interval = str(request.args.get("interval", "1h")).strip()
    allowed_intervals = {"5min", "15min", "1h", "4h", "1day"}
    if interval not in allowed_intervals:
        return jsonify({
            "status": "error",
            "version": APP_VERSION,
            "message": f"Unsupported interval: {interval}",
            "allowed_intervals": sorted(allowed_intervals),
        }), 400

    try:
        outputsize = int(request.args.get("outputsize", "20"))
    except Exception:
        outputsize = 20
    outputsize = max(5, min(outputsize, 5000))

    force_raw = str(request.args.get("force", "0")).strip().lower()
    force_refresh = force_raw in {"1", "true", "yes", "on"}

    before = {
        "requests_success": int(API_RUNTIME.get("requests_success", 0) or 0),
        "cache_hits_fresh": int(API_RUNTIME.get("cache_hits_fresh", 0) or 0),
        "cache_hits_stale": int(API_RUNTIME.get("cache_hits_stale", 0) or 0),
    }

    result = {
        "status": "ok",
        "version": APP_VERSION,
        "symbol": SYMBOL,
        "interval": interval,
        "outputsize": outputsize,
        "force_refresh": force_refresh,
        "key_present": bool(TWELVE_DATA_API_KEY),
        "fetch_ok": False,
        "time_utc": now_utc(),
    }

    try:
        df = fetch_ohlc(interval, outputsize=outputsize, force_refresh=force_refresh)
        if df is None or df.empty:
            raise RuntimeError("No OHLC rows returned")

        after = {
            "requests_success": int(API_RUNTIME.get("requests_success", 0) or 0),
            "cache_hits_fresh": int(API_RUNTIME.get("cache_hits_fresh", 0) or 0),
            "cache_hits_stale": int(API_RUNTIME.get("cache_hits_stale", 0) or 0),
        }

        if after["requests_success"] > before["requests_success"]:
            data_source = "api"
        elif after["cache_hits_fresh"] > before["cache_hits_fresh"]:
            data_source = "cache_fresh"
        elif after["cache_hits_stale"] > before["cache_hits_stale"]:
            data_source = "cache_stale"
        else:
            data_source = "cache_or_api"

        last = df.iloc[-1]
        result.update({
            "fetch_ok": True,
            "data_source": data_source,
            "rows": int(len(df)),
            "last_candle": {
                "datetime": str(last.get("datetime")),
                "open": safe_float(last.get("open")),
                "high": safe_float(last.get("high")),
                "low": safe_float(last.get("low")),
                "close": safe_float(last.get("close")),
            },
            "quota_guard": api_runtime_snapshot(),
            "cache_interval": cache_status_snapshot().get(interval),
        })
        return jsonify(result)

    except Exception as e:
        result.update({
            "status": "error",
            "fetch_ok": False,
            "error": f"{type(e).__name__}: {e}",
            "quota_guard": api_runtime_snapshot(),
            "cache_interval": cache_status_snapshot().get(interval),
        })
        # Diagnostic endpoint deliberately returns JSON body even on provider failure.
        return jsonify(result), 200


@app.get("/entry-status")
def entry_status_endpoint():
    try:
        s = build_signal()
        e = evaluate_entry_signal(s)
        return jsonify({
            "status": "ok",
            "version": APP_VERSION,
            "entry": e,
            "signal": {
                "signal": s.get("signal"),
                "score": s.get("score"),
                "price": s.get("price"),
                "trend": s.get("trend"),
            },
            "api_runtime": api_runtime_snapshot(),
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "version": APP_VERSION,
            "error": f"{type(e).__name__}: {e}",
            "api_runtime": api_runtime_snapshot(),
        }), 200


@app.get("/exit-status")
def exit_status_endpoint():
    try:
        s = build_signal() if EXIT_ON_OPPOSITE_SIGNAL or EXIT_ON_H1_INVALIDATION else None
        events = evaluate_exit_signals(s)
        return jsonify({
            "status": "ok",
            "version": APP_VERSION,
            "positions_count": len(load_positions()),
            "events_count": len(events),
            "events": events,
            "signal": {
                "signal": s.get("signal") if s else None,
                "score": s.get("score") if s else None,
                "price": s.get("price") if s else None,
                "trend": s.get("trend") if s else None,
            },
            "api_runtime": api_runtime_snapshot(),
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "version": APP_VERSION,
            "error": f"{type(e).__name__}: {e}",
            "api_runtime": api_runtime_snapshot(),
        }), 200


@app.get("/signal-now")
def signal_now_endpoint():
    try:
        s = build_signal()
        e = evaluate_entry_signal(s)
        events = evaluate_exit_signals(s)
        return jsonify({
            "status": "ok",
            "version": APP_VERSION,
            "signal": s,
            "entry": e,
            "exit_events": events,
            "api_runtime": api_runtime_snapshot(),
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "version": APP_VERSION,
            "error": f"{type(e).__name__}: {e}",
            "api_runtime": api_runtime_snapshot(),
        }), 200


@app.post("/entry-exit-run-now")
def entry_exit_run_now_endpoint():
    entry_exit_signal_job()
    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "entry_exit_status": LAST_ENTRY_EXIT_STATUS,
    })


@app.get("/signal")
def signal_endpoint():
    job()
    return jsonify(LAST_SIGNAL)


@app.get("/last")
def last_endpoint():
    return jsonify(LAST_SIGNAL)


@app.get("/positions")
def positions_endpoint():
    return jsonify({"positions": load_positions(), "count": len(load_positions()), "version": APP_VERSION})


@app.post("/positions")
def add_position_endpoint():
    data = request.get_json(force=True, silent=True) or {}
    side = str(data.get("side", "")).upper()
    entry = safe_float(data.get("entry"))
    volume = safe_float(data.get("volume"))
    if side not in ("BUY", "SELL") or entry is None:
        return jsonify({"status": "error", "message": "Use JSON: {'side':'SELL','entry':4097}"}), 400
    p = add_position(side, entry, volume)
    return jsonify({"status": "ok", "position": p})


@app.post("/telegram/webhook")
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text") or ""
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if text and chat_id:
        send_telegram(handle_command(text, chat_id), chat_id=chat_id)
    return jsonify({"ok": True})


@app.get("/move-alert-test")
def move_alert_test():
    results = []
    for interval in MOVE_ALERT_INTERVALS:
        try:
            results.append({"interval": interval, "move": detect_big_move(interval)})
        except Exception as e:
            results.append({"interval": interval, "error": str(e)})
    return jsonify({"results": results})


# Restore persistent cache before scheduler starts.
load_ohlc_cache()
cleanup_cache_job()


if SCHEDULER_ENABLED:
    scheduler = BackgroundScheduler(daemon=True)

    # Pełna analiza sygnału. Domyślnie nadal co RUN_INTERVAL_MINUTES,
    # bo MTF cache ogranicza realne requesty API.
    scheduler.add_job(
        job,
        "interval",
        minutes=max(1, RUN_INTERVAL_MINUTES),
        id="gold_ai_bot_v6_5_signal",
        replace_existing=True,
    )

    # Monitor pozycji może działać co 1 minutę; przy 0 pozycjach robi 0 requestów.
    scheduler.add_job(
        position_monitor_job,
        "interval",
        minutes=max(1, FAST_CHECK_INTERVAL_MINUTES if FAST_CHECK_ENABLED else POSITION_CHECK_INTERVAL_MINUTES),
        id="position_monitor",
        replace_existing=True,
    )

    # Move Alert Engine co 1 minutę; dane pochodzą z cache, więc API nie jest odpytywane co minutę.
    scheduler.add_job(
        check_move_alerts,
        "interval",
        minutes=max(1, MOVE_ALERT_CHECK_INTERVAL_MINUTES),
        id="move_alerts",
        replace_existing=True,
    )

    # Telegram polling co najmniej raz na minutę.
    scheduler.add_job(
        telegram_poll_job,
        "interval",
        minutes=max(1, TELEGRAM_POLL_INTERVAL_MINUTES),
        id="telegram_poll",
        replace_existing=True,
    )

    # Entry / Exit Signal Engine.
    scheduler.add_job(
        entry_exit_signal_job,
        "interval",
        minutes=max(1, ENTRY_SIGNAL_CHECK_INTERVAL_MINUTES),
        id="entry_exit_signal_engine",
        replace_existing=True,
    )

    # Czyszczenie cache bez zapytań do API.
    scheduler.add_job(
        cleanup_cache_job,
        "interval",
        minutes=max(5, CACHE_CLEANUP_INTERVAL_MINUTES),
        id="cache_cleanup",
        replace_existing=True,
    )

    scheduler.start()
    try:
        ensure_telegram_polling_mode()
        telegram_poll_job()
    except Exception as e:
        TELEGRAM_STATUS["last_error"] = f"startup: {type(e).__name__}: {e}"
        print(f"TELEGRAM STARTUP ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
