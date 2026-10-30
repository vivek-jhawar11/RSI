"""
Hidden RSI Divergence Scanner: web app (Streamlit).

Run locally:   streamlit run app.py
Needs hidden_rsi_scanner.py in the same folder.

Educational tool, not financial advice. Backtest before trading.
"""
import io
from datetime import date

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st

import hidden_rsi_scanner as hrs

st.set_page_config(page_title="Hidden RSI Scanner", page_icon="📈", layout="wide")

COLS = ["symbol", "signal", "confirmed", "close", "stop", "swing1", "swing2",
        "price1", "price2", "rsi1", "rsi2", "rsi_now"]


# ---------- cached data helpers ----------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cached_universe():
    return hrs.get_nifty500()


@st.cache_data(ttl=900, show_spinner=False)
def cached_chunk(chunk, period, interval):
    return hrs.download_prices(list(chunk), period=period, interval=interval, batch=len(chunk), pause=0)


def fetch_prices(tickers, period, interval, batch=100):
    """Download in batches with a progress bar. Each batch is cached for 15 minutes."""
    out, bar = {}, st.progress(0.0, text="Downloading prices...")
    for i in range(0, len(tickers), batch):
        chunk = tuple(tickers[i : i + batch])
        out.update(cached_chunk(chunk, period, interval))
        bar.progress(min(1.0, (i + batch) / len(tickers)),
                     text=f"Downloaded {min(i + batch, len(tickers))}/{len(tickers)}")
    bar.empty()
    return out


def candle_ticks(index, timeframe, max_ticks=8):
    """Tick positions and labels for a chart drawn by candle number."""
    n = len(index)
    if timeframe == "hourly":
        day = pd.Index([ts.date() for ts in index])
        pos = [0] + [i for i in range(1, n) if day[i] != day[i - 1]]      # first candle of each day
        fmt = "%d %b"
    else:
        pos = list(range(n))
        fmt = "%d %b %y" if timeframe == "weekly" else "%d %b"
    step = max(1, int(np.ceil(len(pos) / max_ticks)))
    pos = pos[::step]
    return pos, [index[i].strftime(fmt) for i in pos]


def make_fig(df, res, timeframe, bars):
    """Price + RSI chart (seaborn), drawn by candle number like TradingView: no gaps for
    nights, weekends or holidays (a real time axis would draw long sloped lines across them)."""
    df = df.copy()
    df["RSI"] = hrs.rsi_wilder(df["Close"])
    d = df.iloc[-bars:]
    x = np.arange(len(d))
    col = "#2e9e5b" if "BULL" in res["signal"] else "#d64545"
    with sns.axes_style("whitegrid"):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1.5]})
    sns.lineplot(x=x, y=d["Close"].values, ax=ax1, color="#1f77b4", linewidth=1.6,
                 label=f"{timeframe} close")
    sns.lineplot(x=x, y=d["RSI"].values, ax=ax2, color="#7b3fa0", linewidth=1.4)
    for k in ("swing1", "swing2"):
        pos = d.index.get_indexer([res[k]])[0]
        if pos >= 0:
            for ax in (ax1, ax2):
                ax.axvline(pos, color=col, alpha=0.3)
            sns.scatterplot(x=[pos], y=[res["price" + k[-1]]], ax=ax1, color=col, s=70, zorder=5, legend=False)
            sns.scatterplot(x=[pos], y=[res["rsi" + k[-1]]], ax=ax2, color=col, s=70, zorder=5, legend=False)
    ax1.axhline(res["stop"], color="gray", linestyle=":", label="Stop level")
    ax1.set_title(f"{res['symbol']} ({timeframe})  {res['signal']}")
    ax1.legend(loc="upper left")
    ax2.axhline(70, color="gray", linewidth=0.8, linestyle="--")
    ax2.axhline(30, color="gray", linewidth=0.8, linestyle="--")
    ax2.set_ylabel("RSI 14")
    ticks, labels = candle_ticks(d.index, timeframe)
    ax2.set_xticks(ticks)
    ax2.set_xticklabels(labels)
    ax2.set_xlim(-1, len(d))
    sns.despine(fig)
    fig.tight_layout()
    return fig


# ---------- sidebar ----------
st.title("Hidden RSI Divergence Scanner")
st.caption("Hidden bullish: higher price low + lower RSI low. Hidden bearish: lower price high + higher RSI high. "
           "No trend filter. Educational tool, not financial advice.")

with st.sidebar:
    st.header("Settings")
    timeframe = st.radio("Timeframe", list(hrs.PRESETS), index=list(hrs.PRESETS).index("daily"),
                         horizontal=True)
    preset = hrs.PRESETS[timeframe]

    universe = st.radio("Stocks", ["Nifty 500", "My own list"], horizontal=True)
    custom = ""
    if universe == "My own list":
        custom = st.text_area("NSE symbols (comma or space separated)", "TCS, INFY, RELIANCE")
    uploaded = None
    if universe == "Nifty 500":
        uploaded = st.file_uploader(
            "Nifty 500 list (optional CSV)", type="csv",
            help="Only needed if NSE blocks the automatic download (error 403). Download "
                 "ind_nifty500list.csv from NSE in your browser and upload it here. "
                 "Or add that file to your GitHub repo next to app.py and it is picked up automatically.")

    st.subheader("Swing detection")
    order = st.number_input("Bars each side of a swing", 1, 15, preset["order"], key=f"order_{timeframe}",
                            help="Lower = more signals, more noise")
    max_age = st.number_input("Latest swing at most this many bars old", 1, 60, preset["max_age"],
                              key=f"age_{timeframe}")
    min_gap = st.number_input("Min bars between swings", 1, 100, preset["min_gap"], key=f"min_{timeframe}")
    max_gap = st.number_input("Max bars between swings", 2, 200, preset["max_gap"], key=f"max_{timeframe}")

    st.subheader("Filters")
    only_confirmed = st.checkbox("Only confirmed signals", False,
                                 help="Latest close breaks the previous candle's high (bullish) or low (bearish)")
    signal_filter = st.multiselect("Signal type", ["HIDDEN BULLISH", "HIDDEN BEARISH"],
                                   default=["HIDDEN BULLISH", "HIDDEN BEARISH"])
    include_partial = False
    if timeframe in ("weekly", "hourly"):
        include_partial = st.checkbox(
            "Include current unfinished " + ("week" if timeframe == "weekly" else "hour"), False)

    run = st.button("Run scan", type="primary", width="stretch")

# ---------- run ----------
if run:
    cfg = hrs.make_config(timeframe, order=int(order), max_age=int(max_age),
                          min_gap=int(min_gap), max_gap=int(max_gap))
    if cfg["min_gap"] > cfg["max_gap"]:
        st.error("Min bars between swings must not exceed the max.")
        st.stop()
    try:
        if universe == "Nifty 500":
            symbols = (hrs.get_nifty500(io.BytesIO(uploaded.getvalue())) if uploaded is not None
                       else cached_universe())
        else:
            symbols = [s.strip().upper().replace(".NS", "")
                       for s in custom.replace(",", " ").split() if s.strip()]
    except Exception as e:
        st.error(str(e))
        st.stop()
    if not symbols:
        st.warning("No symbols to scan.")
        st.stop()

    tickers = [s + ".NS" for s in symbols]
    prices = fetch_prices(tickers, cfg["period"], cfg["interval"])
    prices = hrs.prepare_prices(prices, cfg, include_partial=include_partial)
    rows = hrs.scan(prices, cfg)
    failed = [t.replace(".NS", "") for t in tickers if t not in prices]
    st.session_state["result"] = dict(rows=rows, prices=prices, cfg=cfg, failed=failed,
                                      n=len(tickers), when=pd.Timestamp.now().strftime("%d %b %Y %H:%M"))

res = st.session_state.get("result")
if not res:
    st.info("Pick your settings in the sidebar and press **Run scan**. "
            "A full Nifty 500 scan takes a few minutes the first time; repeat scans within 15 minutes are quicker.")
    st.stop()

# ---------- results ----------
rows = [r for r in res["rows"]
        if r["signal"] in signal_filter and (r["confirmed"] or not only_confirmed)]
cfg = res["cfg"]
st.subheader(f"{len(rows)} signals ({cfg['timeframe']})")
st.caption(f"Scanned {len(res['prices'])} of {res['n']} symbols at {res['when']}.")
if res["failed"]:
    with st.expander(f"{len(res['failed'])} symbols had no data"):
        st.write(", ".join(res["failed"]))

if not rows:
    st.write("No hidden divergences match the current filters.")
    st.stop()

table = (pd.DataFrame(rows)[COLS]
         .sort_values(["signal", "confirmed"], ascending=[True, False]).reset_index(drop=True))
st.dataframe(table, width="stretch", hide_index=True)
st.download_button("Download CSV", table.to_csv(index=False).encode(),
                   file_name=f"hidden_rsi_signals_{cfg['timeframe']}_{date.today().isoformat()}.csv",
                   mime="text/csv")

st.subheader("Chart")
labels = [f"{r['symbol']}  {r['signal']}" for r in rows]
pick = st.selectbox("Signal", range(len(rows)), format_func=lambda i: labels[i])
sel = rows[pick]
fig = make_fig(res["prices"][sel["symbol"] + ".NS"], sel, cfg["timeframe"], cfg["plot_bars"])
st.pyplot(fig)
plt.close(fig)
