"""Faithful port of the supplied Saab B Momentum Scanner v1 Pine v6 rules.
Input: 5-minute OHLCV, sorted by timestamp. No trading/order execution.
"""
import numpy as np
import pandas as pd


def ema(s, span):
    return s.ewm(span=span, adjust=False, min_periods=1).mean()


def rsi_wilder(close, length=14):
    # Wilder RMA initialized from SMA of the first `length` changes.
    d = close.diff()
    up, down = d.clip(lower=0), (-d).clip(lower=0)
    def rma(v):
        out = pd.Series(np.nan, index=v.index, dtype=float)
        if len(v) <= length:
            return out
        seed = v.iloc[1:length + 1].mean()
        out.iloc[length] = seed
        for i in range(length + 1, len(v)):
            out.iloc[i] = (out.iloc[i - 1] * (length - 1) + v.iloc[i]) / length
        return out
    a, b = rma(up), rma(down)
    result = 100 - 100 / (1 + a / b.replace(0, np.nan))
    result = result.mask((b == 0) & (a > 0), 100)
    result = result.mask((b == 0) & (a == 0), 50)
    return result


def scan(df, threshold=70, vol_multiplier=1.5, min_tick=0.01):
    x = df.copy().sort_index()
    for k in ('open', 'high', 'low', 'close', 'volume'):
        x[k] = pd.to_numeric(x[k], errors='raise')
    c, o, h, l, v = (x[k] for k in ('close', 'open', 'high', 'low', 'volume'))
    x['ema9'], x['ema21'] = ema(c, 9), ema(c, 21)
    x['rsi'] = rsi_wilder(c)
    macd = ema(c, 12) - ema(c, 26)
    x['macd_hist'] = macd - ema(macd, 9)
    volume_avg = v.rolling(20, min_periods=20).mean()
    volume_strong = v > volume_avg * vol_multiplier
    engulfing = (c > o) & (c.shift() < o.shift()) & (c >= o.shift()) & (o <= c.shift())
    body = (c - o).abs()
    spread = h - l
    lower_wick = np.minimum(o, c) - l
    upper_wick = h - np.maximum(o, c)
    hammer = (spread > 0) & (c > o) & (lower_wick >= np.maximum(body, min_tick) * 2) & (upper_wick <= np.maximum(body, min_tick))
    rsi_strong = (x.rsi > 50) & (x.rsi < 70) & (x.rsi > x.rsi.shift())
    macd_strong = (x.macd_hist > 0) & (x.macd_hist > x.macd_hist.shift())
    ema_strong = (c > x.ema9) & (x.ema9 > x.ema21)
    gap = (x.ema21 - x.ema9) / c * 100
    early = (x.ema9 < x.ema21) & (x.ema9 > x.ema9.shift()) & (gap <= 0.20) & (x.rsi > x.rsi.shift()) & volume_strong & (c > o)

    # Use *previous completed* 15m candle for each 5m candle, as in Pine
    # request.security(..., ta.ema(close,20)[1] > ta.ema(close,50)[1], lookahead_on).
    # Index represents 5m candle OPEN time; resample at session clock 00:00.
    if not isinstance(x.index, pd.DatetimeIndex):
        raise ValueError('Timestamp-index behövs för 15-minuterstrenden.')
    closes15 = c.resample('15min', label='left', closed='left').last().dropna()
    trend15_series = (ema(closes15, 20).shift(1) > ema(closes15, 50).shift(1))
    # Align to current 15-minute block, including first/second/third 5m bars.
    blocks = x.index.floor('15min')
    trend15 = pd.Series(trend15_series.reindex(blocks).fillna(False).to_numpy(dtype=bool), index=x.index)
    x['score'] = (engulfing.astype(int) * 20 + hammer.astype(int) * 15 + rsi_strong.astype(int) * 15 + macd_strong.astype(int) * 15 + volume_strong.astype(int) * 20 + ema_strong.astype(int) * 10 + trend15.astype(int) * 5)
    x['watch_condition'] = early.fillna(False)
    x['watch_alert'] = (early & ~early.shift(1).fillna(False)).astype(bool)
    x['buy'] = ((x.score >= threshold) & (x.score.shift(1) < threshold)).fillna(False)
    x['trend15'] = trend15
    return x


def demo_ohlcv():
    """Synthetic bars, deliberately not representing Saab prices."""
    rng = np.random.default_rng(117)
    dates = pd.bdate_range('2026-10-12', periods=25)
    times = [d + pd.Timedelta(hours=9) + pd.Timedelta(minutes=5*i) for d in dates for i in range(102)]
    idx = pd.DatetimeIndex(times, name='timestamp')
    returns = rng.normal(0.00008, 0.0019, len(idx))
    close = 100 * np.exp(np.cumsum(returns))
    op = np.r_[100, close[:-1]]
    hi = np.maximum(op, close) * (1 + rng.uniform(0, 0.0014, len(idx)))
    lo = np.minimum(op, close) * (1 - rng.uniform(0, 0.0014, len(idx)))
    vol = rng.integers(1500, 13000, len(idx)).astype(float)
    vol[rng.choice(len(idx), size=125, replace=False)] *= 3
    return pd.DataFrame({'open': op, 'high': hi, 'low': lo, 'close': close, 'volume': vol}, index=idx)
