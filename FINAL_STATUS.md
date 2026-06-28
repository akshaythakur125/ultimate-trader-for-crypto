# Final Status — ultimate-trader-for-crypto

**Date:** 2026-06-28
**Commit:** `38c4939`
**Branch:** `main`

## Frozen Strategy Configuration

| Parameter | Value |
|-----------|-------|
| stop_method | atr14_20 |
| entry_method | immediate |
| regime_gate | enabled |
| risk_control | consecutive_loss_cap(max_losses=6) |
| live_trading | `false` (hard-locked) |
| paper_trading | `false` (hard-locked) |
| dry_run | `true` (hard-locked) |

## Allowed Configs

| Symbol | Timeframe | Trades | EV(R) | PF | DD(R) | Kill |
|--------|-----------|--------|-------|----|-------|------|
| BTCUSDT | 15m | 34 | +0.822 | 2.41 | 5.92 | OK |
| BTCUSDT | 30m | 25 | +1.241 | 3.73 | 5.56 | OK |
| SOLUSDT | 15m | 36 | +0.982 | 2.84 | 7.74 | OK |

## Blocked Configs (permanently excluded)

ETHUSDT 15m, XRPUSDT 15m, BNBUSDT 15m (KILL), BTCUSDT 1h, BTCUSDT 5m

## Launch Check Status

**PASS** — All 8 gates pass.

| Gate | Status |
|------|--------|
| live_trading_disabled | PASS |
| paper_trading_disabled | PASS |
| dry_run_enabled | PASS |
| no_blocked_configs | PASS |
| report_exists | PASS |
| allowed_configs_valid | PASS |
| git_tree_clean | PASS |
| bias_audit_passed | PASS |

## Test Status

**32/32 tests pass.**

- tests/test_lockdown.py: 12/12 PASS
- tests/test_production_replay.py: 9/9 PASS
- tests/test_validation_gate.py: 6/6 PASS
- tests/test_live_trading_disabled.py: 5/5 PASS

## Live Trading

**DISABLED.** Hard-locked in config_locked.yaml (live_trading: false),
launch_check.py (blocks if enabled), and validation_gate.py:125
(eligible_for_live_trading = False).

## Paper Trading

**DISABLED.** Hard-locked in config_locked.yaml (paper_trading: false)
and launch_check.py (blocks if enabled).

## Evidence Status

**95 total OOS trades** across 3 allowed configs.
**Verdict: INSUFFICIENT_TRADES.**

Not deployable for live or paper because:
1. 95 trades < 100 minimum evidence gate (Gate A)
2. 0 calendar days of paper-trading results (Gate B)
3. Only 3 of 8 tested configs show edge (REGIME_SPECIFIC_EDGE)
4. Live eligibility hard-coded to False in validation_gate.py

---

## Daily Routine

Run this once per day (takes ~5 minutes):

```
python production_replay/run_dry_forward.py
```

Then inspect:
- `deploy_results/dry_forward_report.json` — consolidated verdict, gates, per-config metrics
- `deploy_results/BTCUSDT_15m/forward_test_result.json` — individual trades
- `deploy_results/BTCUSDT_30m/forward_test_result.json`
- `deploy_results/SOLUSDT_15m/forward_test_result.json`

Record:
- Total trades and per-config counts
- Rejection counts per config
- Kill-switch status (OK / KILL — if KILL, stop and investigate)
- Minimum evidence gate status
- Any anomalies in trade PnL, DD, or WR trends

Do NOT manually execute trades from this system. The system is in
dry-run mode only — no orders are placed.

---

## Paper Trading Unlock Conditions

All of the following must be true before paper_trading can be set to `true`
in config_locked.yaml (the launch_check must also be updated):

1. **≥ 100 total dry-forward trades** (combined across all allowed configs)
2. **≥ 30 calendar days** of dry-forward logs (daily runs with reports)
3. **No kill-switch trigger** in the most recent run
4. **Cumulative DD < 12.0R** in the most recent run
5. **PF ≥ 1.5** and **WR ≥ 35%** in the most recent run
6. **No bias-audit failures** in the most recent run
7. **Phase 5 re-validation** against paper data (not just historical)
8. **All launch_check gates PASS** consistently for 7 consecutive days

When these are met, update config_locked.yaml (paper_trading: true) and
run launch_check before enabling the paper trading path.

---

## Command to Run Tomorrow

```
python production_replay/run_dry_forward.py
```
