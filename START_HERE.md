# Start Here — ultimate-trader-for-crypto

## Current Status

The system is in **DRY-RUN mode only**. It runs historical simulations
(walk-forward validation) across 3 allowed configs:
- BTCUSDT 15m (34 trades, EV +0.82R, PF 2.41, DD 5.92R)
- BTCUSDT 30m (25 trades, EV +1.24R, PF 3.73, DD 5.56R)
- SOLUSDT 15m (36 trades, EV +0.98R, PF 2.84, DD 7.74R)

**Combined: 95 trades, verdict INSUFFICIENT_TRADES.**

## Why Live and Paper Trading Are Disabled

1. **Not enough trades** — only 95 total. Need 100+.
2. **Not enough days** — 0 calendar days of dry-forward runs.
3. **Regime-specific edge** — works for BTC/SOL, fails for ETH/XRP/BNB.
4. **Hard-locked in code** — you cannot accidentally enable trading.
   Even if you edit config_locked.yaml, the launch_check will block it.

## Daily Command (one line)

```
python production_replay/operator.py
```

Or double-click `run_operator.bat` (Windows).

This single command runs all checks, generates reports, and prints
a status table. Takes 3-5 minutes.

## Reports

After running the operator, check:

| File | Contents |
|------|----------|
| `deploy_results/operator_summary.txt` | Full session summary |
| `deploy_results/dry_forward_report.json` | Verdict, gates, per-config metrics |
| `deploy_results/dry_forward_report.txt` | Human-readable text report |
| `deploy_results/BTCUSDT_15m/forward_test_result.json` | BTC 15m individual trades |
| `deploy_results/BTCUSDT_30m/forward_test_result.json` | BTC 30m individual trades |
| `deploy_results/SOLUSDT_15m/forward_test_result.json` | SOL 15m individual trades |

## What Must Happen Before Paper Trading Can Be Discussed

All of the following must be true:

- **≥ 100** valid dry-forward trades
- **≥ 30** calendar days of dry-forward runs
- **No kill-switch trigger** in the latest run
- **PF ≥ 1.5** and **WR ≥ 35%** in the latest run
- **DD < 12.0R** in the latest run
- **Bias audit passes**
- **All launch_check gates PASS** for 7 consecutive days

Only after these are met should you consider updating config_locked.yaml
to enable paper_trading. Then re-run launch_check.

## WARNING

**Do not edit config_locked.yaml manually.**

It is the single source of truth for production safety. If you change
it incorrectly, the launch_check will block the operator. If you
force-skip the launch_check, you risk enabling live trading on an
unvalidated strategy.

If you believe a config change is needed, run the full validation
pipeline (Phase 5-7) first.
