# Start Here — ultimate-trader-for-crypto

This system is a **dry-forward evidence collection system only.**
It is NOT deployable for live or paper trading. It is NOT ready
to generate income. Do not use it for real trading.

## Current Status

| Metric | Value |
|--------|-------|
| Mode | DRY_RUN |
| Live trading | DISABLED |
| Paper trading | DISABLED |
| Total trades collected | **95 / 100** |
| Verdict | **INSUFFICIENT_TRADES** |
| Launch check | PASS |
| Safety locks | ALL ENGAGED |
| Tests | 1148 / 1148 PASS |

## Daily Command

```
python -m production_replay.operator
```

Or double-click `run_operator.bat` (Windows). Takes 3-5 minutes.

## Where to Read Results

Open **`deploy_results/operator_summary.txt`** after each run.

It contains:
- Launch check result (PASS / BLOCKED)
- Safety lock status
- Dry-forward verdict and trade count
- Evidence tracker: trades, days, kill switch, unlock status
- Next required action

## Why Live and Paper Trading Are Disabled

1. **95 trades < 100** minimum evidence gate (Gate A)
2. **1 day < 30** calendar day minimum (Gate B)
3. **Regime-specific edge** — works for BTC/SOL, fails for ETH/XRP/BNB
4. **Hard-locked in config** — config_locked.yaml sets live/paper=false
5. **Hard-locked in code** — launch_check.py blocks any flip;
   validation_gate.py hardcodes eligible_for_live_trading=False;
   safety_lock.py scans for forbidden imports

## Unlock Criteria Before Paper Trading

All conditions must be met simultaneously:

| Condition | Target | Current |
|-----------|--------|---------|
| Dry-forward trades | >= 100 | 95 |
| Calendar days logged | >= 30 | 1 |
| Kill switch | NOT triggered | OK |
| Profit factor | >= 1.5 | 2.87 |
| Win rate | >= 35% | 53.7% |
| Drawdown | < 12.0R | 7.74R |
| Expectancy | > 0 | +0.993R |
| Bias audit | PASS | PASS |
| Launch check | PASS (7+ consecutive days) | PASS |

When these are met, run the full paper-trading pipeline (code changes
required outside the operator layer). Do not simply flip config_locked.yaml.

## WARNING

**This system is NOT deployable for income.**

- It only collects evidence through historical simulation
- It does not execute real or paper trades
- Live and paper trading are permanently disabled in code
- Do not attempt to override config_locked.yaml or force-skip launch_check
- If you believe you are ready for paper trading, run the full
  validation pipeline (Phase 5-7) and pass all unlock conditions first

**Do not edit config_locked.yaml manually.**

## Doctor/Busy Operator Mode

Forget the manual checks. Just run one of:

```
python -m production_replay.healthcheck
```

Or (Linux/Mac):

```
bash scripts/doctor_check.sh
```

This runs safety locks, launch check, verifies live/paper disabled, checks for API imports, and reports test status. All in one command.
