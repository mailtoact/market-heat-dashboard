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

Data Health confirmed 11/11 live, so thresholds have had a first calibration
pass against real observed values (Aug 2026: WTI ~$82, 2Y ~4.2%, 10Y ~4.65%,
30Y ~5.2%, 10Y-2Y +0.47pp, unemployment 4.1%, Sahm -0.03, HY spread 2.7pp,
IG spread 0.78pp, DXY ~99.8). Level bounds in `score_indicator()` are now
anchored to real historical cycle ranges (e.g. HY spread 2.5pp tight-extreme
to 9pp broad-stress; 10Y-2Y -2.0pp deep-inversion floor to +1.2pp
steep-expansion ceiling) rather than arbitrary round numbers — see the
inline comments next to each indicator for the specific anchors and
reasoning. With today's tight credit spreads, sub-trigger Sahm Rule, and a
positively-sloped curve, the model correctly reads "Low Heat" rather than
flagging elevated *nominal* yield levels as stress.

**Two known display/logic fixes already applied in this pass:**
- Percentage-point series that hover near zero (Sahm Rule, 10Y-2Y spread)
  now display point change (`+0.02pp`) instead of percentage change, which
  was producing misleading numbers like "-111%" on tiny moves near zero.
  HY/IG spreads and 10Y-2Y also use `pp` display since they're naturally
  point-denominated; yields, oil, and DXY keep `%` since those series don't
  approach zero.
- Trend lookback is now frequency-aware: 5 observations (~1 trading week)
  for daily series, 3 observations (~3 months) for monthly series
  (unemployment, Sahm Rule), instead of a flat 15-observation window that
  made "trend" mean "vs. over a year ago" for the monthly series.

**Still open for a future pass**, once more market regimes have been
observed live:
- Stress-tested against a benign/low-heat environment only so far — the
  "High Heat" and "Stress" thresholds haven't yet been checked against a
  real overheating or credit-stress episode. Worth revisiting `wti`,
  `hy_spread`, and the regime cutoffs in `classify_regime()` next time
  conditions shift.
- The 20Y yield sitting slightly above the 30Y yield is a real, known
  liquidity quirk in that note (not a data error) — worth keeping in mind
  if the two ever diverge more sharply.

This dashboard is a transparent decision-support tool, not an automated
trading system — always sanity-check the regime call against your own
judgment.
