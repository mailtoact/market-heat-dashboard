# Market Heat Dashboard — Final V2

A self-hosted, iPhone-friendly macro dashboard designed to answer:

> Is the market moving toward Goldilocks, inflation/overheating, slowdown, or recession/financial stress?

## Indicators

### Headline buckets
- Inflation / oil
- Rates / term premium
- Labor / recession
- Credit stress
- USD / liquidity

### Underlying data
- WTI crude
- 2Y Treasury
- 10Y Treasury
- 20Y Treasury
- 30Y Treasury
- 10Y–2Y spread
- 30Y–10Y spread
- Unemployment
- Sahm Rule
- HY credit spread
- IG credit spread
- DXY

## What changed from V1

- 0–100 Market Heat Score
- Five bucket scores
- Level + 30-day direction logic
- Explicit credit/labor weighting
- Sahm Rule
- Yield-curve context
- DXY liquidity context
- "What changed?" warning cards
- Qualitative portfolio posture
- 90-day sparklines
- iPhone PWA manifest and icon
- Hourly automated data refresh
- GitHub Pages automatic deployment
- No API key required for the included data sources

## Deploy on GitHub Pages

1. Create a GitHub repository named `market-heat-dashboard`.
2. Upload the contents of this folder to the repository root.
3. Make sure the default branch is `main`.
4. In **Settings → Pages**, set **Source** to **GitHub Actions**.
5. Go to **Actions** and run **Update market data** once.
6. The deployment workflow will publish the site.
7. Open the published URL in Safari on iPhone.
8. Tap **Share → Add to Home Screen**.

GitHub's official documentation confirms that Pages can publish static files from a repository and that custom Actions workflows can deploy Pages artifacts.

## Important implementation detail

The data update workflow commits `data.json` back to the repository. The Pages deployment workflow is separate. This avoids relying on a Pages build being triggered by the bot's data commit.

## Scoring philosophy

The score is a transparent monitoring heuristic, not a predictive model.

- Credit and labor receive the largest weights because deterioration there is more useful for identifying recession/financial stress than a high oil price alone.
- Rates focus on the 10Y/30Y long end.
- Oil emphasizes both level and recent acceleration.
- DXY is treated as a liquidity/context signal rather than "strong dollar = bad".
- The Sahm Rule is displayed separately and contributes to the labor bucket.

Thresholds are intentionally easy to edit in `fetch_data.py`.

## Data sources

FRED:
- DGS2
- DGS10
- DGS20
- DGS30
- DCOILWTICO
- UNRATE
- BAMLH0A0HYM2
- BAMLC0A0CM

DXY:
- Yahoo Finance `DX-Y.NYB`

## Disclaimer

This dashboard is for informational and educational purposes only. It is not investment advice, a market-timing system, or a guarantee of future returns. Economic data can be revised and financial-market data can be delayed.
