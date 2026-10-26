"""
Hidden RSI divergence scanner for NIFTY 500 stocks (hourly, daily or weekly timeframe).

Hidden bullish : price makes a HIGHER low,  RSI makes a LOWER low
Hidden bearish : price makes a LOWER high,  RSI makes a HIGHER high

No moving-average / trend filter is applied. Price swings and RSI both use the CLOSE.
The Nifty 500 list is downloaded from NSE at run time.

Usage:
    pip install yfinance pandas numpy requests
    python hidden_rsi_scanner.py                          # scans NIFTY 500 (daily)
    python hidden_rsi_scanner.py --timeframe weekly       # weekly candles
    python hidden_rsi_scanner.py --timeframe hourly       # 1-hour candles (last ~3 months)
    python hidden_rsi_scanner.py --list ind_nifty500list.csv   # use a downloaded NSE csv
    python hidden_rsi_scanner.py --file my_list.txt       # one symbol per line

Educational tool only, not financial advice. Backtest before trading.
"""
import argparse
import io
import sys
import time

import numpy as np
import pandas as pd
import requests

NIFTY500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/",
}


def rsi_wilder(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(avg_loss != 0, 100.0)


def pivots(series, order, kind):
    """Positions of swing lows/highs confirmed by `order` bars on each side."""
    vals = series.values
    idx = []
    for i in range(order, len(vals) - order):
        window = vals[i - order : i + order + 1]
        if np.isnan(window).any():
            continue
        if kind == "low" and vals[i] == window.min() and (window == vals[i]).sum() == 1:
            idx.append(i)
        elif kind == "high" and vals[i] == window.max() and (window == vals[i]).sum() == 1:
            idx.append(i)
    return idx


def detect(df, order=5, rsi_period=14, min_gap=5, max_gap=60, max_age=10, min_bars=60):
    """
    df needs High, Low, Close columns. Returns a LIST of signal dicts (0, 1 or 2 items).
    max_age : the latest swing must be at most this many bars before the last bar.
    """
    if len(df) < min_bars:
        return []
    df = df.copy()
    df["RSI"] = rsi_wilder(df["Close"], rsi_period)
    close, rsi = df["Close"], df["RSI"]
    n = len(df)
    last, prev = df.iloc[-1], df.iloc[-2]
    signals = []

    for kind in ("low", "high"):
        bull = kind == "low"
        pv = pivots(close, order, kind)
        if len(pv) < 2:
            continue
        i1, i2 = pv[-2], pv[-1]
        gap, age = i2 - i1, (n - 1) - i2
        if not (min_gap <= gap <= max_gap and age <= max_age):
            continue
        c1, c2 = close.iloc[i1], close.iloc[i2]
        r1, r2 = rsi.iloc[i1], rsi.iloc[i2]
        if np.isnan(r1) or np.isnan(r2):
            continue

        if bull:
            ok = c2 > c1 and r2 < r1          # higher price low, lower RSI low
            stop = df["Low"].iloc[i2]
            confirmed = last["Close"] > prev["High"]
            name = "HIDDEN BULLISH"
        else:
            ok = c2 < c1 and r2 > r1          # lower price high, higher RSI high
            stop = df["High"].iloc[i2]
            confirmed = last["Close"] < prev["Low"]
            name = "HIDDEN BEARISH"
        if not ok:
            continue

        signals.append(dict(
            signal=name, confirmed=bool(confirmed),
            close=round(float(last["Close"]), 2), stop=round(float(stop), 2),
            swing1=df.index[i1], swing2=df.index[i2],
            price1=round(float(c1), 2), price2=round(float(c2), 2),
            rsi1=round(float(r1), 1), rsi2=round(float(r2), 1),
            rsi_now=round(float(last["RSI"]), 1),
        ))
    return signals


def get_nifty500(local_csv=None):
    """Return the list of NSE symbols in the Nifty 500 (from NSE, or a local csv you saved)."""
    if local_csv:
        table = pd.read_csv(local_csv)
    else:
        try:
            r = requests.get(NIFTY500_URL, headers=HEADERS, timeout=30)
            r.raise_for_status()
            table = pd.read_csv(io.StringIO(r.text))
        except Exception as e:
            raise RuntimeError(
                f"Could not download the Nifty 500 list from NSE ({e}). Download "
                f"ind_nifty500list.csv from {NIFTY500_URL} in your browser, put it next to "
                "this script/notebook and pass its path (local_csv / --list)."
            )
    col = next(c for c in table.columns if c.strip().lower() == "symbol")
    syms = table[col].astype(str).str.strip().str.upper().tolist()
    return [s for s in dict.fromkeys(syms) if s and s != "NAN"]


def get_frame(data, tk, single=False):
    if isinstance(data.columns, pd.MultiIndex):
        if tk not in data.columns.get_level_values(0):
            return None
        return data[tk].dropna(subset=["Close"])
    return data.dropna(subset=["Close"]) if single else None


def download_prices(tickers, period="1y", interval="1d", batch=100, pause=1.0):
    """Download prices (interval 1d or 1wk) in batches. Returns {ticker: DataFrame}; missing tickers are skipped."""
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        try:
            data = yf.download(chunk, period=period, interval=interval, group_by="ticker",
                               auto_adjust=True, progress=False, threads=True)
        except Exception as e:
            print(f"  batch starting {chunk[0]} failed: {e}")
            continue
        for tk in chunk:
            df = get_frame(data, tk, single=len(chunk) == 1)
            if df is not None and not df.empty:
                out[tk] = df
        print(f"  downloaded {min(i + batch, len(tickers))}/{len(tickers)}")
        time.sleep(pause)
    return out


def drop_partial_week(df, now=None):
    """Drop the last weekly bar while that week is still in progress (NSE closes Friday 15:30 IST)."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    if df.empty:
        return df
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    week_start = pd.Timestamp(df.index[-1]).tz_localize(None).normalize()
    week_end = week_start + timedelta(days=4, hours=15, minutes=30)   # Friday 15:30
    if now.replace(tzinfo=None) < week_end:
        return df.iloc[:-1]
    return df


def drop_partial_hour(df, now=None, bar_minutes=60):
    """Drop the last hourly bar while it is still forming (NSE session 09:15-15:30 IST)."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    if df.empty:
        return df
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    start = pd.Timestamp(df.index[-1])
    if start.tzinfo is not None:
        start = start.tz_convert("Asia/Kolkata").tz_localize(None)
    session_end = start.normalize() + timedelta(hours=15, minutes=30)
    bar_end = min(start + timedelta(minutes=bar_minutes), session_end)
    if now.replace(tzinfo=None) < bar_end:
        return df.iloc[:-1]
    return df


PRESETS = {
    "hourly": dict(interval="1h",  period="3mo", order=5, max_age=10, min_gap=5, max_gap=60,
                   min_bars=60, plot_bars=150),
    "daily":  dict(interval="1d",  period="1y", order=5, max_age=10, min_gap=5, max_gap=60,
                   min_bars=60, plot_bars=120),
    "weekly": dict(interval="1wk", period="3y", order=3, max_age=6,  min_gap=4, max_gap=40,
                   min_bars=40, plot_bars=80),
}


def make_config(timeframe="daily", **overrides):
    """Settings for 'hourly', 'daily' or 'weekly'. Any override that is not None replaces the preset value."""
    if timeframe not in PRESETS:
        raise ValueError(f"timeframe must be one of {list(PRESETS)}, got {timeframe!r}")
    cfg = dict(PRESETS[timeframe])
    cfg["timeframe"] = timeframe
    cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


def prepare_prices(prices, cfg, include_partial=False, include_partial_week=None):
    """Drop the current unfinished candle for weekly and hourly scans (unless include_partial).
    include_partial_week is the old name for include_partial and still works."""
    include_partial = include_partial or bool(include_partial_week)
    if cfg["timeframe"] == "weekly" and not include_partial:
        return {t: drop_partial_week(d) for t, d in prices.items()}
    if cfg["timeframe"] == "hourly" and not include_partial:
        return {t: drop_partial_hour(d) for t, d in prices.items()}
    return prices


def scan(prices, cfg):
    """Run detect() on every {ticker: DataFrame}; returns a list of signal dicts with a 'symbol'."""
    rows = []
    for tk, df in prices.items():
        for res in detect(df, order=cfg["order"], min_gap=cfg["min_gap"], max_gap=cfg["max_gap"],
                          max_age=cfg["max_age"], min_bars=cfg["min_bars"]):
            res["symbol"] = tk.replace(".NS", "")
            rows.append(res)
    return rows


def load_symbols(path):
    with open(path) as f:
        return [l.strip().upper().replace(".NS", "") for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", help="local copy of NSE ind_nifty500list.csv (skips the download)")
    ap.add_argument("--file", help="text file with one NSE symbol per line (instead of Nifty 500)")
    ap.add_argument("--timeframe", choices=list(PRESETS), default="daily",
                    help="candle size to scan (default daily)")
    ap.add_argument("--order", type=int, help="bars each side to confirm a swing (hourly/daily 5, weekly 3)")
    ap.add_argument("--max-age", type=int, help="max bars since latest swing (hourly/daily 10, weekly 6)")
    ap.add_argument("--min-gap", type=int, help="min bars between the two swings (hourly/daily 5, weekly 4)")
    ap.add_argument("--max-gap", type=int, help="max bars between the two swings (hourly/daily 60, weekly 40)")
    ap.add_argument("--include-partial", "--include-partial-week", dest="include_partial",
                    action="store_true",
                    help="weekly/hourly only: also use the current unfinished candle")
    ap.add_argument("--confirmed-only", action="store_true")
    ap.add_argument("--out", help="output csv (default hidden_rsi_signals_<timeframe>.csv)")
    args = ap.parse_args()
    cfg = make_config(args.timeframe, order=args.order, max_age=args.max_age,
                      min_gap=args.min_gap, max_gap=args.max_gap)
    out_file = args.out or f"hidden_rsi_signals_{args.timeframe}.csv"

    symbols = load_symbols(args.file) if args.file else get_nifty500(args.list)
    tickers = [s + ".NS" for s in symbols]
    print(f"Downloading {args.timeframe} data for {len(tickers)} symbols...")
    prices = download_prices(tickers, period=cfg["period"], interval=cfg["interval"])
    prices = prepare_prices(prices, cfg, include_partial=args.include_partial)
    rows = scan(prices, cfg)

    failed = [t.replace(".NS", "") for t in tickers if t not in prices]
    print(f"Scanned {len(prices)} symbols, {len(failed)} had no data, {len(rows)} signals.")
    if failed:
        print("No data for:", ", ".join(failed))
    if args.confirmed_only:
        rows = [r for r in rows if r["confirmed"]]
    if not rows:
        print("No hidden divergences found.")
        return
    cols = ["symbol", "signal", "confirmed", "close", "stop", "swing1", "swing2",
            "price1", "price2", "rsi1", "rsi2", "rsi_now"]
    out = pd.DataFrame(rows)[cols].sort_values(["signal", "confirmed"], ascending=[True, False])
    out.to_csv(out_file, index=False)
    print(out.to_string(index=False))
    print(f"\nSaved to {out_file}")


if __name__ == "__main__":
    main()
