"""Score revealed calls honestly.

Point-in-time rules:
- Baseline = the close on horizon_start_date, or the last close before it if the market was shut.
- Outcome  = the last close on or before horizon_end_date. Nothing after the horizon is ever used.
- Hit      = price moved in the called direction (up: end > start; down: end < start).
- Equities also report the return of SPY over the same dates and the excess return.

Aggregate: hit rate with a 95% Wilson interval, Brier score (mean of (confidence - outcome)^2;
0 is perfect, 0.25 is a coin flip at 50%), and calibration buckets. Under 10 scored calls the
summary says so: that is too few to judge skill.
"""
from __future__ import annotations

import datetime as dt
import math

MIN_TO_JUDGE = 10
BUCKETS = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.00)]
Z95 = 1.959963984540054


def _close_on_or_before(series: dict, day: str, not_before: str):
    eligible = [d for d in series if not_before <= d <= day]
    if not eligible:
        return None, None
    d = max(eligible)
    return d, series[d]


def score_call(call: dict, prices, benchmark: str = "SPY", lookback_days: int = 7) -> dict:
    start, end = call["horizon_start_date"], call["horizon_end_date"]
    window_start = (dt.date.fromisoformat(start) - dt.timedelta(days=lookback_days)).isoformat()
    series = prices.closes(call["ticker"], call["asset_type"], window_start, end)
    s_day, s_px = _close_on_or_before(series, start, window_start)
    e_day, e_px = _close_on_or_before(series, end, start)
    base = {"ticker": call["ticker"], "confidence": call["confidence"], "direction": call["direction"],
            "start_date_used": s_day, "end_date_used": e_day, "start_close": s_px, "end_close": e_px,
            "return": None, "benchmark": None, "benchmark_return": None, "excess_return": None, "hit": None}
    if s_px is None or e_px is None or e_day == s_day:
        return dict(base, status="pending_prices")
    ret = e_px / s_px - 1.0
    hit = ret > 0 if call["direction"] == "up" else ret < 0
    out = dict(base, status="scored", hit=bool(hit), **{"return": ret})
    if call["asset_type"] == "equity":
        bser = prices.closes(benchmark, "equity", window_start, end)
        _, b0 = _close_on_or_before(bser, start, window_start)
        _, b1 = _close_on_or_before(bser, end, start)
        if b0 and b1:
            out["benchmark"] = benchmark
            out["benchmark_return"] = b1 / b0 - 1.0
            out["excess_return"] = ret - out["benchmark_return"]
    return out


def wilson(hits: int, n: int, z: float = Z95):
    if n == 0:
        return None, None
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def summarize(scored: list) -> dict:
    done = [s for s in scored if s.get("status") == "scored"]
    n, hits = len(done), sum(1 for s in done if s["hit"])
    calib = []
    for lo, hi in BUCKETS:
        inb = [s for s in done if lo <= s["confidence"] < hi or (hi == 1.00 and s["confidence"] == 1.00)]
        calib.append({"range": f"{lo:.2f}-{hi:.2f}", "n": len(inb),
                      "avg_confidence": (sum(s["confidence"] for s in inb) / len(inb)) if inb else None,
                      "hit_rate": (sum(1 for s in inb if s["hit"]) / len(inb)) if inb else None})
    return {
        "n": n,
        "hits": hits,
        "pending": sum(1 for s in scored if s.get("status") != "scored"),
        "hit_rate": hits / n if n else None,
        "hit_rate_ci95": list(wilson(hits, n)) if n else None,
        "brier": sum((s["confidence"] - (1.0 if s["hit"] else 0.0)) ** 2 for s in done) / n if n else None,
        "calibration": calib,
        "too_few_to_judge": n < MIN_TO_JUDGE,
        "min_to_judge": MIN_TO_JUDGE,
    }
