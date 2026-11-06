"""Scoring: point-in-time closes, hit/miss, excess vs SPY, Brier, calibration, Wilson CI.
All prices come from tests/fixtures/prices.json, which are FIXTURE (made-up) numbers."""
import math
from pathlib import Path

import pytest

from receipts import scoring
from receipts.prices import FixturePrices

FIX = FixturePrices(Path(__file__).parent / "fixtures" / "prices.json")


def call(**over):
    c = {"ticker": "HOOD", "asset_type": "equity", "direction": "up", "confidence": 0.7,
         "horizon_start_date": "2027-02-10", "horizon_end_date": "2027-02-18"}
    c.update(over)
    return c


def test_hit_uses_start_and_end_closes_and_excess_vs_spy():
    s = scoring.score_call(call(), FIX)
    assert s["start_close"] == 50.0 and s["end_close"] == 54.0
    assert s["return"] == pytest.approx(0.08)
    assert s["benchmark_return"] == pytest.approx(0.01)
    assert s["excess_return"] == pytest.approx(0.07)
    assert s["hit"] is True and s["status"] == "scored"


def test_down_call_hits_when_price_falls():
    s = scoring.score_call(call(ticker="COIN", direction="down", confidence=0.6), FIX)
    assert s["hit"] is True and s["return"] == pytest.approx(-0.05)


def test_non_trading_end_date_uses_last_close_on_or_before():
    s = scoring.score_call(call(horizon_end_date="2027-02-16"), FIX)  # 13-16 missing -> 2027-02-12
    assert s["end_close"] == 47.0 and s["end_date_used"] == "2027-02-12"
    assert s["hit"] is False


def test_never_uses_prices_after_the_horizon():
    s = scoring.score_call(call(horizon_end_date="2027-02-11"), FIX)
    assert s["end_date_used"] == "2027-02-11" and s["end_close"] == 51.0


def test_crypto_has_no_spy_benchmark():
    s = scoring.score_call(call(ticker="PURR", asset_type="crypto", horizon_start_date="2027-01-15",
                                horizon_end_date="2027-01-29"), FIX)
    assert s["hit"] is True and s["benchmark_return"] is None and s["excess_return"] is None


def test_missing_prices_mark_pending_not_scored():
    s = scoring.score_call(call(ticker="NVDA", horizon_start_date="2027-05-01", horizon_end_date="2027-05-10"), FIX)
    assert s["status"] == "pending_prices" and s["hit"] is None


def test_summary_brier_calibration_and_wilson():
    scored = [
        {"status": "scored", "hit": True, "confidence": 0.9},
        {"status": "scored", "hit": False, "confidence": 0.6},
        {"status": "scored", "hit": True, "confidence": 0.65},
        {"status": "pending_prices", "hit": None, "confidence": 0.8},
    ]
    s = scoring.summarize(scored)
    assert s["n"] == 3 and s["hits"] == 2
    assert s["hit_rate"] == pytest.approx(2 / 3)
    assert s["brier"] == pytest.approx(((0.9 - 1) ** 2 + (0.6 - 0) ** 2 + (0.65 - 1) ** 2) / 3)
    lo, hi = s["hit_rate_ci95"]
    assert 0 < lo < 2 / 3 < hi < 1
    b = {x["range"]: x for x in s["calibration"]}
    assert b["0.60-0.70"]["n"] == 2 and b["0.60-0.70"]["hit_rate"] == pytest.approx(0.5)
    assert b["0.90-1.00"]["n"] == 1
    assert s["too_few_to_judge"] is True


def test_wilson_matches_formula():
    lo, hi = scoring.wilson(8, 10)
    z = 1.959963984540054
    p = 0.8
    c = (p + z * z / 20) / (1 + z * z / 10)
    m = z * math.sqrt(p * (1 - p) / 10 + z * z / 400) / (1 + z * z / 10)
    assert lo == pytest.approx(c - m) and hi == pytest.approx(c + m)


def test_too_few_flag_clears_at_ten():
    s = scoring.summarize([{"status": "scored", "hit": True, "confidence": 0.7}] * 10)
    assert s["too_few_to_judge"] is False


def test_empty_summary_is_safe():
    s = scoring.summarize([])
    assert s["n"] == 0 and s["hit_rate"] is None and s["brier"] is None and s["too_few_to_judge"] is True


def test_purr_source_follows_asset_type():
    """PURR is both a Hyperliquid spot token and a Nasdaq ticker (Hyperliquid Strategies).
    The call's asset_type decides where prices come from."""
    from receipts.prices import LivePrices

    calls_made = []

    class Spy(LivePrices):
        def _hyperliquid(self, coin, start, end):
            calls_made.append(("hyperliquid", coin))
            return {}

        def _yfinance(self, ticker, start, end):
            calls_made.append(("yfinance", ticker))
            return {}

    p = Spy()
    p.closes("PURR", "crypto", "2027-01-15", "2027-01-29")
    p.closes("PURR", "equity", "2027-01-15", "2027-01-29")
    assert calls_made == [("hyperliquid", "PURR/USDC"), ("yfinance", "PURR")]


def test_hyperliquid_candles_parse_to_utc_dates():
    from receipts.prices import parse_hyperliquid_candles

    rows = [{"t": 1799971200000, "c": "0.2"}, {"t": 1800057600000, "c": "0.25"}]  # FIXTURE candles
    assert parse_hyperliquid_candles(rows) == {"2027-01-15": 0.2, "2027-01-16": 0.25}
