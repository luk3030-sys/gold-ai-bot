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
            'volume': float(row.get('volume') or 0),
        })
    return candles


def fetch_candles(symbol=None, interval='1h', outputsize=250):
    api_key = os.getenv('TWELVEDATA_API_KEY')
    if not api_key:
        raise RuntimeError('Brak TWELVEDATA_API_KEY w Render Environment')
    symbol = symbol or os.getenv('SYMBOL', 'XAU/USD')
    params = {'symbol': symbol, 'interval': interval, 'outputsize': outputsize, 'apikey': api_key}
    r = requests.get(BASE_URL, params=params, timeout=25)
    r.raise_for_status()
    return _parse_values(r.json())


def _safe_fetch(symbol, interval, outputsize):
    try:
        return fetch_candles(symbol, interval, outputsize)
    except Exception as e:
        return {'error': str(e), 'symbol': symbol}


def fetch_market_snapshot(symbol=None):
    symbol = symbol or os.getenv('SYMBOL', 'XAU/USD')
    dxy_symbol = os.getenv('DXY_SYMBOL', 'DXY')
    return {
        'symbol': symbol,
        'm15': fetch_candles(symbol, '15min', 250),
        'h1': fetch_candles(symbol, '1h', 250),
        'h4': fetch_candles(symbol, '4h', 250),
        'd1': fetch_candles(symbol, '1day', 250),
        'dxy_h1': _safe_fetch(dxy_symbol, '1h', 120) if os.getenv('ENABLE_DXY', 'true').lower() == 'true' else None,
    }
