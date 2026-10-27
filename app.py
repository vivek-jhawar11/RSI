"""
Hidden RSI Divergence Scanner: web app (Streamlit).

Run locally:   streamlit run app.py
Needs hidden_rsi_scanner.py in the same folder.

Educational tool, not financial advice. Backtest before trading.
"""
from datetime import date

import matplotlib.pyplot as plt
import pandas as pd
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


def make_fig(df, res, timeframe, bars):
    df = df.copy()
    df["RSI"] = hrs.rsi_wilder(df["Close"])
    d = df.iloc[-bars:]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1.5]})
    ax1.plot(d.index, d["Close"], label=f"{timeframe} close")
    col = "tab:green" if "BULL" in res["signal"] else "tab:red"
    for k in ("swing1", "swing2"):
        t = res[k]
        if t in d.index:
            for ax in (ax1, ax2):
                ax.axvline(t, color=col, alpha=0.3)
            ax1.scatter([t], [res["price" + k[-1]]], color=col, zorder=5)
            ax2.scatter([t], [res["rsi" + k[-1]]], color=col, zorder=5)
    ax1.axhline(res["stop"], color="gray", linestyle=":", label="Stop level")
    ax1.set_title(f"{res['symbol']} ({timeframe})  {res['signal']}")
    ax1.legend()
    ax2.plot(d.index, d["RSI"], color="purple")
    ax2.axhline(70, color="gray", linewidth=0.5)
    ax2.axhline(30, color="gray", linewidth=0.5)
    ax2.set_ylabel("RSI 14")
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

    st.subheader("Swing detection")
    order = st.number_input("Bars each side of a swing", 1, 15, preset["order"], key=f"order_{timeframe}",
                            help="Lower = more signals, more noise")
    max_age = st.number_input("Latest swing at most this many bars old", 1, 60, preset["max_age"],
                              key=f"age_{timeframe}")
    min_gap = st.number_input("Min bars between swings", 1, 100, preset["min_gap"], key=f"min_{timeframe}")
    max_gap = st.number_input("Max bars between swings", 2, 200, preset["max_gap"], key=f"max_{timeframe}")
    confirm = st.number_input(
        "Bars to confirm the latest swing", 1, int(order), int(order), key=f"confirm_{timeframe}_{int(order)}",
        help="How many candles must follow a low/high before it counts as a swing. "
             "1-2 catches fresh swings earlier, but they can be cancelled by the next candles.")
    compare_label = st.radio(
        "Compare the latest swing with", ["Previous swing only", "Any earlier swing in range"],
        key=f"cmp_{timeframe}",
        help="'Any earlier swing' also finds divergences against an older low/high, "
             "as long as it is within the min/max bars above. Raise 'Max bars' to look further back.")
    compare = "any" if compare_label.startswith("Any") else "last"

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
                          min_gap=int(min_gap), max_gap=int(max_gap),
                          confirm=int(confirm), compare=compare)
    if cfg["min_gap"] > cfg["max_gap"]:
        st.error("Min bars between swings must not exceed the max.")
        st.stop()
    try:
        if universe == "Nifty 500":
            symbols = cached_universe()
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
