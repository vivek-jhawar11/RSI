# Hidden RSI Divergence Scanner

Web app that scans the Nifty 500 (or your own list) for hidden bullish and hidden bearish RSI divergence on hourly, daily or weekly candles.

Hourly scans use Yahoo Finance's 1-hour candles for the last 3 months (NSE session candles start 09:15, 10:15 ... 15:15 IST). The current unfinished candle is left out by default, for weekly and hourly alike.

- Hidden bullish: higher price low, lower RSI low
- Hidden bearish: lower price high, higher RSI high
- No trend filter. Educational tool, not financial advice.

Two optional settings in the sidebar control how strict swing detection is:
- **Bars to confirm the latest swing** (default = swing size): set to 1 or 2 to catch a fresh low/high earlier. It can be cancelled by the next candles, so expect some false signals.
- **Compare the latest swing with**: *Previous swing only* (default) or *Any earlier swing in range*, which also finds divergences against an older low/high (raise *Max bars* to look further back).

## Run on your computer

```
pip install -r requirements.txt
streamlit run app.py
```

## Host it free from GitHub

GitHub Pages cannot run Python, so use Streamlit Community Cloud, which deploys straight from a GitHub repo:

1. Create a GitHub repo and upload `app.py`, `hidden_rsi_scanner.py`, `requirements.txt` and this README (all in the repo root).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click **Create app**, pick the repo and branch, set the main file to `app.py`, and deploy.
4. You get a public URL you can open from any device. If you make the repo private, the app can still be deployed, and you can restrict who may view it in the app's sharing settings.

If a scan shows "Could not download the Nifty 500 list from NSE", NSE sometimes blocks cloud servers. Use the "My own list" option, or add the Nifty 500 symbols to the repo and load them from there.
