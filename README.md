# Market Heat Dashboard — V5

A self-hosted, free-to-run macro dashboard that scores overall "market heat"
(0–100) and classifies the environment as **Low Heat / Elevated / High Heat /
Stress**, with rough portfolio-posture guidance (equities, gold, BTC, bonds,
TIPS, cash). Runs entirely on GitHub Actions + GitHub Pages — no server to
maintain, no hosting bill. Add it to your iPhone Home Screen from Safari and
it behaves like a native app (PWA).

```
FRED API + Yahoo Finance  →  GitHub Actions (fetch_data.py)  →  data.json
                                                                     │
                                                    GitHub Pages ◄───┘
                                                          │
                                                       iPhone (PWA)
```

## What changed in V5

V2 → Fixed → Fixed2 → Fixed3 → V4 all pulled economic series from FRED's
public graph/CSV endpoints, which turned out to be unreliable when called
from GitHub Actions' IP ranges (only DXY, sourced from Yahoo Finance,
consistently worked — hence "1/9 live" on V4).

**V5 fixes the root cause** by switching every FRED-sourced indicator to the
**official FRED REST API** (`api.stlouisfed.org`), authenticated with a free
API key stored as a GitHub Actions secret. Key properties of V5:

- Every indicator is fetched **independently** — one failure can't take down
  the others.
- Missing data is shown as **"Unavailable"**, never silently treated as
  zero, as an extreme reading, or filled with stale/sample data.
- The **Data Health** strip at the top of the dashboard shows e.g.
  `11/11 live` or `9/11 live — HY Spread, Sahm Rule Indicator unavailable`.
- The Market Heat Score is **renormalized** across whatever indicators are
  actually live that hour.
- Every indicator card shows its **source and last observation date**, so
  you can tell "FRED hasn't published this month's unemployment number yet"
  apart from "this feed is broken."
- Level *and* trend both matter — each indicator's sub-score reacts to
  direction (rising/falling), not just the raw level.

## Indicators tracked

| Indicator | Source | Series |
|---|---|---|
| WTI Crude Oil | FRED | `DCOILWTICO` |
| 2Y Treasury Yield | FRED | `DGS2` |
| 10Y Treasury Yield | FRED | `DGS10` |
| 20Y Treasury Yield | FRED | `DGS20` |
| 30Y Treasury Yield | FRED | `DGS30` |
| 10Y–2Y Spread | FRED (official spread series) | `T10Y2Y` |
| Unemployment Rate | FRED | `UNRATE` |
| Sahm Rule (real-time) | FRED | `SAHMREALTIME` |
| High Yield Credit Spread | FRED (ICE BofA) | `BAMLH0A0HYM2` |
| Investment Grade Credit Spread | FRED (ICE BofA) | `BAMLC0A0CM` |
| US Dollar Index (DXY) | Yahoo Finance | `DX-Y.NYB` |

## One-time setup

### 1. Get a free FRED API key
1. Create a free account at https://fred.stlouisfed.org/
2. Go to **My Account → API Keys → Request API Key**
3. Copy the key (a long alphanumeric string).

### 2. Add it as a GitHub Actions secret — never in code
1. In this repository: **Settings → Secrets and variables → Actions**
2. **New repository secret**
3. Name: **`FRED_API_KEY`** (must match exactly)
4. Value: paste the key from FRED
5. **Add secret**

The key is only ever read from `os.environ["FRED_API_KEY"]` inside
`fetch_data.py`, injected by `update.yml`. It is never written to
`data.json`, `index.html`, or any committed file.

### 3. Enable GitHub Pages
**Settings → Pages → Source → GitHub Actions.** The `deploy.yml` workflow
handles the rest.

### 4. Run it
- The **Update Market Data** workflow runs automatically every hour
  (`.github/workflows/update.yml`), or trigger it manually from
  **Actions → Update Market Data → Run workflow**.
- Every successful commit to `data.json` on `main` automatically triggers
  **Deploy Market Heat** to republish the site.
- Open the GitHub Pages URL on your iPhone in Safari, tap **Share → Add to
  Home Screen**.

## Files

| File | Purpose |
|---|---|
| `fetch_data.py` | Data engine: fetches all indicators, scores heat, writes `data.json` |
| `data.json` | Generated output; committed automatically by the update workflow |
| `index.html` | The PWA dashboard itself (single file, no build step) |
| `manifest.json` | PWA manifest (Home Screen icon/name/theme) |
| `icon.svg` | App icon |
| `sw.js` | Service worker — caches the app shell only; `data.json` is always fetched fresh |
| `.github/workflows/update.yml` | Hourly data refresh + commit |
| `.github/workflows/deploy.yml` | Publishes the static site to GitHub Pages |

## Checking Data Health / debugging a feed

1. **Actions → Update Market Data →** open the latest run → expand
   **Fetch market data**. Each indicator logs `live` with its value, or
   `UNAVAILABLE` with the specific error (timeout, HTTP error, missing
   `FRED_API_KEY`, unexpected response shape, etc).
2. On the dashboard itself, any card showing **"—"** displays the same
   error message in small type at the bottom of the card.
3. `SAHMREALTIME` and `UNRATE` are monthly series — a "stale" date of a few
   weeks is normal and expected, not a broken feed. The date shown on each
   card is FRED's own observation date, so you can tell the difference at a
   glance.

## Calibration status

The scoring thresholds in `fetch_data.py` (`score_indicator`,
`classify_regime`) are a first-pass placeholder, intentionally simple.
Per the original design goal, the priority for V5 was a **reliable data
pipeline** first. Once Data Health is consistently at (or near) full
live status, the next step is to inspect real live values across a range of
market conditions and calibrate the regime thresholds — including making
sure the model correctly distinguishes a **soft landing** (elevated but
stable levels, no adverse trend) from genuine **recession risk** (Sahm Rule
triggering, unemployment trending up, credit spreads widening, curve
dynamics turning) rather than flagging every elevated reading as "Stress."

This dashboard is a transparent decision-support tool, not an automated
trading system — always sanity-check the regime call against your own
judgment.
