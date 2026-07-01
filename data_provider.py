import os
import requests
import pandas as pd

BASE_URL = "https://api.twelvedata.com/time_series"

def _normalize_symbol(symbol: str) -> str:
    return symbol.strip() or "XAU/USD"

def fetch_ohlc(symbol: str, interval: str, outputsize: int = 220) -> pd.DataFrame:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("Brak TWELVEDATA_API_KEY w zmiennych środowiskowych")
    params = {
        "symbol": _normalize_symbol(symbol),
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
        "timezone": os.getenv("TIMEZONE", "Europe/Warsaw"),
    }
    r = requests.get(BASE_URL, params=params, timeout=20)
    data = r.json()
    if "values" not in data:
        raise RuntimeError(f"Błąd API TwelveData dla {symbol} {interval}: {data}")
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)
    return df

def fetch_last_price(symbol: str) -> float:
    df = fetch_ohlc(symbol, "1min", 5)
    return float(df["close"].iloc[-1])
