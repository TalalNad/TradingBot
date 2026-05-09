# Assignment 4 Analysis

## What the assignment asks for

The assignment is to build a demo-only automated crypto trading bot with these parts:

1. TradingView Pine Script that creates buy and sell signals from technical indicators.
2. TradingView webhook alerts that send JSON to a Python server.
3. Python Flask or FastAPI backend that receives, logs, validates, and acts on those alerts.
4. Testnet exchange integration that places market orders with testnet keys only.
5. Local trade history stored as CSV or JSON.
6. Documentation report with strategy explanation, workflow diagram, code explanation, screenshots, and conclusion.

## Implementation choices in this repo

- Pine Script strategy: EMA crossover with RSI filter.
- Webhook server: Flask in `bot.py`.
- Exchange: Binance Spot Testnet REST API.
- Safety: `DRY_RUN=true` by default, strict Binance testnet URL validation, and webhook secret validation.
- Local history: incoming alerts in `data/alerts.jsonl`, trade records in `data/trades.csv`, server logs in `logs/bot.log`.
- Diagram/report: `docs/system_flow.mmd`, `docs/system_flow.svg`, and `docs/report.md`.

## Rubric mapping

- Pine Script logic and correctness: `pine/tradingview_ema_rsi_strategy.txt`
- Webhook integration: `/webhook/tradingview` route in `bot.py`
- Python webhook server: Flask app in `bot.py`
- Demo trade execution: `BinanceSpotTestnetClient.place_market_order` in `bot.py`
- Documentation report: `docs/report.md`
- Creativity and error handling: dry-run mode, webhook secret, invalid signal handling, testnet-only guard, CSV/JSON persistence

## Work the student must still do manually

Screenshots cannot be produced without using the student's TradingView account and Binance Testnet account. After running the bot, capture:

- TradingView chart showing BUY/SELL labels.
- Terminal or `logs/bot.log` showing received webhook logs.
- Binance Spot Testnet order confirmation.
- `data/trades.csv` showing recorded trade history.
