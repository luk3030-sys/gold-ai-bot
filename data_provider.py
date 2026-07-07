from __future__ import annotations

import hashlib
import io
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import env_bool, env_int
from db import find_market_cache, get_market_cache, market_cache_rows, put_market_cache
from quota_guard import (
    QuotaGuardBlocked,
    RateLimitError,
    check_request,
    on_429,
    on_success,
    quota_status,
    record_request,
)

BASE_URL = "https://api.twelvedata.com/time_series"
_CACHE: Dict[str, Tuple[float, str | None, pd.DataFrame]] = {}
_CACHE_LOCK = threading.Lock()
_NEGATIVE_CACHE: Dict[str, float] = {}
_NEGATIVE_LOCK = threading.Lock()


class ProviderDataUnavailable(RuntimeError):
    """Raised when no safe live or cached data can be supplied."""


def _http_session() -> requests.Session:
    # Important: HTTP 429 is intentionally NOT retried automatically. Retrying 429
    # can multiply quota pressure and prolong rate-limit lockouts.
    retries = max(0, env_int("HTTP_RETRIES", 2))
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=0.7,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "Gold-AI-Bot/6.3.2"})
    return session


_SESSION = _http_session()


_INTERVAL_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "45min": 2700,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "1day": 86400,
    "1week": 604800,
}


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip() or "XAU/USD"


def _drop_incomplete(df: pd.DataFrame) -> pd.DataFrame:
    # Twelve Data usually returns the currently forming candle as the newest row.
    if env_bool("USE_CLOSED_CANDLES", True) and len(df) > 1:
        return df.iloc[:-1].reset_index(drop=True)
    return df


def _cache_key(symbol: str, interval: str, outputsize: int, closed_only: bool) -> str:
    raw = f"{symbol}|{interval}|{int(outputsize)}|{1 if closed_only else 0}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _interval_seconds(interval: str) -> int:
    return _INTERVAL_SECONDS.get(interval, max(60, env_int("UNKNOWN_INTERVAL_SECONDS", 900)))


def _closed_bucket_id(interval: str) -> str:
    seconds = _interval_seconds(interval)
    grace = max(0, env_int("CANDLE_CLOSE_GRACE_SECONDS", 75))
    now = int(time.time()) - grace
    bucket = now // seconds
    return f"closed:{interval}:{bucket}"


def _live_bucket_id(interval: str) -> str:
    ttl = max(30, env_int("LIVE_CACHE_SECONDS", 300))
    return f"live:{interval}:{int(time.time()) // ttl}"


def _bucket_id(interval: str, closed_only: bool) -> str:
    return _closed_bucket_id(interval) if closed_only else _live_bucket_id(interval)


def _stale_ttl(interval: str, closed_only: bool) -> int:
    if not closed_only:
        return max(300, env_int("LIVE_STALE_CACHE_SECONDS", 1800))
    seconds = _interval_seconds(interval)
    # Keep enough history to survive short provider outages without treating old
    # data as fresh. Signal generation can inspect attrs['stale_age_seconds'].
    return max(seconds * 4, env_int("API_STALE_CACHE_SECONDS", 21600))


def _memory_get(key: str) -> Optional[Tuple[float, str | None, pd.DataFrame]]:
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item:
            return item[0], item[1], item[2].copy()
    return None


def _memory_put(key: str, fetched_ts: float, bucket_id: str | None, df: pd.DataFrame) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (fetched_ts, bucket_id, df.copy())


def _df_to_json(df: pd.DataFrame) -> str:
    work = df.copy()
    work["datetime"] = pd.to_datetime(work["datetime"], utc=True, errors="coerce").astype(str)
    return work.to_json(orient="records")


def _df_from_json(payload: str) -> pd.DataFrame:
    records = json.loads(payload)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return (
        df.dropna(subset=["datetime", "open", "high", "low", "close"])
        .sort_values("datetime")
        .drop_duplicates(subset=["datetime"], keep="last")
        .reset_index(drop=True)
    )


def _parse_iso_ts(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _persistent_get(
    symbol: str,
    interval: str,
    outputsize: int,
    closed_only: bool,
) -> Optional[Tuple[str, float, str | None, pd.DataFrame, dict]]:
    key = _cache_key(symbol, interval, outputsize, closed_only)
    row = get_market_cache(key)
    if row is None:
        # Reuse a larger cached frame, e.g. tracker 500 bars can serve strategy 320.
        row = find_market_cache(symbol, interval, closed_only, outputsize)
    if not row:
        return None
    try:
        df = _df_from_json(row["payload_json"])
        if len(df) > outputsize:
            df = df.tail(outputsize).reset_index(drop=True)
        meta = json.loads(row.get("meta_json") or "{}")
        return row["cache_key"], _parse_iso_ts(row.get("fetched_at")), row.get("bucket_id"), df, meta
    except Exception:
        return None


def _persistent_put(
    key: str,
    *,
    symbol: str,
    interval: str,
    outputsize: int,
    closed_only: bool,
    bucket_id: str,
    df: pd.DataFrame,
    meta: dict,
) -> None:
    fetched_at = datetime.now(timezone.utc).isoformat()
    put_market_cache(
        key,
        symbol=symbol,
        interval=interval,
        closed_only=closed_only,
        outputsize=outputsize,
        fetched_at=fetched_at,
        bucket_id=bucket_id,
        payload_json=_df_to_json(df),
        meta=meta,
    )


def _decorate(df: pd.DataFrame, *, source: str, fetched_ts: float, stale: bool = False, reason: str = "") -> pd.DataFrame:
    out = df.copy()
    age = max(0, int(time.time() - fetched_ts)) if fetched_ts else None
    out.attrs["data_source"] = source
    out.attrs["stale"] = bool(stale)
    out.attrs["stale_age_seconds"] = age
    if reason:
        out.attrs["fallback_reason"] = reason
    return out


def _cached_frame(
    symbol: str,
    interval: str,
    outputsize: int,
    closed_only: bool,
    *,
    require_current_bucket: bool,
) -> Optional[pd.DataFrame]:
    key = _cache_key(symbol, interval, outputsize, closed_only)
    current_bucket = _bucket_id(interval, closed_only)

    mem = _memory_get(key)
    if mem:
        fetched_ts, bucket, df = mem
        if (not require_current_bucket) or bucket == current_bucket:
            return _decorate(df, source="cache_memory", fetched_ts=fetched_ts, stale=bucket != current_bucket)

    persisted = _persistent_get(symbol, interval, outputsize, closed_only)
    if persisted:
        persisted_key, fetched_ts, bucket, df, _meta = persisted
        _memory_put(key, fetched_ts, bucket, df)
        if (not require_current_bucket) or bucket == current_bucket:
            return _decorate(df, source="cache_postgresql", fetched_ts=fetched_ts, stale=bucket != current_bucket)
    return None


def _stale_frame(symbol: str, interval: str, outputsize: int, closed_only: bool, reason: str) -> Optional[pd.DataFrame]:
    key = _cache_key(symbol, interval, outputsize, closed_only)
    candidates = []
    mem = _memory_get(key)
    if mem:
        candidates.append((mem[0], mem[2], "cache_memory_stale"))
    persisted = _persistent_get(symbol, interval, outputsize, closed_only)
    if persisted:
        _pkey, fetched_ts, _bucket, df, _meta = persisted
        candidates.append((fetched_ts, df, "cache_postgresql_stale"))
    if not candidates:
        return None
    fetched_ts, df, source = max(candidates, key=lambda item: item[0])
    age = time.time() - fetched_ts
    if age > _stale_ttl(interval, closed_only):
        return None
    return _decorate(df, source=source, fetched_ts=fetched_ts, stale=True, reason=reason)


def _parse_response(data: dict, symbol: str, interval: str) -> pd.DataFrame:
    if "values" not in data:
        message = data.get("message") or data.get("status") or str(data)
        raise RuntimeError(f"Błąd API TwelveData dla {symbol} {interval}: {message}")

    df = pd.DataFrame(data["values"])
    parsed_dt = pd.to_datetime(df["datetime"], errors="coerce")
    requested_tz = os.getenv("TIMEZONE", "Europe/Warsaw")
    try:
        if parsed_dt.dt.tz is None:
            parsed_dt = parsed_dt.dt.tz_localize(requested_tz, ambiguous="NaT", nonexistent="shift_forward")
        else:
            parsed_dt = parsed_dt.dt.tz_convert(requested_tz)
        parsed_dt = parsed_dt.dt.tz_convert("UTC")
    except (TypeError, ValueError):
        pass

    df["datetime"] = parsed_dt
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    df = (
        df.dropna(subset=["datetime", "open", "high", "low", "close"])
        .sort_values("datetime")
        .drop_duplicates(subset=["datetime"], keep="last")
        .reset_index(drop=True)
    )
    if df.empty:
        raise RuntimeError(f"Brak poprawnych danych dla {symbol} {interval}")
    return df


def fetch_ohlc(
    symbol: str,
    interval: str,
    outputsize: int = 220,
    *,
    closed_only: bool = True,
    force_refresh: bool = False,
) -> pd.DataFrame:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("Brak TWELVEDATA_API_KEY w zmiennych środowiskowych")

    symbol = _normalize_symbol(symbol)
    outputsize = max(10, min(int(outputsize), 5000))
    current_bucket = _bucket_id(interval, closed_only)
    key = _cache_key(symbol, interval, outputsize, closed_only)

    # Smart MTF cache: closed M15/H1/H4/D1 data is fetched only when a new
    # closed-candle bucket should exist. This works even if cron runs every 10 min.
    if not force_refresh:
        current = _cached_frame(symbol, interval, outputsize, closed_only, require_current_bucket=True)
        if current is not None:
            current.attrs["smart_cache_hit"] = True
            return current

    quota_enabled = env_bool("QUOTA_GUARD_ENABLED", True)
    if quota_enabled:
        decision = check_request(1)
        if not decision.allowed:
            stale = _stale_frame(symbol, interval, outputsize, closed_only, decision.reason)
            if stale is not None:
                stale.attrs["quota_guard_blocked"] = True
                stale.attrs["quota_guard_reason"] = decision.reason
                return stale
            raise QuotaGuardBlocked(
                f"Twelve Data request blocked: {decision.reason}; "
                f"minute={decision.minute_used}/{decision.minute_limit}, daily={decision.daily_used}/{decision.daily_limit}"
            )

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
        "timezone": os.getenv("TIMEZONE", "Europe/Warsaw"),
    }

    try:
        response = _SESSION.get(BASE_URL, params=params, timeout=env_int("HTTP_TIMEOUT_SECONDS", 25))
        status = int(response.status_code)
        if status == 429:
            record_request(endpoint="time_series", symbol=symbol, interval=interval, status="http_429", detail=response.text)
            breaker = on_429(response.text)
            stale = _stale_frame(symbol, interval, outputsize, closed_only, "http_429")
            if stale is not None:
                stale.attrs["rate_limited"] = True
                stale.attrs["circuit_breaker"] = breaker
                return stale
            raise RateLimitError(f"429 Too Many Requests; circuit blocked until {breaker['blocked_until']}")

        response.raise_for_status()
        record_request(endpoint="time_series", symbol=symbol, interval=interval, status="success", detail=f"http_{status}")
        on_success()
        df = _parse_response(response.json(), symbol, interval)
        if closed_only:
            df = _drop_incomplete(df)
        if df.empty:
            raise RuntimeError(f"Brak poprawnych danych po filtracji dla {symbol} {interval}")

        fetched_ts = time.time()
        meta = {"http_status": status, "provider": "twelvedata", "version": "6.3.2"}
        _memory_put(key, fetched_ts, current_bucket, df)
        try:
            _persistent_put(
                key,
                symbol=symbol,
                interval=interval,
                outputsize=outputsize,
                closed_only=closed_only,
                bucket_id=current_bucket,
                df=df,
                meta=meta,
            )
        except Exception:
            # Persistent cache is a resilience layer; live market data must not fail
            # solely because cache persistence had a transient DB issue.
            pass
        return _decorate(df, source="live_api", fetched_ts=fetched_ts)

    except (QuotaGuardBlocked, RateLimitError):
        raise
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        record_request(
            endpoint="time_series",
            symbol=symbol,
            interval=interval,
            status=f"http_{status or 'error'}",
            detail=str(exc),
        )
        stale = _stale_frame(symbol, interval, outputsize, closed_only, f"http_{status or 'error'}")
        if stale is not None and env_bool("USE_STALE_CACHE_ON_ERROR", True):
            return stale
        raise ProviderDataUnavailable(str(exc)) from exc
    except Exception as exc:
        record_request(endpoint="time_series", symbol=symbol, interval=interval, status="error", detail=str(exc))
        stale = _stale_frame(symbol, interval, outputsize, closed_only, type(exc).__name__)
        if stale is not None and env_bool("USE_STALE_CACHE_ON_ERROR", True):
            return stale
        raise ProviderDataUnavailable(f"{type(exc).__name__}: {exc}") from exc


def fetch_last_price(symbol: str) -> float:
    df = fetch_ohlc(symbol, "1min", 5, closed_only=False)
    return float(df["close"].iloc[-1])


def _candidate_list(value: str) -> Iterable[str]:
    seen = set()
    for item in value.split(","):
        symbol = item.strip()
        if symbol and symbol not in seen:
            seen.add(symbol)
            yield symbol


def _negative_cached(symbol: str) -> bool:
    ttl = env_int("DXY_FAILURE_CACHE_SECONDS", 21600)
    with _NEGATIVE_LOCK:
        failed_at = _NEGATIVE_CACHE.get(symbol)
        return failed_at is not None and time.time() - failed_at < ttl


def _mark_negative(symbol: str) -> None:
    with _NEGATIVE_LOCK:
        _NEGATIVE_CACHE[symbol] = time.time()


def fetch_dxy_context(interval: str = "1h", outputsize: int = 220) -> dict:
    if not env_bool("DXY_ENABLED", True):
        return {"available": False, "status": "DISABLED", "kind": "disabled"}

    candidates = list(_candidate_list(os.getenv("DXY_SYMBOLS", os.getenv("DXY_SYMBOL", "DXY,DX"))))
    errors = []
    for symbol in candidates:
        if _negative_cached(symbol):
            errors.append(f"{symbol}:negative_cache")
            continue
        try:
            df = fetch_ohlc(symbol, interval, outputsize, closed_only=True)
            return {
                "available": True,
                "status": "DIRECT",
                "kind": "direct",
                "symbol": symbol,
                "df": df,
                "data_source": df.attrs.get("data_source"),
                "stale": bool(df.attrs.get("stale", False)),
            }
        except (RateLimitError, QuotaGuardBlocked) as exc:
            errors.append(f"{symbol}:{type(exc).__name__}")
            # Do not mark a symbol invalid just because the whole provider is rate-limited.
            break
        except Exception as exc:
            _mark_negative(symbol)
            errors.append(f"{symbol}:{type(exc).__name__}")

    proxy = os.getenv("DXY_PROXY_SYMBOL", "").strip()
    if proxy:
        try:
            df = fetch_ohlc(proxy, interval, outputsize, closed_only=True)
            return {
                "available": True,
                "status": "PROXY",
                "kind": "proxy",
                "symbol": proxy,
                "df": df,
                "errors": errors,
                "data_source": df.attrs.get("data_source"),
                "stale": bool(df.attrs.get("stale", False)),
            }
        except Exception as exc:
            errors.append(f"{proxy}:{type(exc).__name__}")

    return {"available": False, "status": "UNAVAILABLE", "kind": "none", "errors": errors[-5:]}


def provider_health(symbol: Optional[str] = None) -> dict:
    symbol = symbol or os.getenv("SYMBOL", "XAU/USD")
    started = time.time()
    try:
        price = fetch_last_price(symbol)
        return {
            "ok": True,
            "symbol": symbol,
            "price": round(price, 4),
            "latency_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "symbol": symbol,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": int((time.time() - started) * 1000),
        }


def market_cache_status(limit: int = 100) -> dict:
    rows = market_cache_rows(limit)
    now = time.time()
    normalized = []
    for row in rows:
        fetched_ts = _parse_iso_ts(row.get("fetched_at"))
        normalized.append({
            "symbol": row.get("symbol"),
            "interval": row.get("interval"),
            "closed_only": bool(row.get("closed_only")),
            "outputsize": int(row.get("outputsize") or 0),
            "fetched_at": row.get("fetched_at"),
            "age_seconds": max(0, int(now - fetched_ts)) if fetched_ts else None,
            "bucket_id": row.get("bucket_id"),
        })
    return {
        "entries": normalized,
        "count": len(normalized),
        "smart_cache": True,
        "quota": quota_status(),
    }
