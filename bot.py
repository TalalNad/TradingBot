"""TradingView webhook trading bot for Binance Spot Testnet demo orders.

This project is intentionally testnet-only. The default mode is DRY_RUN=true,
which records alerts and fake fills locally. Set DRY_RUN=false only after adding
Binance Spot Testnet API keys to .env.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    import requests
    from dotenv import load_dotenv
    from flask import Flask, jsonify, request
except ImportError as exc:  # pragma: no cover - handled at runtime for users.
    raise SystemExit(
        "Missing dependency. Run: pip install -r requirements.txt"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parent
VALID_SIGNALS = {"buy": "BUY", "sell": "SELL"}


class ConfigError(Exception):
    """Raised when environment configuration is unsafe or incomplete."""


class ExchangeError(Exception):
    """Raised when Binance rejects a signed testnet API request."""

    def __init__(self, message: str, status_code: int, payload: dict[str, Any]):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class BotConfig:
    webhook_secret: str
    dry_run: bool
    binance_base_url: str
    binance_api_key: str
    binance_api_secret: str
    default_symbol: str
    default_quantity: str
    host: str
    port: int
    flask_debug: bool
    log_file: Path
    alerts_file: Path
    trades_file: Path

    @classmethod
    def from_env(cls) -> "BotConfig":
        load_dotenv(PROJECT_ROOT / ".env")

        config = cls(
            webhook_secret=os.getenv("WEBHOOK_SECRET", "").strip(),
            dry_run=getenv_bool("DRY_RUN", default=True),
            binance_base_url=os.getenv(
                "BINANCE_BASE_URL", "https://testnet.binance.vision"
            ).strip().rstrip("/"),
            binance_api_key=os.getenv("BINANCE_API_KEY", "").strip(),
            binance_api_secret=os.getenv("BINANCE_API_SECRET", "").strip(),
            default_symbol=os.getenv("DEFAULT_SYMBOL", "BTCUSDT").strip().upper(),
            default_quantity=os.getenv("DEFAULT_QUANTITY", "0.001").strip(),
            host=os.getenv("HOST", "0.0.0.0").strip(),
            port=int(os.getenv("PORT", "5000")),
            flask_debug=getenv_bool("FLASK_DEBUG", default=False),
            log_file=PROJECT_ROOT / os.getenv("LOG_FILE", "logs/bot.log").strip(),
            alerts_file=PROJECT_ROOT
            / os.getenv("ALERTS_FILE", "data/alerts.jsonl").strip(),
            trades_file=PROJECT_ROOT
            / os.getenv("TRADES_FILE", "data/trades.csv").strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.default_symbol:
            raise ConfigError("DEFAULT_SYMBOL cannot be empty.")

        validate_positive_decimal(self.default_quantity, "DEFAULT_QUANTITY")

        if not is_binance_testnet_url(self.binance_base_url):
            raise ConfigError(
                "BINANCE_BASE_URL must point to Binance testnet. "
                "Use https://testnet.binance.vision for this assignment."
            )

        if not self.dry_run and (
            not self.binance_api_key or not self.binance_api_secret
        ):
            raise ConfigError(
                "DRY_RUN=false requires BINANCE_API_KEY and BINANCE_API_SECRET "
                "from Binance Spot Testnet."
            )

        for path in (self.log_file, self.alerts_file, self.trades_file):
            path.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class TradingAlert:
    received_at: str
    signal: str
    side: str
    symbol: str
    quantity: str
    strategy: str
    price: str
    timeframe: str
    raw_payload: dict[str, Any]


def getenv_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ConfigError(f"{name} must be a boolean value.")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_positive_decimal(value: str, field_name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal number.") from exc

    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")

    return number


def is_binance_testnet_url(url: str) -> bool:
    normalized = url.lower()
    return "testnet.binance.vision" in normalized


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    if "secret" in sanitized:
        sanitized["secret"] = "***"
    return sanitized


def parse_tradingview_alert(
    payload: dict[str, Any], config: BotConfig
) -> TradingAlert:
    raw_signal = payload.get("signal") or payload.get("side")
    if raw_signal is None:
        raise ValueError("Missing required field: signal.")

    signal = str(raw_signal).strip().lower()
    if signal not in VALID_SIGNALS:
        raise ValueError("Invalid signal. Use 'buy' or 'sell'.")

    raw_symbol = payload.get("symbol") or config.default_symbol
    symbol = str(raw_symbol).strip().upper().replace("/", "")
    if not symbol:
        raise ValueError("Symbol cannot be empty.")

    raw_quantity = payload.get("quantity") or config.default_quantity
    quantity = str(raw_quantity).strip()
    validate_positive_decimal(quantity, "quantity")

    return TradingAlert(
        received_at=utc_now_iso(),
        signal=signal,
        side=VALID_SIGNALS[signal],
        symbol=symbol,
        quantity=quantity,
        strategy=str(payload.get("strategy") or "TradingView").strip(),
        price=str(payload.get("price") or "").strip(),
        timeframe=str(payload.get("timeframe") or "").strip(),
        raw_payload=sanitize_payload(payload),
    )


class TradeStore:
    def __init__(self, alerts_file: Path, trades_file: Path) -> None:
        self.alerts_file = alerts_file
        self.trades_file = trades_file

    def append_alert(self, payload: dict[str, Any]) -> None:
        record = {"received_at": utc_now_iso(), "payload": sanitize_payload(payload)}
        with self.alerts_file.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(record, sort_keys=True) + "\n")

    def append_trade(
        self,
        alert: TradingAlert,
        dry_run: bool,
        status: str,
        exchange_response: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> None:
        file_exists = self.trades_file.exists() and self.trades_file.stat().st_size > 0
        fieldnames = [
            "received_at",
            "strategy",
            "signal",
            "side",
            "symbol",
            "quantity",
            "price",
            "timeframe",
            "dry_run",
            "status",
            "order_id",
            "exchange_response",
            "error_message",
        ]
        exchange_response = exchange_response or {}

        with self.trades_file.open("a", newline="", encoding="utf-8") as file_handle:
            writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            writer.writerow(
                {
                    "received_at": alert.received_at,
                    "strategy": alert.strategy,
                    "signal": alert.signal,
                    "side": alert.side,
                    "symbol": alert.symbol,
                    "quantity": alert.quantity,
                    "price": alert.price,
                    "timeframe": alert.timeframe,
                    "dry_run": dry_run,
                    "status": status,
                    "order_id": extract_order_id(exchange_response),
                    "exchange_response": json.dumps(exchange_response, sort_keys=True),
                    "error_message": error_message,
                }
            )


def read_recent_trades(trades_file: Path, limit: int = 25) -> list[dict[str, Any]]:
    if not trades_file.exists() or trades_file.stat().st_size == 0:
        return []

    with trades_file.open("r", newline="", encoding="utf-8") as file_handle:
        rows = list(csv.DictReader(file_handle))

    rows.reverse()
    return rows[:limit]


def read_recent_log_lines(log_file: Path, limit: int = 80) -> list[str]:
    if not log_file.exists() or log_file.stat().st_size == 0:
        return []

    with log_file.open("r", encoding="utf-8") as file_handle:
        lines = file_handle.readlines()

    return [line.rstrip("\n") for line in lines[-limit:]]


class DryRunExchangeClient:
    def place_market_order(
        self, symbol: str, side: str, quantity: str
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "orderId": f"DRYRUN-{uuid.uuid4().hex[:12].upper()}",
            "clientOrderId": f"dryrun-{uuid.uuid4().hex[:16]}",
            "transactTime": int(time.time() * 1000),
            "price": "0",
            "origQty": quantity,
            "executedQty": quantity,
            "cummulativeQuoteQty": "0",
            "status": "FILLED",
            "timeInForce": "GTC",
            "type": "MARKET",
            "side": side,
            "fills": [],
            "note": "Dry run only. No exchange API request was sent.",
        }


class BinanceSpotTestnetClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self._time_offset_ms: int | None = None

    def place_market_order(
        self, symbol: str, side: str, quantity: str
    ) -> dict[str, Any]:
        params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
        }
        return self._signed_request("POST", "/api/v3/order", params)

    def _signed_request(
        self, method: str, path: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if self._time_offset_ms is None:
            self._sync_server_time()

        last_payload: dict[str, Any] = {}
        for attempt in range(2):
            signed_params = dict(params)
            signed_params["recvWindow"] = 5000
            signed_params["timestamp"] = self._timestamp_ms()

            query_string = urlencode(signed_params)
            signature = hmac.new(
                self.api_secret.encode("utf-8"),
                query_string.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            url = f"{self.base_url}{path}?{query_string}&signature={signature}"
            response = self.session.request(
                method,
                url,
                headers={"X-MBX-APIKEY": self.api_key},
                timeout=15,
            )
            payload = parse_json_response(response)
            last_payload = payload

            if response.ok:
                return payload

            if payload.get("code") == -1021 and attempt == 0:
                self._sync_server_time()
                continue

            raise ExchangeError(
                f"Binance Testnet returned HTTP {response.status_code}.",
                response.status_code,
                payload,
            )

        raise ExchangeError("Binance request failed.", 502, last_payload)

    def _sync_server_time(self) -> None:
        response = self.session.get(f"{self.base_url}/api/v3/time", timeout=10)
        payload = parse_json_response(response)
        if not response.ok:
            raise ExchangeError(
                "Could not sync Binance Testnet server time.",
                response.status_code,
                payload,
            )

        server_time = int(payload["serverTime"])
        local_time = int(time.time() * 1000)
        self._time_offset_ms = server_time - local_time

    def _timestamp_ms(self) -> int:
        offset = self._time_offset_ms or 0
        return int(time.time() * 1000) + offset


def parse_json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    if isinstance(payload, dict):
        return payload
    return {"data": payload}


def extract_order_id(exchange_response: dict[str, Any]) -> str:
    for key in ("orderId", "clientOrderId"):
        if key in exchange_response:
            return str(exchange_response[key])
    return ""


def configure_logging(config: BotConfig) -> logging.Logger:
    logger = logging.getLogger("trading_bot")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        config.log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def create_app() -> Flask:
    config = BotConfig.from_env()
    logger = configure_logging(config)
    store = TradeStore(config.alerts_file, config.trades_file)
    exchange_client: DryRunExchangeClient | BinanceSpotTestnetClient

    if config.dry_run:
        exchange_client = DryRunExchangeClient()
        logger.info("Bot started in DRY_RUN mode.")
    else:
        exchange_client = BinanceSpotTestnetClient(
            config.binance_base_url,
            config.binance_api_key,
            config.binance_api_secret,
        )
        logger.info("Bot started in Binance Spot Testnet mode.")

    if not config.webhook_secret:
        logger.warning("WEBHOOK_SECRET is empty. Set one before exposing the server.")

    app = Flask(__name__)
    app.config["BOT_CONFIG"] = config

    @app.get("/")
    def index() -> Any:
        return jsonify(
            {
                "name": "TradingView Binance Testnet Bot",
                "mode": "dry_run" if config.dry_run else "binance_spot_testnet",
                "webhook_endpoint": "/webhook/tradingview",
                "health_endpoint": "/health",
            }
        )

    @app.get("/health")
    def health() -> Any:
        return jsonify(
            {
                "ok": True,
                "mode": "dry_run" if config.dry_run else "binance_spot_testnet",
                "default_symbol": config.default_symbol,
                "default_quantity": config.default_quantity,
            }
        )

    @app.get("/api/status")
    def api_status() -> Any:
        return jsonify(
            {
                "ok": True,
                "mode": "dry_run" if config.dry_run else "binance_spot_testnet",
                "default_symbol": config.default_symbol,
                "default_quantity": config.default_quantity,
                "webhook_secret_configured": bool(config.webhook_secret),
                "testnet_url": config.binance_base_url,
                "files": {
                    "alerts": str(config.alerts_file.relative_to(PROJECT_ROOT)),
                    "trades": str(config.trades_file.relative_to(PROJECT_ROOT)),
                    "logs": str(config.log_file.relative_to(PROJECT_ROOT)),
                },
            }
        )

    @app.get("/api/trades")
    def api_trades() -> Any:
        limit = parse_limit(request.args.get("limit"), default=25, maximum=100)
        return jsonify(
            {
                "ok": True,
                "trades": read_recent_trades(config.trades_file, limit=limit),
            }
        )

    @app.get("/api/logs")
    def api_logs() -> Any:
        limit = parse_limit(request.args.get("limit"), default=80, maximum=300)
        return jsonify(
            {
                "ok": True,
                "lines": read_recent_log_lines(config.log_file, limit=limit),
            }
        )

    @app.post("/webhook/tradingview")
    def tradingview_webhook() -> Any:
        if not request.is_json:
            return error_response("Request must be JSON.", 415)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error_response("Invalid JSON payload.", 400)

        store.append_alert(payload)
        logger.info("Received alert: %s", sanitize_payload(payload))

        if config.webhook_secret:
            supplied_secret = str(
                request.headers.get("X-Webhook-Secret")
                or payload.get("secret")
                or ""
            )
            if not secrets.compare_digest(supplied_secret, config.webhook_secret):
                logger.warning("Rejected alert because webhook secret was invalid.")
                return error_response("Invalid webhook secret.", 401)

        try:
            alert = parse_tradingview_alert(payload, config)
        except ValueError as exc:
            logger.warning("Rejected alert because validation failed: %s", exc)
            return error_response(str(exc), 400)

        try:
            exchange_response = exchange_client.place_market_order(
                symbol=alert.symbol,
                side=alert.side,
                quantity=alert.quantity,
            )
        except ExchangeError as exc:
            store.append_trade(
                alert,
                dry_run=config.dry_run,
                status="failed",
                exchange_response=exc.payload,
                error_message=str(exc),
            )
            logger.exception("Exchange rejected the order.")
            return error_response(
                "Exchange rejected the order.",
                502,
                details=exc.payload,
            )
        except requests.RequestException as exc:
            store.append_trade(
                alert,
                dry_run=config.dry_run,
                status="failed",
                error_message=str(exc),
            )
            logger.exception("Network error while sending order to exchange.")
            return error_response("Network error while contacting exchange.", 502)

        store.append_trade(
            alert,
            dry_run=config.dry_run,
            status="success",
            exchange_response=exchange_response,
        )
        logger.info(
            "Order handled: side=%s symbol=%s quantity=%s order_id=%s",
            alert.side,
            alert.symbol,
            alert.quantity,
            extract_order_id(exchange_response),
        )

        return jsonify(
            {
                "ok": True,
                "mode": "dry_run" if config.dry_run else "binance_spot_testnet",
                "trade": {
                    "signal": alert.signal,
                    "side": alert.side,
                    "symbol": alert.symbol,
                    "quantity": alert.quantity,
                    "status": "success",
                    "order_id": extract_order_id(exchange_response),
                },
            }
        )

    return app


def error_response(
    message: str, status_code: int, details: dict[str, Any] | None = None
) -> tuple[Any, int]:
    body: dict[str, Any] = {"ok": False, "error": message}
    if details is not None:
        body["details"] = details
    return jsonify(body), status_code


def parse_limit(raw_value: str | None, default: int, maximum: int) -> int:
    if raw_value is None:
        return default

    try:
        limit = int(raw_value)
    except ValueError:
        return default

    return max(1, min(limit, maximum))


if __name__ == "__main__":
    try:
        flask_app = create_app()
        active_config = flask_app.config["BOT_CONFIG"]
    except (ConfigError, ValueError) as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    flask_app.run(
        host=active_config.host,
        port=active_config.port,
        debug=active_config.flask_debug,
    )
