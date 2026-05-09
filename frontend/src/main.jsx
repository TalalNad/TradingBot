import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Database,
  RefreshCcw,
  Send,
  Server,
  ShieldCheck,
  Terminal,
  TrendingDown,
  TrendingUp
} from "lucide-react";
import "./styles.css";

const defaultForm = {
  secret: "change-this-secret",
  signal: "buy",
  symbol: "BTCUSDT",
  quantity: "0.001",
  price: "65000.00",
  timeframe: "15",
  strategy: "EMA_RSI_Webhook_Bot"
};

function App() {
  const [status, setStatus] = useState(null);
  const [trades, setTrades] = useState([]);
  const [logs, setLogs] = useState([]);
  const [form, setForm] = useState(defaultForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [lastResponse, setLastResponse] = useState(null);
  const [error, setError] = useState("");

  const refresh = async () => {
    setError("");
    try {
      const [statusResponse, tradesResponse, logsResponse] = await Promise.all([
        fetch("/api/status"),
        fetch("/api/trades?limit=20"),
        fetch("/api/logs?limit=60")
      ]);

      if (!statusResponse.ok || !tradesResponse.ok || !logsResponse.ok) {
        throw new Error("Dashboard API request failed.");
      }

      const [statusData, tradesData, logsData] = await Promise.all([
        statusResponse.json(),
        tradesResponse.json(),
        logsResponse.json()
      ]);

      setStatus(statusData);
      setTrades(tradesData.trades || []);
      setLogs(logsData.lines || []);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const intervalId = window.setInterval(refresh, 5000);
    return () => window.clearInterval(intervalId);
  }, []);

  const totalTrades = trades.length;
  const successfulTrades = useMemo(
    () => trades.filter((trade) => trade.status === "success").length,
    [trades]
  );

  const updateForm = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const sendAlert = async (signal = form.signal) => {
    setIsSending(true);
    setError("");
    setLastResponse(null);

    const payload = {
      secret: form.secret,
      signal,
      symbol: form.symbol,
      quantity: form.quantity,
      strategy: form.strategy,
      price: form.price,
      timeframe: form.timeframe
    };

    try {
      const response = await fetch("/webhook/tradingview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      setLastResponse({ status: response.status, data });
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <main className="app-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">TradingView Webhook Bot</p>
          <h1>Demo Trading Dashboard</h1>
        </div>
        <button className="icon-button" type="button" onClick={refresh} aria-label="Refresh dashboard">
          <RefreshCcw size={18} />
        </button>
      </section>

      <section className="status-grid">
        <Metric
          icon={<Server size={18} />}
          label="Server"
          value={status?.ok ? "Online" : isLoading ? "Checking" : "Offline"}
          tone={status?.ok ? "good" : "warn"}
        />
        <Metric
          icon={<ShieldCheck size={18} />}
          label="Mode"
          value={status?.mode === "dry_run" ? "Dry Run" : "Testnet"}
          tone={status?.mode === "dry_run" ? "warn" : "good"}
        />
        <Metric icon={<Activity size={18} />} label="Recent Trades" value={String(totalTrades)} />
        <Metric icon={<Database size={18} />} label="Successful" value={String(successfulTrades)} tone="good" />
      </section>

      {error && <div className="notice error">{error}</div>}

      <section className="workbench">
        <div className="panel tester-panel">
          <div className="panel-header">
            <h2>Test Alert</h2>
            <div className="signal-tabs" aria-label="Signal">
              <button
                className={form.signal === "buy" ? "active buy" : ""}
                type="button"
                onClick={() => updateForm("signal", "buy")}
              >
                <TrendingUp size={16} />
                Buy
              </button>
              <button
                className={form.signal === "sell" ? "active sell" : ""}
                type="button"
                onClick={() => updateForm("signal", "sell")}
              >
                <TrendingDown size={16} />
                Sell
              </button>
            </div>
          </div>

          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              sendAlert();
            }}
          >
            <Field label="Secret" value={form.secret} onChange={(value) => updateForm("secret", value)} />
            <Field label="Symbol" value={form.symbol} onChange={(value) => updateForm("symbol", value.toUpperCase())} />
            <Field label="Quantity" value={form.quantity} onChange={(value) => updateForm("quantity", value)} />
            <Field label="Price" value={form.price} onChange={(value) => updateForm("price", value)} />
            <Field label="Timeframe" value={form.timeframe} onChange={(value) => updateForm("timeframe", value)} />
            <Field label="Strategy" value={form.strategy} onChange={(value) => updateForm("strategy", value)} />

            <div className="button-row">
              <button className="primary-button" type="submit" disabled={isSending}>
                <Send size={17} />
                {isSending ? "Sending" : "Send Alert"}
              </button>
              <button className="secondary-button buy" type="button" disabled={isSending} onClick={() => sendAlert("buy")}>
                <TrendingUp size={17} />
                Buy
              </button>
              <button className="secondary-button sell" type="button" disabled={isSending} onClick={() => sendAlert("sell")}>
                <TrendingDown size={17} />
                Sell
              </button>
            </div>
          </form>

          <ResponseBox response={lastResponse} />
        </div>

        <div className="panel trades-panel">
          <div className="panel-header">
            <h2>Recent Trades</h2>
            <span className="path-label">{status?.files?.trades || "data/trades.csv"}</span>
          </div>
          <TradesTable trades={trades} />
        </div>
      </section>

      <section className="panel logs-panel">
        <div className="panel-header">
          <h2>Server Logs</h2>
          <span className="path-label">{status?.files?.logs || "logs/bot.log"}</span>
        </div>
        <div className="log-box">
          <Terminal size={16} />
          <pre>{logs.length ? logs.join("\n") : "No logs yet."}</pre>
        </div>
      </section>
    </main>
  );
}

function Metric({ icon, label, value, tone = "neutral" }) {
  return (
    <div className={`metric ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function ResponseBox({ response }) {
  if (!response) {
    return <div className="response-box muted">No alert sent from this dashboard yet.</div>;
  }

  const ok = response.data?.ok;
  return (
    <div className={`response-box ${ok ? "success" : "failed"}`}>
      <div className="response-title">
        <span>HTTP {response.status}</span>
        <strong>{ok ? "Accepted" : "Rejected"}</strong>
      </div>
      <pre>{JSON.stringify(response.data, null, 2)}</pre>
    </div>
  );
}

function TradesTable({ trades }) {
  if (!trades.length) {
    return <div className="empty-state">No trade records yet.</div>;
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Signal</th>
            <th>Symbol</th>
            <th>Qty</th>
            <th>Status</th>
            <th>Order</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade, index) => (
            <tr key={`${trade.order_id}-${index}`}>
              <td>{formatTime(trade.received_at)}</td>
              <td>
                <span className={`signal-pill ${trade.signal}`}>{trade.signal}</span>
              </td>
              <td>{trade.symbol}</td>
              <td>{trade.quantity}</td>
              <td>{trade.status}</td>
              <td className="mono">{trade.order_id || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatTime(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

createRoot(document.getElementById("root")).render(<App />);
