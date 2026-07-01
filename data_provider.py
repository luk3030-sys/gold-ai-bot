import os
import requests

BASE_URL = 'https://api.twelvedata.com/time_series'


def _parse_values(payload):
    if 'values' not in payload:
        raise RuntimeError(payload.get('message') or str(payload))
    values = list(reversed(payload['values']))
    candles = []
    for row in values:
        candles.append({
            'datetime': row.get('datetime'),
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
        })
    return candles


def fetch_candles(symbol=None, interval='1h', outputsize=200):
    api_key = os.getenv('TWELVEDATA_API_KEY')
    if not api_key:
        raise RuntimeError('Brak TWELVEDATA_API_KEY w Render Environment')
    symbol = symbol or os.getenv('SYMBOL', 'XAU/USD')
    params = {
        'symbol': symbol,
        'interval': interval,
        'outputsize': outputsize,
        'apikey': api_key,
    }
    r = requests.get(BASE_URL, params=params, timeout=20)
    r.raise_for_status()
    return _parse_values(r.json())


def fetch_market_snapshot(symbol=None):
    symbol = symbol or os.getenv('SYMBOL', 'XAU/USD')
    return {
        'symbol': symbol,
        'h1': fetch_candles(symbol, '1h', 220),
        'h4': fetch_candles(symbol, '4h', 220),
        'd1': fetch_candles(symbol, '1day', 220),
    }
