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

## Commands

### Run dry-forward validation (daily)
```
python production_replay/run_dry_forward.py
```
Output: `deploy_results/dry_forward_report.json`

### Run launch check (before any config change)
```
python production_replay/launch_check.py
```
Blocks deployment if: live/paper enabled, dry_run disabled, blocked
configs active, dirty git tree, missing report, or failed bias audit.

### Run full validation suite
```
python -m pytest tests/test_production_replay.py tests/test_lockdown.py -v
```

## Gates Required Before Paper Trading

1. **Evidence:** ≥100 OOS trades across allowed configs (combined)
2. **DD:** < 8.0R preferred, < 12.0R absolute for all allowed configs
3. **PF:** ≥ 1.5 for all allowed configs
4. **EV:** > 0 for all allowed configs
5. **Kill switch:** not triggered
6. **Git tree:** clean
7. **Bias audit:** PASS
8. **Launch check:** PASS

## Gates Required Before Live Trading

1. All paper-trading gates above
2. ≥30 calendar days of paper-trading results
3. ≥25 paper trades
4. Paper PF ≥ 1.2
5. Paper WR ≥ 35%
6. Paper DD ≤ 10.0R
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
meaningfully reduced cumulative DD (14.47R → 5.92R on BTC 15m) without
destroying EV or PF.
