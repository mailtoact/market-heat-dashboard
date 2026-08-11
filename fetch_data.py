#!/usr/bin/env python3
"""
Market Heat Dashboard — V5 Data Engine
========================================
Fetches macro indicators from two independent sources:

  * FRED official API (https://api.stlouisfed.org/fred/series/observations)
    -> WTI, 2Y, 10Y, 20Y, 30Y, Unemployment, Sahm Rule, HY spread, IG spread,
       10Y-2Y spread (official T10Y2Y series)
  * Yahoo Finance chart API
    -> DXY (US Dollar Index)

Design goals (V5):
  1. Every feed is fetched independently. One feed failing never breaks
     another feed or crashes the script.
  2. Missing data is NEVER treated as zero, as "stress", or silently
     replaced with stale/sample data. It is marked "unavailable".
  3. Every indicator records its own last observation date + source, so
     genuinely stale-but-valid economic data (e.g. UNRATE updates monthly)
     can be told apart from a broken feed.
  4. The Market Heat Score is renormalized across whatever indicators are
     actually live — missing indicators are simply excluded from the
     weighted average, not counted as extreme readings.
  5. Trend/direction (not just level) feeds into each indicator's
     sub-score, per the original design brief.

This script is intentionally conservative about crashing: the *only* thing
that should stop it from writing a data.json is a bug in this file itself.
Any single network/data problem is caught, logged into the health block,
and the script moves on.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

REQUEST_TIMEOUT = 20        # seconds per HTTP call
MAX_RETRIES = 3
RETRY_BACKOFF = 3           # seconds, multiplied by attempt number

USER_AGENT = "Mozilla/5.0 (MarketHeatDashboard/5.0; +https://github.com)"

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")

# FRED series definitions.
# `n_obs` = how many recent observations to pull, needed to compute a trend.
FRED_SERIES = {
    "wti":          {"series_id": "DCOILWTICO",   "label": "WTI Crude Oil",        "unit": "$/bbl", "n_obs": 30, "decimals": 2},
    "y2":           {"series_id": "DGS2",          "label": "2Y Treasury Yield",    "unit": "%",     "n_obs": 30, "decimals": 2},
    "y10":          {"series_id": "DGS10",         "label": "10Y Treasury Yield",   "unit": "%",     "n_obs": 30, "decimals": 2},
    "y20":          {"series_id": "DGS20",         "label": "20Y Treasury Yield",   "unit": "%",     "n_obs": 30, "decimals": 2},
    "y30":          {"series_id": "DGS30",         "label": "30Y Treasury Yield",   "unit": "%",     "n_obs": 30, "decimals": 2},
    "spread_10y2y": {"series_id": "T10Y2Y",        "label": "10Y-2Y Spread",        "unit": "pp",    "n_obs": 30, "decimals": 2},
    "unemployment": {"series_id": "UNRATE",        "label": "Unemployment Rate",    "unit": "%",     "n_obs": 15, "decimals": 1},
    "sahm_rule":    {"series_id": "SAHMREALTIME",  "label": "Sahm Rule Indicator",  "unit": "pp",    "n_obs": 15, "decimals": 2},
    "hy_spread":    {"series_id": "BAMLH0A0HYM2",  "label": "High Yield Spread",    "unit": "pp",    "n_obs": 30, "decimals": 2},
    "ig_spread":    {"series_id": "BAMLC0A0CM",    "label": "Investment Grade Spread", "unit": "pp", "n_obs": 30, "decimals": 2},
}

YAHOO_TICKERS = {
    "dxy": {"ticker": "DX-Y.NYB", "label": "US Dollar Index (DXY)", "unit": "", "decimals": 2},
}

TOTAL_INDICATOR_COUNT = len(FRED_SERIES) + len(YAHOO_TICKERS)


# --------------------------------------------------------------------------
# Low-level HTTP helper with retries
# --------------------------------------------------------------------------

def _http_get_json(url, timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES):
    """GET a URL and parse JSON, retrying on network/HTTP errors.
    Returns (data, error_message). Exactly one of them is None on success/failure.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            return json.loads(raw), None
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            last_error = f"URLError: {e.reason}"
        except (TimeoutError, OSError) as e:
            last_error = f"Timeout/OS error: {e}"
        except json.JSONDecodeError as e:
            last_error = f"Bad JSON response: {e}"
        except Exception as e:  # noqa: BLE001 - we deliberately want a catch-all here
            last_error = f"Unexpected error: {e}"

        if attempt < max_retries:
            time.sleep(RETRY_BACKOFF * attempt)

    return None, last_error


# --------------------------------------------------------------------------
# FRED fetch
# --------------------------------------------------------------------------

def fetch_fred_series(key, series_id, n_obs):
    """Fetch the most recent n_obs observations for a FRED series.
    Returns a dict describing the outcome; never raises.
    """
    result = {
        "key": key,
        "status": "unavailable",
        "value": None,
        "date": None,
        "trend": None,
        "change_pct": None,
        "source": f"FRED:{series_id}",
        "error": None,
    }

    if not FRED_API_KEY:
        result["error"] = "FRED_API_KEY secret is not set"
        return result

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(n_obs),
    }
    url = f"{FRED_BASE}?{urllib.parse.urlencode(params)}"

    data, err = _http_get_json(url)
    if err is not None:
        result["error"] = err
        return result

    if not isinstance(data, dict) or "observations" not in data:
        result["error"] = "Unexpected FRED response shape (missing 'observations')"
        return result

    observations = data["observations"]
    # FRED uses "." for missing values. Filter down to real numeric observations,
    # most-recent first (we requested sort_order=desc).
    clean = []
    for obs in observations:
        val_str = obs.get("value", ".")
        if val_str in (".", "", None):
            continue
        try:
            clean.append((obs.get("date"), float(val_str)))
        except (TypeError, ValueError):
            continue

    if not clean:
        result["error"] = "No valid numeric observations returned"
        return result

    latest_date, latest_value = clean[0]
    result["value"] = latest_value
    result["date"] = latest_date
    result["status"] = "live"

    # Trend: compare latest value to the value ~5 observations back (a rough
    # "recent direction" window), falling back to the oldest available point
    # if we don't have that many.
    lookback_idx = min(5, len(clean) - 1)
    if lookback_idx > 0:
        _, past_value = clean[lookback_idx]
        if past_value != 0:
            change_pct = (latest_value - past_value) / abs(past_value) * 100.0
        else:
            change_pct = None
        abs_change = latest_value - past_value

        result["change_pct"] = round(change_pct, 2) if change_pct is not None else None
        # For spread/rate-style series expressed in percentage points, a tiny
        # absolute move shouldn't be labeled a strong trend even if % move is large.
        if abs(abs_change) < 1e-9:
            result["trend"] = "flat"
        elif abs_change > 0:
            result["trend"] = "rising"
        else:
            result["trend"] = "falling"
    else:
        result["trend"] = "flat"

    return result


# --------------------------------------------------------------------------
# Yahoo Finance fetch (DXY)
# --------------------------------------------------------------------------

def fetch_yahoo_ticker(key, ticker):
    result = {
        "key": key,
        "status": "unavailable",
        "value": None,
        "date": None,
        "trend": None,
        "change_pct": None,
        "source": f"Yahoo:{ticker}",
        "error": None,
    }

    params = {"range": "1mo", "interval": "1d"}
    url = f"{YAHOO_BASE.format(ticker=urllib.parse.quote(ticker))}?{urllib.parse.urlencode(params)}"

    data, err = _http_get_json(url)
    if err is not None:
        result["error"] = err
        return result

    try:
        chart_result = data["chart"]["result"][0]
        timestamps = chart_result["timestamp"]
        closes = chart_result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        result["error"] = "Unexpected Yahoo Finance response shape"
        return result

    # Filter out trailing/leading None closes (holidays, partial days).
    pairs = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
    if not pairs:
        result["error"] = "No valid close prices returned"
        return result

    latest_ts, latest_value = pairs[-1]
    result["value"] = round(latest_value, 2)
    result["date"] = datetime.fromtimestamp(latest_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    result["status"] = "live"

    lookback_idx = max(0, len(pairs) - 1 - 5)
    past_value = pairs[lookback_idx][1]
    abs_change = latest_value - past_value
    change_pct = (abs_change / abs(past_value) * 100.0) if past_value else None
    result["change_pct"] = round(change_pct, 2) if change_pct is not None else None

    if abs(abs_change) < 1e-9:
        result["trend"] = "flat"
    elif abs_change > 0:
        result["trend"] = "rising"
    else:
        result["trend"] = "falling"

    return result


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
# NOTE: These thresholds are a *placeholder first pass*, deliberately kept
# simple. Per the project brief, calibration against live V5 data comes
# only after the pipeline is confirmed reliable (Data Health ~10/10 live).
# Each indicator produces a 0-100 sub-score on two conceptual axes:
#   - "overheat" pressure (inflationary / late-cycle heat)
#   - "stress" pressure (recession / credit-stress risk)
# The overall Market Heat Score blends both; the regime label uses a small
# decision layer so that stress signals aren't just averaged away by calm
# signals elsewhere (see classify_regime()).

def _level_score(value, low, high):
    """Linear-map value into 0-100 between low and high, clamped."""
    if high == low:
        return 50.0
    pct = (value - low) / (high - low) * 100.0
    return max(0.0, min(100.0, pct))


def score_indicator(key, res):
    """Return (overheat_subscore, stress_subscore, weight) or (None, None, 0)
    if the indicator is unavailable."""
    if res["status"] != "live":
        return None, None, 0.0

    v = res["value"]
    trend = res.get("trend")
    trend_bonus = 8.0 if trend == "rising" else (-8.0 if trend == "falling" else 0.0)

    if key == "wti":
        overheat = _level_score(v, 50, 110) + trend_bonus
        stress = 0.0
        weight = 1.0
    elif key == "y2":
        overheat = _level_score(v, 1.0, 5.5) + trend_bonus
        stress = 0.0
        weight = 1.0
    elif key in ("y10", "y20", "y30"):
        overheat = _level_score(v, 2.0, 5.5) + trend_bonus
        stress = 0.0
        weight = 0.6
    elif key == "spread_10y2y":
        # Inverted (negative) curve = building recession risk; a sharp
        # move back toward/through zero after inversion is the classic
        # late-cycle "un-inversion" stress signal.
        overheat = 0.0
        stress = _level_score(-v, -1.5, 1.5)
        if trend == "rising" and v < 0.3:
            stress += 10.0  # steepening off an inverted/near-inverted base
        weight = 1.0
    elif key == "unemployment":
        overheat = 0.0
        stress = _level_score(v, 3.5, 7.0) + (trend_bonus if trend == "rising" else 0.0)
        weight = 1.0
    elif key == "sahm_rule":
        overheat = 0.0
        # Sahm Rule >= 0.5 is the historical recession trigger.
        stress = _level_score(v, -0.3, 0.7)
        weight = 1.2
    elif key == "hy_spread":
        overheat = 0.0
        stress = _level_score(v, 3.0, 9.0) + trend_bonus
        weight = 1.1
    elif key == "ig_spread":
        overheat = 0.0
        stress = _level_score(v, 0.8, 2.5) + trend_bonus
        weight = 0.8
    elif key == "dxy":
        # Rapid DXY moves in either direction can signal stress (flight to
        # safety / dollar shortage) more than steady levels do.
        overheat = 0.0
        stress = 0.0
        change_pct = res.get("change_pct") or 0.0
        if abs(change_pct) > 3.0:
            stress = min(100.0, abs(change_pct) * 10.0)
        weight = 0.5
    else:
        overheat, stress, weight = 0.0, 0.0, 0.0

    overheat = max(0.0, min(100.0, overheat)) if overheat is not None else None
    stress = max(0.0, min(100.0, stress)) if stress is not None else None
    return overheat, stress, weight


def classify_regime(overheat_score, stress_score, live_count, total_count):
    if live_count == 0:
        return "Unknown", "No live data available to assess market conditions."

    if stress_score >= 55:
        regime = "Stress"
    elif overheat_score >= 65:
        regime = "High Heat"
    elif overheat_score >= 40 or stress_score >= 35:
        regime = "Elevated"
    else:
        regime = "Low Heat"

    narratives = {
        "Low Heat": "Conditions look broadly consistent with a normal / soft-landing environment. No dominant inflationary or recessionary signal.",
        "Elevated": "Some indicators are drifting away from normal ranges. Could be early-stage overheating or early-stage growth slowdown — watch trend direction, not just level.",
        "High Heat": "Inflationary / late-cycle pressure indicators (oil, front-end and long-end yields) are elevated and trending up. Overheating risk dominant over recession risk right now.",
        "Stress": "Recession / financial-stress indicators (credit spreads, unemployment trend, Sahm Rule, yield-curve dynamics) are flashing. Capital-preservation posture warranted over chasing risk.",
        "Unknown": "Insufficient live data.",
    }
    return regime, narratives[regime]


def portfolio_guidance(regime):
    guidance = {
        "Low Heat": {
            "stance": "Risk-on friendly",
            "equities": "Normal / full target weight",
            "gold": "Baseline hedge allocation",
            "btc": "Normal risk-budget allocation",
            "bonds": "Neutral duration",
            "tips": "Baseline allocation",
            "cash": "Baseline liquidity buffer only",
        },
        "Elevated": {
            "stance": "Cautious, watch trend direction",
            "equities": "Maintain but avoid adding aggressively",
            "gold": "Consider modestly increasing hedge",
            "btc": "Hold, avoid adding on leverage",
            "bonds": "Consider trimming duration if yields trending up",
            "tips": "Consider modest increase if inflation-led",
            "cash": "Slightly above baseline",
        },
        "High Heat": {
            "stance": "Inflation-hedge tilt",
            "equities": "Favor quality / pricing-power names over duration-sensitive growth",
            "gold": "Increase allocation",
            "btc": "Neutral to modest allocation, size for volatility",
            "bonds": "Reduce long duration exposure",
            "tips": "Increase allocation",
            "cash": "Above baseline, short-duration instruments",
        },
        "Stress": {
            "stance": "Capital preservation",
            "equities": "Reduce risk, favor defensives/quality",
            "gold": "Increase — classic stress hedge",
            "btc": "Reduce risk sizing; high-beta risk asset in stress regimes",
            "bonds": "Favor high-quality duration as ballast if disinflation/recession-led",
            "tips": "Neutral to modest",
            "cash": "Increase materially — dry powder / safety",
        },
        "Unknown": {
            "stance": "No guidance — insufficient data",
            "equities": "-", "gold": "-", "btc": "-", "bonds": "-", "tips": "-", "cash": "-",
        },
    }
    return guidance[regime]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    print("Market Heat Dashboard V5 — starting data fetch...")
    indicators = {}
    health_detail = []

    # --- FRED indicators, each fully independent ---
    for key, spec in FRED_SERIES.items():
        print(f"  fetching FRED:{spec['series_id']} ({key}) ...")
        res = fetch_fred_series(key, spec["series_id"], spec["n_obs"])
        res["label"] = spec["label"]
        res["unit"] = spec["unit"]
        if res["value"] is not None:
            res["value"] = round(res["value"], spec["decimals"])
        indicators[key] = res
        health_detail.append({"key": key, "label": spec["label"], "status": res["status"], "error": res["error"]})
        if res["status"] != "live":
            print(f"    -> UNAVAILABLE: {res['error']}")
        else:
            print(f"    -> live: {res['value']} {spec['unit']} as of {res['date']}")

    # --- Yahoo indicators ---
    for key, spec in YAHOO_TICKERS.items():
        print(f"  fetching Yahoo:{spec['ticker']} ({key}) ...")
        res = fetch_yahoo_ticker(key, spec["ticker"])
        res["label"] = spec["label"]
        res["unit"] = spec["unit"]
        if res["value"] is not None:
            res["value"] = round(res["value"], spec["decimals"])
        indicators[key] = res
        health_detail.append({"key": key, "label": spec["label"], "status": res["status"], "error": res["error"]})
        if res["status"] != "live":
            print(f"    -> UNAVAILABLE: {res['error']}")
        else:
            print(f"    -> live: {res['value']} as of {res['date']}")

    live_count = sum(1 for r in indicators.values() if r["status"] == "live")
    total_count = TOTAL_INDICATOR_COUNT

    if live_count == total_count:
        health_status = f"{live_count}/{total_count} live"
    else:
        missing = [r["label"] for r in indicators.values() if r["status"] != "live"]
        health_status = f"{live_count}/{total_count} live — " + ", ".join(missing) + " unavailable"

    # --- Heat score, renormalized across live indicators only ---
    overheat_total, stress_total, weight_total = 0.0, 0.0, 0.0
    for key, res in indicators.items():
        overheat, stress, weight = score_indicator(key, res)
        if weight == 0.0:
            continue
        overheat_total += (overheat or 0.0) * weight
        stress_total += (stress or 0.0) * weight
        weight_total += weight

    if weight_total > 0:
        overheat_score = round(overheat_total / weight_total, 1)
        stress_score = round(stress_total / weight_total, 1)
        heat_score = round((overheat_score + stress_score) / 2.0, 1)
    else:
        overheat_score = stress_score = heat_score = None

    if weight_total > 0:
        regime, narrative = classify_regime(overheat_score, stress_score, live_count, total_count)
    else:
        regime, narrative = "Unknown", "No live indicators were available to compute a score."

    guidance = portfolio_guidance(regime)

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_version": "V5",
        "data_health": {
            "live_count": live_count,
            "total_count": total_count,
            "status": health_status,
            "detail": health_detail,
        },
        "indicators": indicators,
        "heat_score": {
            "score": heat_score,
            "overheat_subscore": overheat_score,
            "stress_subscore": stress_score,
            "regime": regime,
            "indicators_used": int(round(weight_total)) if weight_total else 0,
            "indicators_total": total_count,
        },
        "interpretation": {
            "narrative": narrative,
            "portfolio_guidance": guidance,
        },
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nData Health: {health_status}")
    print(f"Heat Score: {heat_score} ({regime})")
    print(f"Wrote {OUTPUT_PATH}")

    # Never fail the whole workflow just because some feeds were down —
    # a partial data.json with clear health status is far more useful than
    # no update at all. Only fail hard on an actual bug (uncaught exception
    # above would already have stopped us before this point).
    return 0


if __name__ == "__main__":
    sys.exit(main())
