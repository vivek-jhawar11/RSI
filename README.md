# Hidden RSI Divergence Scanner

Web app that scans the Nifty 500 (or your own list) for hidden bullish and hidden bearish RSI divergence on daily or weekly candles.

- Hidden bullish: higher price low, lower RSI low
- Hidden bearish: lower price high, higher RSI high
- No trend filter. Educational tool, not financial advice.

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
