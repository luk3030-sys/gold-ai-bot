import os
import requests


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def fetch_twelvedata(symbol: str, interval: str, outputsize: int = 120):
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("Brak TWELVEDATA_API_KEY w Environment Variables")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "format": "JSON",
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()

    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(f"TwelveData error for {symbol} {interval}: {payload}")

    candles = []
    for item in reversed(payload["values"]):
        candles.append({
            "datetime": item.get("datetime"),
            "open": _to_float(item.get("open")),
            "high": _to_float(item.get("high")),
            "low": _to_float(item.get("low")),
            "close": _to_float(item.get("close")),
        })
    return candles


def get_multi_timeframe_data(symbol: str):
    return {
        "H1": fetch_twelvedata(symbol, "1h", 150),
        "H4": fetch_twelvedata(symbol, "4h", 150),
        "D1": fetch_twelvedata(symbol, "1day", 150),
    }
