import os
import threading
import time
from typing import Dict, Tuple

import pandas as pd
import requests

from config import env_bool, env_int

BASE_URL = "https://api.twelvedata.com/time_series"
_CACHE: Dict[Tuple[str, str, int, bool], Tuple[float, pd.DataFrame]] = {}
_CACHE_LOCK = threading.Lock()


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip() or "XAU/USD"


def _drop_incomplete(df: pd.DataFrame) -> pd.DataFrame:
    # Twelve Data often returns the currently forming candle as the newest row.
    # For signal generation we deliberately use only closed candles.
    if env_bool("USE_CLOSED_CANDLES", True) and len(df) > 1:
        return df.iloc[:-1].reset_index(drop=True)
    return df


def fetch_ohlc(symbol: str, interval: str, outputsize: int = 220, *, closed_only: bool = True) -> pd.DataFrame:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("Brak TWELVEDATA_API_KEY w zmiennych środowiskowych")

    symbol = _normalize_symbol(symbol)
    outputsize = max(10, min(int(outputsize), 5000))
    cache_ttl = env_int("API_CACHE_SECONDS", 45)
    key = (symbol, interval, outputsize, closed_only)

    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] <= cache_ttl:
            return cached[1].copy()

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
        "timezone": os.getenv("TIMEZONE", "Europe/Warsaw"),
    }
    response = requests.get(BASE_URL, params=params, timeout=25)
    response.raise_for_status()
    data = response.json()
    if "values" not in data:
        raise RuntimeError(f"Błąd API TwelveData dla {symbol} {interval}: {data}")

    df = pd.DataFrame(data["values"])
    parsed_dt = pd.to_datetime(df["datetime"], errors="coerce")
    # Twelve Data returns datetimes in the requested timezone, often without an offset.
    # Normalize all timestamps to UTC so outcome tracking remains correct across DST.
    requested_tz = os.getenv("TIMEZONE", "Europe/Warsaw")
    try:
        if parsed_dt.dt.tz is None:
            parsed_dt = parsed_dt.dt.tz_localize(requested_tz, ambiguous="NaT", nonexistent="shift_forward")
        else:
            parsed_dt = parsed_dt.dt.tz_convert(requested_tz)
        parsed_dt = parsed_dt.dt.tz_convert("UTC")
    except (TypeError, ValueError):
        # Defensive fallback: keep parsed timestamps; downstream code still validates rows.
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
    if closed_only:
        df = _drop_incomplete(df)
    if df.empty:
        raise RuntimeError(f"Brak poprawnych danych dla {symbol} {interval}")

    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), df.copy())
    return df


def fetch_last_price(symbol: str) -> float:
    df = fetch_ohlc(symbol, "1min", 5, closed_only=False)
    return float(df["close"].iloc[-1])
