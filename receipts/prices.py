"""Price sources. All read-only and public; no accounts, keys, trading or signing.

- Equities: daily closes from yfinance (split/dividend adjusted), installed with `pip install .[prices]`.
- PURR and other Hyperliquid spot tokens: Hyperliquid's PUBLIC read-only `info` endpoint
  (candleSnapshot). No Hyperliquid account or wallet is used.
- Tests: FixturePrices reads a JSON file of made-up numbers.

A source returns {"YYYY-MM-DD": close} for a ticker over [start, end] inclusive.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request
from pathlib import Path

# Tickers that are not plain equities, and where their prices come from.
SPECIAL = {
    "PURR": {"source": "hyperliquid_spot", "coin": "PURR/USDC"},
}
HYPERLIQUID_INFO = "https://api.hyperliquid.xyz/info"


class PriceError(RuntimeError):
    pass


class FixturePrices:
    """Made-up prices for tests. Never used for real scoring."""

    def __init__(self, path):
        data = json.loads(Path(path).read_text())
        self.data = {k: v for k, v in data.items() if not k.startswith("_")}

    def closes(self, ticker: str, asset_type: str, start: str, end: str) -> dict:
        series = self.data.get(ticker, {})
        return {d: float(p) for d, p in series.items() if start <= d <= end}


def _post_json(url: str, body: dict, timeout: int = 20):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URL)
        return json.loads(r.read())


def parse_hyperliquid_candles(candles: list) -> dict:
    """candleSnapshot rows -> {UTC date of the candle open: close}."""
    out = {}
    for c in candles:
        day = dt.datetime.fromtimestamp(int(c["t"]) / 1000, dt.timezone.utc).date().isoformat()
        out[day] = float(c["c"])
    return out


class LivePrices:
    def __init__(self, fetch_json=_post_json):
        self._post = fetch_json

    def closes(self, ticker: str, asset_type: str, start: str, end: str) -> dict:
        spec = SPECIAL.get(ticker)
        if spec and spec["source"] == "hyperliquid_spot":
            return self._hyperliquid(spec["coin"], start, end)
        if asset_type == "crypto":
            raise PriceError(f"no price source configured for crypto ticker {ticker}; add it to prices.SPECIAL")
        return self._yfinance(ticker, start, end)

    def _hyperliquid(self, coin: str, start: str, end: str) -> dict:
        s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
        e = dt.datetime.fromisoformat(end).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1)
        body = {"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d",
                                                  "startTime": int(s.timestamp() * 1000), "endTime": int(e.timestamp() * 1000)}}
        rows = self._post(HYPERLIQUID_INFO, body)
        return {d: p for d, p in parse_hyperliquid_candles(rows).items() if start <= d <= end}

    def _yfinance(self, ticker: str, start: str, end: str) -> dict:
        try:
            import yfinance as yf  # optional dependency
        except ImportError as e:  # pragma: no cover - depends on the machine
            raise PriceError("equity prices need yfinance: pip install '.[prices]'") from e
        end_excl = (dt.date.fromisoformat(end) + dt.timedelta(days=1)).isoformat()
        df = yf.download(ticker, start=start, end=end_excl, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return {}
        close = df["Close"]
        if hasattr(close, "columns"):  # newer yfinance returns a one-column frame
            close = close.iloc[:, 0]
        return {idx.date().isoformat(): float(v) for idx, v in close.items() if v == v}
