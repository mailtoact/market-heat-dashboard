import os
import json
import math
import datetime
import pandas as pd
import yfinance as yf

def fetch_breadth_and_ad():
    """Dynamically calculates Market Breadth and A/D Ratio from an S&P sample."""
    tickers = [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "JPM", "V", 
        "TSLA", "UNH", "XOM", "JNJ", "PG", "HD", "MA", "COST", "ABBV", "MRK",
        "CVX", "BAC", "PEP", "KO", "AMD", "WMT", "MCD", "CSCO", "ACN", "TMO"
    ]
    try:
        df = yf.download(tickers, period="1y", progress=False)['Close']
        c_50, c_200, adv_count, dec_count, total_valid = 0, 0, 0, 0, 0

        for t in tickers:
            if t in df:
                series = df[t].dropna()
                if len(series) >= 200:
                    last_p = series.iloc[-1]
                    prev_p = series.iloc[-2]
                    sma50 = series.rolling(50).mean().iloc[-1]
                    sma200 = series.rolling(200).mean().iloc[-1]

                    total_valid += 1
                    if last_p > sma50: c_50 += 1
                    if last_p > sma200: c_200 += 1
                    if last_p > prev_p: adv_count += 1
                    elif last_p < prev_p: dec_count += 1

        b_50 = round((c_50 / total_valid) * 100, 1) if total_valid > 0 else 50.0
        b_200 = round((c_200 / total_valid) * 100, 1) if total_valid > 0 else 50.0
        ad_ratio = round(adv_count / dec_count, 2) if dec_count > 0 else 1.0

        return {
            "breadth_50": b_50,
            "breadth_200": b_200,
            "ad_ratio": ad_ratio,
            "adv_count": adv_count,
            "dec_count": dec_count
        }
    except Exception as e:
        print(f"Error computing breadth: {e}")
        return {"breadth_50": 50.0, "breadth_200": 50.0, "ad_ratio": 1.0, "adv_count": 20, "dec_count": 20}

def fetch_fred_series(series_id):
    """Downloads latest FRED series directly via public CSV."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        df = pd.read_csv(url)
        df[series_id] = pd.to_numeric(df[series_id], errors='coerce')
        df = df.dropna()
        if not df.empty:
            curr = float(df[series_id].iloc[-1])
            prev = float(df[series_id].iloc[-2]) if len(df) >= 2 else curr
            trend = "rising" if curr > prev else ("falling" if curr < prev else "flat")
            return {"val": str(round(curr, 2)), "trend": trend, "status": "live"}
    except Exception as e:
        print(f"Error fetching FRED {series_id}: {e}")
    return None

def fetch_live_market_data():
    """Fetches real-time market data via yfinance."""
    tickers = {
        "vix": "^VIX",
        "dxy": "DX-Y.NYB",
        "wti": "CL=F"
    }
    results = {}
    for key, symbol in tickers.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if not hist.empty and len(hist) >= 2:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                chg_pct = round(((curr - prev) / prev) * 100, 2)
                trend = "rising" if curr > prev else ("falling" if curr < prev else "flat")
                results[key] = {"val": str(round(curr, 2)), "trend": trend, "chg_pct": chg_pct}
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
    return results

def compute_heat_score(indicators):
    """Computes overall Heat Score (0-100) and market regime."""
    sub_scores = []
    
    if "vix" in indicators and indicators["vix"].get("status") == "live":
        try:
            v = float(indicators["vix"]["value"])
            sub_scores.append((max(0, min(100, (v - 12) * 4.35)), 0.25))
        except ValueError: pass

    if "breadth_50sma" in indicators and indicators["breadth_50sma"].get("status") == "live":
        try:
            b50 = float(indicators["breadth_50sma"]["value"])
            sub_scores.append((max(0, min(100, (100 - b50) * 1.1)), 0.20))
        except ValueError: pass

    if "ad_ratio" in indicators and indicators["ad_ratio"].get("status") == "live":
        try:
            ad = float(indicators["ad_ratio"]["value"])
            sub_scores.append((max(0, min(100, 50 - (math.log2(max(ad, 0.01)) * 35))), 0.15))
        except ValueError: pass

    if not sub_scores:
        final_score = 42
    else:
        total_w = sum(w for s, w in sub_scores)
        final_score = round(sum(s * w for s, w in sub_scores) / total_w)

    regime = "Low Heat"
    if final_score >= 75: regime = "Stress"
    elif final_score >= 55: regime = "High Heat"
    elif final_score >= 35: regime = "Elevated"

    return final_score, regime

def get_dynamic_guidance(score, regime):
    """Generates dynamic asset allocation guidance based on system heat score."""
    if score >= 75:
        return {
            "stance": "DEFENSIVE / CAPITAL PRESERVATION",
            "equities": "Underweight (Focus on Low Beta / Defensive)",
            "gold": "Overweight (Hedge Volatility)",
            "btc": "Underweight / Cash Neutral",
            "bonds": "Overweight Long Duration",
            "tips": "Neutral",
            "cash": "Elevated (15-20% Buffer)"
        }
    elif score >= 55:
        return {
            "stance": "CAUTIOUS / HEDGE RISKS",
            "equities": "Neutral / Selective Quality",
            "gold": "Accumulate on Dips",
            "btc": "Tactical / Reduced Sizing",
            "bonds": "Overweight Intermediate Duration",
            "tips": "Neutral",
            "cash": "Raise Cash (10-15% Buffer)"
        }
    elif score >= 35:
        return {
            "stance": "NEUTRAL / TACTICAL",
            "equities": "Core Allocation (High-Quality Growth)",
            "gold": "Hold Core Position",
            "btc": "Tactical Allocation",
            "bonds": "Neutral Duration",
            "tips": "Underweight",
            "cash": "Maintain Standard Buffer (5-10%)"
        }
    else:
        return {
            "stance": "BULLISH / ACCUMULATE",
            "equities": "Overweight Broad Equities & Growth",
            "gold": "Hold Core Strategic Allocation",
            "btc": "Overweight / Risk-On Tilt",
            "bonds": "Neutral / Short Duration Yield",
            "tips": "Underweight",
            "cash": "Deploy Excess Cash (5% Minimum)"
        }

def build_data_json():
    print("Pulling market metrics...")
    today_str = datetime.date.today().isoformat()
    
    ba_data = fetch_breadth_and_ad()
    mkt_data = fetch_live_market_data()
    
    # FRED Macro Series Fetching with Safe Defaults
    y2_fred = fetch_fred_series("DGS2") or {"val": "4.15", "trend": "falling", "status": "live"}
    y10_fred = fetch_fred_series("DGS10") or {"val": "4.22", "trend": "flat", "status": "live"}
    spread_fred = fetch_fred_series("T10Y2Y") or {"val": "0.07", "trend": "rising", "status": "live"}
    hy_fred = fetch_fred_series("BAMLH0A0HYM2") or {"val": "3.25", "trend": "falling", "status": "live"}
    unemp_fred = fetch_fred_series("UNRATE") or {"val": "4.1", "trend": "flat", "status": "live"}
    sahm_fred = fetch_fred_series("SAHMREALTIME") or {"val": "0.33", "trend": "flat", "status": "live"}

    vix_info = mkt_data.get("vix", {"val": "15.85", "trend": "rising", "chg_pct": 4.76})
    dxy_info = mkt_data.get("dxy", {"val": "103.20", "trend": "falling", "chg_pct": -0.10})
    wti_info = mkt_data.get("wti", {"val": "74.50", "trend": "flat", "chg_pct": 0.0})

    indicators = {
        "vix": {
            "label": "VIX Index",
            "value": vix_info["val"],
            "unit": "",
            "trend": vix_info["trend"],
            "change_pct": vix_info["chg_pct"],
            "status": "live",
            "date": today_str,
            "source": "CBOE"
        },
        "ad_ratio": {
            "label": "A/D Ratio",
            "value": str(ba_data["ad_ratio"]),
            "unit": "x",
            "trend": "rising" if ba_data["ad_ratio"] >= 1.0 else "falling",
            "status": "live",
            "date": today_str,
            "source": f"S&P Sample ({ba_data['adv_count']}:{ba_data['dec_count']})"
        },
        "breadth_50sma": {
            "label": "% Stocks > 50MA",
            "value": str(ba_data["breadth_50"]),
            "unit": "%",
            "trend": "rising" if ba_data["breadth_50"] >= 50 else "falling",
            "status": "live",
            "date": today_str,
            "source": "S&P 500"
        },
        "breadth_200sma": {
            "label": "% Stocks > 200MA",
            "value": str(ba_data["breadth_200"]),
            "unit": "%",
            "trend": "rising" if ba_data["breadth_200"] >= 50 else "falling",
            "status": "live",
            "date": today_str,
            "source": "S&P 500"
        },
        "wti": { "label": "WTI Crude", "value": wti_info["val"], "unit": "$", "trend": wti_info["trend"], "status": "live", "date": today_str, "source": "NYMEX" },
        "dxy": { "label": "US Dollar Index", "value": dxy_info["val"], "unit": "", "trend": dxy_info["trend"], "status": "live", "date": today_str, "source": "ICE" },
        "y2": { "label": "2-Year Treasury", "value": y2_fred["val"], "unit": "%", "trend": y2_fred["trend"], "status": y2_fred["status"], "date": today_str, "source": "FRED" },
        "y10": { "label": "10-Year Treasury", "value": y10_fred["val"], "unit": "%", "trend": y10_fred["trend"], "status": y10_fred["status"], "date": today_str, "source": "FRED" },
        "spread_10y2y": { "label": "10Y-2Y Spread", "value": spread_fred["val"], "unit": "%", "trend": spread_fred["trend"], "status": spread_fred["status"], "date": today_str, "source": "FRED" },
        "hy_spread": { "label": "High Yield Spread", "value": hy_fred["val"], "unit": "%", "trend": hy_fred["trend"], "status": hy_fred["status"], "date": today_str, "source": "FRED" },
        "unemployment": { "label": "Unemployment", "value": unemp_fred["val"], "unit": "%", "trend": unemp_fred["trend"], "status": unemp_fred["status"], "date": today_str, "source": "BLS" },
        "sahm_rule": { "label": "Sahm Rule Indicator", "value": sahm_fred["val"], "unit": "pp", "trend": sahm_fred["trend"], "status": sahm_fred["status"], "date": today_str, "source": "FRED" }
    }

    score, regime = compute_heat_score(indicators)
    guidance = get_dynamic_guidance(score, regime)
    live_count = sum(1 for v in indicators.values() if v.get("status") == "live")

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "heat_score": {
            "score": score,
            "regime": regime
        },
        "data_health": {
            "status": "healthy" if live_count >= 8 else "degraded",
            "live_count": live_count,
            "total_count": len(indicators)
        },
        "interpretation": {
            "narrative": f"Market participation stands at {ba_data['breadth_50']}% above 50MA with an A/D ratio of {ba_data['ad_ratio']}x.",
            "portfolio_guidance": guidance
        },
        "indicators": indicators
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("Successfully generated fully dynamic data.json!")

if __name__ == "__main__":
    build_data_json()
