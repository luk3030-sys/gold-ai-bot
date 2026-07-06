import os
import threading
import time
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import env_bool, env_int

BASE_URL = "https://api.twelvedata.com/time_series"
_CACHE: Dict[Tuple[str, str, int, bool], Tuple[float, pd.DataFrame]] = {}
_CACHE_LOCK = threading.Lock()
_NEGATIVE_CACHE: Dict[str, float] = {}
_NEGATIVE_LOCK = threading.Lock()


def _http_session() -> requests.Session:
    retry = Retry(
        total=env_int("HTTP_RETRIES", 3),
        connect=env_int("HTTP_RETRIES", 3),
        read=env_int("HTTP_RETRIES", 3),
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "Gold-AI-Bot/5.1"})
    return session


_SESSION = _http_session()


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip() or "XAU/USD"


def _drop_incomplete(df: pd.DataFrame) -> pd.DataFrame:
    # Twelve Data usually returns the currently forming candle as the newest row.
    if env_bool("USE_CLOSED_CANDLES", True) and len(df) > 1:
        return df.iloc[:-1].reset_index(drop=True)
    return df


def _cache_get(key, max_age: int) -> Optional[pd.DataFrame]:
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] <= max_age:
            return cached[1].copy()
    return None


def _cache_put(key, df: pd.DataFrame) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), df.copy())


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


def fetch_ohlc(symbol: str, interval: str, outputsize: int = 220, *, closed_only: bool = True) -> pd.DataFrame:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("Brak TWELVEDATA_API_KEY w zmiennych środowiskowych")

    symbol = _normalize_symbol(symbol)
    outputsize = max(10, min(int(outputsize), 5000))
    cache_ttl = env_int("API_CACHE_SECONDS", 45)
    stale_ttl = env_int("API_STALE_CACHE_SECONDS", 900)
    key = (symbol, interval, outputsize, closed_only)

    fresh = _cache_get(key, cache_ttl)
    if fresh is not None:
        fresh.attrs["data_source"] = "cache_fresh"
        return fresh

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
        response.raise_for_status()
        df = _parse_response(response.json(), symbol, interval)
        if closed_only:
            df = _drop_incomplete(df)
        if df.empty:
            raise RuntimeError(f"Brak poprawnych danych po filtracji dla {symbol} {interval}")
        df.attrs["data_source"] = "live_api"
        _cache_put(key, df)
        return df.copy()
    except Exception:
        if env_bool("USE_STALE_CACHE_ON_ERROR", True):
            stale = _cache_get(key, stale_ttl)
            if stale is not None:
                stale.attrs["data_source"] = "cache_stale"
                stale.attrs["stale"] = True
                return stale
        raise


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
    ttl = env_int("DXY_FAILURE_CACHE_SECONDS", 900)
    with _NEGATIVE_LOCK:
        failed_at = _NEGATIVE_CACHE.get(symbol)
        return failed_at is not None and time.time() - failed_at < ttl


def _mark_negative(symbol: str) -> None:
    with _NEGATIVE_LOCK:
        _NEGATIVE_CACHE[symbol] = time.time()


def fetch_dxy_context(interval: str = "1h", outputsize: int = 220) -> dict:
    """Fetch direct DXY if available, otherwise an explicitly configured proxy.

    DXY_SYMBOLS is a comma-separated direct-symbol candidate list. DXY_PROXY_SYMBOL
    is optional and is never silently treated as the real index.
    """
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
            return {"available": True, "status": "DIRECT", "kind": "direct", "symbol": symbol, "df": df}
        except Exception as exc:
            _mark_negative(symbol)
            errors.append(f"{symbol}:{type(exc).__name__}")

    proxy = os.getenv("DXY_PROXY_SYMBOL", "").strip()
    if proxy:
        try:
            df = fetch_ohlc(proxy, interval, outputsize, closed_only=True)
            return {"available": True, "status": "PROXY", "kind": "proxy", "symbol": proxy, "df": df, "errors": errors}
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
