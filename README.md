# TradingBot

Demo-only crypto trading bot for Assignment 4. It connects TradingView webhook
alerts to a Python Flask server and can place market orders on Binance Spot
Testnet. Real trading is intentionally blocked.

## Project files

- `bot.py` - Flask webhook server and Binance Spot Testnet order execution.
- `pine/tradingview_ema_rsi_strategy.txt` - TradingView Pine Script strategy.
- `docs/assignment_analysis.md` - assignment breakdown and rubric mapping.
- `docs/system_flow.mmd` and `docs/system_flow.svg` - workflow diagram.
- `docs/report.md` - report draft with screenshot placeholders.
- `samples/buy_alert.json` and `samples/sell_alert.json` - local test payloads.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- Keep `DRY_RUN=true` while testing locally.
- Set `WEBHOOK_SECRET` and use the same value in the Pine Script settings.
- Add Binance Spot Testnet keys from `https://testnet.binance.vision/`.
- Set `DRY_RUN=false` only when you want to place demo testnet orders.

## Run the bot

```bash
python bot.py
```

Health check:

```bash
curl http://127.0.0.1:5000/health
```

Local buy test:

```bash
curl -X POST http://127.0.0.1:5000/webhook/tradingview \
  -H "Content-Type: application/json" \
  --data @samples/buy_alert.json
```

Local sell test:

```bash
curl -X POST http://127.0.0.1:5000/webhook/tradingview \
  -H "Content-Type: application/json" \
  --data @samples/sell_alert.json
```

## Run the React dashboard

The dashboard is in `frontend/`. It expects the Flask bot to be running on port
`5050`.

Terminal 1:

```bash
source .venv/bin/activate
DRY_RUN=true WEBHOOK_SECRET=change-this-secret PORT=5050 python bot.py
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The dashboard can send BUY/SELL test alerts, show the latest server response,
and read recent rows from `data/trades.csv` and `logs/bot.log`.

## TradingView setup

1. Open TradingView and add the script from
   `pine/tradingview_ema_rsi_strategy.txt`.
2. Set the webhook secret, symbol, and quantity in the script settings.
3. Start this Flask server.
4. Expose your local server with a tunnel such as `ngrok http 5000`.
5. Create a TradingView alert with condition:
   `EMA RSI Webhook Bot (Demo Testnet) - Any alert() function call`.
6. Put the public webhook URL in TradingView:
   `https://your-public-url/webhook/tradingview`.

## Evidence for submission

After testing, collect screenshots of:

- TradingView BUY/SELL markers.
- Terminal or `logs/bot.log` showing webhook alerts.
- Binance Spot Testnet demo order confirmations.
- `data/trades.csv` showing saved trade history.
