# Deployment Guide — ultimate-trader-for-crypto

## Current Verdict

**REGIME_SPECIFIC_EDGE**

Edge confirmed for BTCUSDT (15m, 30m) and SOLUSDT (15m) with risk control
`consecutive_loss_cap=6`. Fails for ETH, XRP, BNB and other altcoins.
Not safe for live deployment yet.

## Allowed Configs (only these may run)

| Symbol   | Timeframe | Phase 7 Trades | EV      | PF    | DD     |
|----------|-----------|----------------|---------|-------|--------|
| BTCUSDT  | 15m       | 34             | +0.82R  | 2.41  | 5.92R  |
| BTCUSDT  | 30m       | 25             | +1.24R  | 3.73  | 5.56R  |
| SOLUSDT  | 15m       | 36             | +0.98R  | 2.84  | 7.74R  |

## Blocked Configs

- ETHUSDT 15m — PF 1.22 < 1.5
- XRPUSDT 15m — PF 1.36 < 1.5
- BNBUSDT 15m — EV -0.09R < 0, KILL triggered
- BTCUSDT 1h — insufficient trades (5)
- BTCUSDT 5m — insufficient data (0 trades)

## Status

- **Live trading:** DISABLED (config_locked.yaml: live_trading: false)
- **Paper trading:** DISABLED (config_locked.yaml: paper_trading: false)
- **Mode:** DRY_RUN only

## Why Live and Paper Trading Remain Disabled

1. **Insufficient trades** — 95 total across 3 allowed configs, below the 100
   minimum evidence gate. More walk-forward windows needed.
2. **Regime-specific edge** — works for BTC and SOL only. Fails for ETH,
   XRP, BNB. Live deployment requires broader market coverage.
3. **No paper data** — 0 days, 0 trades on paper. Paper trading must run
   for 30+ days with 25+ trades before live can be considered.
4. **Hard-blocked in code** — config_locked.yaml sets live/paper=false,
   launch_check.py blocks any flip, validation_gate.py hardcodes
   eligible_for_live_trading=False.

## Daily Operating Procedure

### 1. Pull latest repo
```
git pull
```

### 2. Run operator
```
python production_replay/operator.py
```
This single command runs safety lock, launch check, dry-forward,
evidence tracker, generates all reports, and prints the final status table.

Alternatively double-click `run_operator.bat` (Windows).

### 3. Inspect generated files

| File | What to check |
|------|---------------|
| `deploy_results/operator_summary.txt` | Full session summary (all steps) |
| `deploy_results/dry_forward_report.json` | Verdict, gates, per-config metrics |
| `deploy_results/dry_forward_report.txt` | Human-readable text report |
| `deploy_results/BTCUSDT_15m/forward_test_result.json` | BTC 15m individual trades |
| `deploy_results/BTCUSDT_30m/forward_test_result.json` | BTC 30m individual trades |
| `deploy_results/SOLUSDT_15m/forward_test_result.json` | SOL 15m individual trades |

### 4. Do not enable paper/live trading until gates pass

The operator blocks itself if safety locks are compromised. Do not
manually override config_locked.yaml or launch_check.py.

### 5. Required unlock conditions for paper trading

All must be true:
- >= 100 valid dry-forward trades
- >= 30 calendar days of dry-forward logs
- No kill-switch trigger
- PF >= 1.5
- WR >= 35%
- DD < 12.0R
- Bias audit pass

## Interpreting Results

| Output | Meaning |
|--------|---------|
| **PASS** (launch_check) | All deployment safety gates pass |
| **BLOCKED** (launch_check) | One or more safety gates failed. See which gate. |
| **OK** (kill switch) | No kill conditions triggered (DD < 12R, PF > 1.2, WR > 35%) |
| **KILL** (kill switch) | Kill switch triggered. Stop and investigate. |
| **ROBUST_EDGE** | All gates pass, DD < 8R. Ready for paper consideration. |
| **REGIME_SPECIFIC_EDGE** | Edge for some configs, fails for others. Needs more data. |
| **INSUFFICIENT_TRADES** | < 100 total OOS trades. Continue collecting data. |
| **NO_EDGE** | EV <= 0 or PF < 1.5 or DD >= 12R. Strategy not viable. |

## Commands

### Run daily operator (recommended)
```
python production_replay/operator.py
```
Outputs: `deploy_results/dry_forward_report.json`,
`deploy_results/dry_forward_report.txt`,
`deploy_results/operator_summary.txt`

### Run individual checks (debugging)

```
python production_replay/safety_lock.py           # verify locks engaged
python production_replay/launch_check.py          # check all 8 gates
python production_replay/run_dry_forward.py       # run dry-forward only
python production_replay/evidence_tracker.py      # check evidence status
```

### Run full test suite
```
python -m pytest tests/ -v
```

## Gates Required Before Paper Trading

1. **Evidence:** >= 100 OOS trades across allowed configs (combined)
2. **DD:** < 8.0R preferred, < 12.0R absolute for all allowed configs
3. **PF:** >= 1.5 for all allowed configs
4. **EV:** > 0 for all allowed configs
5. **Kill switch:** not triggered
6. **Git tree:** clean
7. **Bias audit:** PASS
8. **Launch check:** PASS

## Gates Required Before Live Trading

1. All paper-trading gates above
2. >= 30 calendar days of paper-trading results
3. >= 25 paper trades
4. Paper PF >= 1.2
5. Paper WR >= 35%
6. Paper DD <= 10.0R
7. Minimum evidence rule: PASS (Gate A + Gate B + Gate C)
8. Phase 5/7 re-validation on paper data

## Configuration

Locked in `production_replay/config_locked.yaml`:
- stop_method: atr14_20
- entry_method: immediate
- regime_gate: enabled
- risk_control: consecutive_loss_cap at max_losses=6
- live_trading: false
- paper_trading: false
- dry_run: true

## Risk Control

`consecutive_loss_cap(max_losses=6)` — stops trading for the rest of the
day after 6 consecutive losses. This was the only risk control that
meaningfully reduced cumulative DD (14.47R -> 5.92R on BTC 15m) without
destroying EV or PF.
