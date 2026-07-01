import pandas as pd
import numpy as np

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([(high-low), (high-prev_close).abs(), (low-prev_close).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    hist = line - sig
    return line, sig, hist

def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atrv = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atrv)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atrv)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(period).mean()

def bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0):
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return mid + std_mult * sd, mid, mid - std_mult * sd

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for p in [20, 50, 100, 200]:
        df[f"ema{p}"] = ema(df["close"], p)
    df["rsi14"] = rsi(df["close"], 14)
    df["atr14"] = atr(df, 14)
    macd_line, macd_signal, macd_hist = macd(df["close"])
    df["macd"] = macd_line
    df["macd_signal"] = macd_signal
    df["macd_hist"] = macd_hist
    df["adx14"] = adx(df, 14)
    upper, mid, lower = bollinger(df["close"])
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = upper, mid, lower
    return df
