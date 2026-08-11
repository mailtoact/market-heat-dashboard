import os
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
FRED_API_KEY = os.getenv("FRED_API_KEY")

FRED_SERIES = {
    'WTI': 'DCOILWTICO',
    'US2Y': 'DGS2',
    'US10Y': 'DGS10',
    'US20Y': 'DGS20',
    'US30Y': 'DGS30',
    'US10Y2Y': 'T10Y2Y',
    'UNEMP': 'UNRATE',
    'SAHM': 'SAHMREALTIME',
    'HY_SPREAD': 'BAMLH0A0HYM2',
    'IG_SPREAD': 'BAMLC0A0CM'
}

EQUITY_TICKERS = {
    'VTI': 'Vanguard Total Stock Market',
    'GLD': 'SPDR Gold Shares',
    'IBIT': 'iShares Bitcoin Trust',
    'BND': 'Vanguard Total Bond Market',
    'SCHP': 'Schwab U.S. TIPS ETF'
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def fetch_fred_series(series_id, api_key, limit=90):
    url = f"https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': series_id,
        'api_key': api_key,
        'file_type': 'json',
        'sort_order': 'desc',
        'limit': limit
    }
    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        obs = [o for o in data.get('observations', []) if o['value'] != '.']
        if not obs:
            return None
        return {
            'value': float(obs[0]['value']),
            'date': obs[0]['date'],
            'history': [float(o['value']) for o in obs if o['value'] != '.']
        }
    except Exception as e:
        print(f"Error fetching FRED series {series_id}: {e}")
        return None

def fetch_yahoo_ticker(ticker, period="6m"):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period)
        if df.empty or len(df) < 5:
            return None
        close_series = df['Close'].dropna()
        return close_series
    except Exception as e:
        print(f"Error fetching Yahoo ticker {ticker}: {e}")
        return None

def generate_svg_sparkline(prices, width=120, height=30):
    if not prices or len(prices) < 2:
        return ""
    prices = list(prices)[-30:] # Last 30 points
    min_p, max_p = min(prices), max(prices)
    range_p = max_p - min_p if max_p != min_p else 1.0
    
    points = []
    for i, p in enumerate(prices):
        x = (i / (len(prices) - 1)) * width
        y = height - (((p - min_p) / range_p) * (height - 4) + 2)
        points.append(f"{x:.1f},{y:.1f}")
    
    return f"M " + " L ".join(points)

def calculate_returns(series):
    if series is None or len(series) < 2:
        return {'last': None, 'd1': None, 'm1': None, 'm3': None}
    
    last = float(series.iloc[-1])
    d1 = ((last / series.iloc[-2]) - 1) * 100 if len(series) >= 2 else 0.0
    m1 = ((last / series.iloc[-22]) - 1) * 100 if len(series) >= 22 else 0.0
    m3 = ((last / series.iloc[-65]) - 1) * 100 if len(series) >= 65 else 0.0
    
    return {
        'last': round(last, 2),
        'd1': round(d1, 2),
        'm1': round(m1, 2),
        'm3': round(m3, 2)
    }

# ==========================================
# MAIN EXECUTION PIPELINE
# ==========================================
def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    results = {'timestamp': timestamp, 'macro': {}, 'assets': {}, 'health': {}}
    
    # 1. Fetch Macro Feeds from FRED
    live_count = 0
    total_feeds = len(FRED_SERIES) + 1 # +1 for DXY
    
    for key, series_id in FRED_SERIES.items():
        data = fetch_fred_series(series_id, FRED_API_KEY)
        if data:
            results['macro'][key] = data
            live_count += 1
        else:
            results['macro'][key] = {'value': None, 'date': 'N/A', 'history': []}
            
    # 2. Fetch DXY from Yahoo
    dxy_series = fetch_yahoo_ticker("DX-Y.NYB", period="3m")
    if dxy_series is not None and not dxy_series.empty:
        results['macro']['DXY'] = {
            'value': round(float(dxy_series.iloc[-1]), 2),
            'date': dxy_series.index[-1].strftime("%Y-%m-%d"),
            'history': dxy_series.tolist()
        }
        live_count += 1
    else:
        results['macro']['DXY'] = {'value': None, 'date': 'N/A', 'history': []}

    results['health']['live_status'] = f"{live_count}/{total_feeds} Live"

    # 3. Calculate Market Heat Score (0 - 100)
    # Simple dynamic normalization placeholder
    score = 45 # Default Baseline (Normal / Soft Landing)
    regime = "Soft Landing / Growth"
    if results['macro']['HY_SPREAD']['value'] and results['macro']['HY_SPREAD']['value'] > 5.0:
        score += 25
        regime = "High Heat / Credit Stress"
    elif results['macro']['SAHM']['value'] and results['macro']['SAHM']['value'] >= 0.5:
        score += 35
        regime = "Recession Risk / Stress"

    results['macro']['heat_score'] = score
    results['macro']['regime'] = regime

    # 4. Fetch Asset Portfolio Matrix (VTI, GLD, IBIT, BND, SCHP)
    for ticker, name in EQUITY_TICKERS.items():
        s = fetch_yahoo_ticker(ticker, period="6m")
        if s is not None:
            ret = calculate_returns(s)
            sparkline = generate_svg_sparkline(s)
            
            # Tailwinds evaluation
            tailwind = "Neutral"
            if ticker in ['VTI', 'IBIT'] and score <= 50:
                tailwind = "Favorable"
            elif ticker in ['GLD', 'SCHP'] and score > 50:
                tailwind = "Favorable"
            elif ticker == 'BND' and score > 65:
                tailwind = "Favorable"

            results['assets'][ticker] = {
                'name': name,
                'price': ret['last'],
                'd1_pct': ret['d1'],
                'm1_pct': ret['m1'],
                'm3_pct': ret['m3'],
                'tailwind': tailwind,
                'sparkline_svg': sparkline
            }
        else:
            results['assets'][ticker] = {
                'name': name, 'price': None, 'd1_pct': 0, 'm1_pct': 0, 'm3_pct': 0,
                'tailwind': 'Unavailable', 'sparkline_svg': ''
            }

    # Save output to data.json
    with open("data.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"data.json updated successfully at {timestamp}. Status: {results['health']['live_status']}")

if __name__ == "__main__":
    main()
