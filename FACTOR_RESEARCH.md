# Factor Research — 2026-07-04 Session

Honest re-validation of the breadwinner strategy space plus a first pass at
cross-sectional (portfolio-style) factors on longer history. All numbers are
net of taker fees (0.05%/side) with real funding history applied where
available. No orders were placed; live/paper trading remain disabled.

## Part 1 — Intraday candle strategies: no edge (conclusive)

Data: 150 highest-volume BingX USDT perps, 120–180 days of 15m/30m/1h
candles (~2.19M simulated trades, 104 strategy variants).

Methodology bugs fixed first (see commit `9debbc5`): the phase 75–78 engines
split in-sample/out-of-sample by **entry price** (or symbol name), not time;
scored promotion gates on **pre-fee** R; and allowed overlapping trades.
Measured inflation from those bugs: **+0.09R per trade average OOS avg R
(max +0.42R)** on identical data.

Results under honest validation (true time split, net of fees, no overlap):

| Metric | Value |
|---|---|
| Variants with positive OOS avg R | 0 / 104 |
| Variants with profit factor > 1.0 | 0 / 104 |
| Best variant (funding_trap_proxy 15m RR2) | −0.027R/trade, PF 0.86 |
| Flagship LSRv2 (all 6 variants) | −0.10 to −0.17R/trade, all REJECTED |

Conclusion: classic price-action archetypes (sweep reversal, breakout
retest, trend pullback, mean reversion, funding proxy) on OHLCV candles at
15m–1h have no edge after fees on this universe. Further parameter mining in
this space is re-fitting noise.

## Part 2 — Cross-sectional factors on ~2.6 years of daily data

Data: `scripts/download_factor_data.py` (daily candles ~964 trading days,
funding history ~333 days, 148 symbols). Lab: `scripts/factor_lab.py`,
report: `deploy_results/factor_lab_report.json`.

Daily-rebalanced long/short decile portfolios (15 per side, half gross per
leg), signal strictly prior to entry, fees on actual turnover:

| Factor | Ann. ret | Sharpe | Max DD | IS/OOS Sharpe | +months |
|---|---|---|---|---|---|
| momentum_30d | +39% | 0.93 | 41% | 1.15 / 0.64 | 20/33 |
| momentum_30d, 1-day lag | +27% | 0.63 | 37% | 0.87 / 0.35 | 17/33 |
| momentum_30d, top-50 only | +19% | 0.46 | 42% | −0.13 / 2.09 | 11/20 |
| momentum_7d | +29% | 0.66 | 36% | 0.54 / 0.87 | 15/34 |
| reversal_2d / 5d | −47% / −39% | −1.6 / −1.4 | — | both negative | — |
| funding_crowding (short high funding) | −44% | −1.6 | — | both negative | — |

Reading:

- **30-day cross-sectional momentum is the only positive result**, and it is
  consistent with published crypto-momentum research. It survives a 1-day
  execution lag (edge is not microstructure noise) and both IS and OOS
  periods are positive on the full universe.
- **It is materially inflated by survivorship bias**: the universe is
  today's listings, so dead coins are missing and the long leg looks better
  than reality. The long-leg-only number (+178% ann.) is mostly this bias —
  do not trust it. The tradable truth is likely well below the headline.
- **The short leg loses money on its own** (−31% ann.); its role is hedging
  the long leg, not alpha.
- **Risk is heavy**: ~40% max drawdown against ~0.6–0.9 Sharpe. This is an
  investment-style factor allocation, not an income strategy.
- Short-term reversal and the funding-crowding short are strongly negative —
  crossed off.

## What this is NOT

This is not a validated trading system and not income. Before risking even
paper capital on momentum, it needs: delisting-aware universe data, a
slippage model for the small-cap legs, at least a full bear-market cycle of
history, and the same forward dry-run evidence discipline the rest of this
repo enforces.

## Reproduce

```
python scripts/download_factor_data.py
python scripts/factor_lab.py
cat deploy_results/factor_lab_report.json
```
