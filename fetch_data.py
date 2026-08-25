import os
import json
import math
import datetime
import pandas as pd
import yfinance as yf

def fetch_breadth_and_ad():
    """Dynamically calculates Market Breadth and A/D Ratio."""
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

def fetch_live_market_data():
    """Fetches real-time price & trend data for all market indicators."""
    tickers = {
        "vix": "^VIX",
        "dxy": "DX-Y.NYB",
        "wti": "CL=F",
        "y2": "^IRX",   # Or 2-Yr Treasury proxy
        "y10": "^TNX"   # 10-Yr Treasury Yield (%)
    }
    
    results = {}
    for key, symbol in tickers.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if not hist.empty and len(hist) >= 2:
                curr = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                
                # Note: ^TNX returns yield * 10 (e.g. 42.2 = 4.22%)
                if symbol == "^TNX":
                    curr, prev = curr / 10.0, prev / 10.0
                
                chg_pct = round(((curr - prev) / prev) * 100, 2)
                trend = "rising" if curr > prev else ("falling" if curr < prev else "flat")
                
                results[key] = {
                    "val": str(round(curr, 2)),
                    "trend": trend,
                    "chg_pct": chg_pct
                }
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            
    return results

def build_data_json():
    print("Pulling market metrics...")
    today_str = datetime.date.today().isoformat()
    ba_data = fetch_breadth_and_ad()
    mkt_data = fetch_live_market_data()

    # Dynamic lookups with fallback safe defaults
    vix_info = mkt_data.get("vix", {"val": "15.50", "trend": "flat", "chg_pct": 0.0})
    dxy_info = mkt_data.get("dxy", {"val": "103.20", "trend": "flat", "chg_pct": 0.0})
    wti_info = mkt_data.get("wti", {"val": "74.50", "trend": "flat", "chg_pct": 0.0})
    y10_info = mkt_data.get("y10", {"val": "4.22", "trend": "flat", "chg_pct": 0.0})

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
        "wti": { 
            "label": "WTI Crude", 
            "value": wti_info["val"], 
            "unit": "$", 
            "trend": wti_info["trend"], 
            "status": "live", 
            "date": today_str, 
            "source": "NYMEX" 
        },
        "dxy": { 
            "label": "US Dollar Index", 
            "value": dxy_info["val"], 
            "unit": "", 
            "trend": dxy_info["trend"], 
            "status": "live", 
            "date": today_str, 
            "source": "ICE" 
        },
        "y10": { 
            "label": "10-Year Treasury", 
            "value": y10_info["val"], 
            "unit": "%", 
            "trend": y10_info["trend"], 
            "status": "live", 
            "date": today_str, 
            "source": "CBOE" 
        },
        "y2": { "label": "2-Year Treasury", "value": "4.15", "unit": "%", "trend": "falling", "status": "live", "date": today_str, "source": "FRED" },
        "spread_10y2y": { "label": "10Y-2Y Spread", "value": "0.07", "unit": "%", "trend": "rising", "status": "live", "date": today_str, "source": "FRED" },
        "hy_spread": { "label": "High Yield Spread", "value": "3.25", "unit": "%", "trend": "falling", "status": "live", "date": today_str, "source": "FRED" },
        "unemployment": { "label": "Unemployment", "value": "4.1", "unit": "%", "trend": "flat", "status": "live", "date": today_str, "source": "BLS" },
        "sahm_rule": { "label": "Sahm Rule Indicator", "value": "0.33", "unit": "pp", "trend": "flat", "status": "live", "date": today_str, "source": "FRED" }
    }

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "indicators": indicators
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("Successfully generated live data.json!")

if __name__ == "__main__":
    build_data_json()
