# Live Micro Runbook

How to run the strategy live on the VM, and what was fixed to make orders
actually go through. Risk stays capped at the values in the executor
(default `MAX_RISK_PER_TRADE_USDT=1`, `MAX_DAILY_LOSS_USDT=2`, one position at
a time). Start at micro size, prove the plumbing on a single order, then scale.

## Bugs fixed (why orders were not going through)

| # | File | Bug | Effect |
|---|------|-----|--------|
| 1 | `bingx_live_micro_executor.py` | Order params sent as JSON body while the signature was computed over the query string | BingX rejected **every** order on signature mismatch |
| 2 | `bingx_live_micro_executor.py` | On stop-loss failure it tried to *cancel* a filled MARKET entry | Left a **naked position** with no stop |
| 3 | `bingx_live_micro_executor.py` | Stop/TP orders had no `reduceOnly` | A triggered exit could open an opposite position |
| 4 | `safety_lock.py` | `import ccxt` in a read-only data fetcher failed the whole lock | Blocked `operator.py` (dies at step 1) **and** the executor's safety gate |
| 5 | `bingx_shadow_executor.py` | `UnboundLocalError: risk_usdt` on every no-trade cycle | The order intent was never written, so nothing downstream could fire |
| 6 | `hourly_alert.py` | `subprocess` used before import | First refresh step silently skipped |
| 7 | `breadwinner_daily_report.py` | Undefined `final_decision` | Report crashed |

`pyflakes` now reports zero undefined-name / use-before-assignment errors in
`production_replay/`, and `safety_lock` passes.

## Not verified from here

I cannot reach the live BingX API from this environment, so the **order
placement itself is not end-to-end tested against BingX**. The code path,
signing, payloads, and gate chain are correct and run clean in dry mode. You
must confirm the first real order manually (next section) before trusting the
loop.

## One-time setup on the VM

```bash
cd ~/ultimate-trader-for-crypto
pip install -r requirements.txt
export BINGX_API_KEY=...            # your BingX API key (futures enabled)
export BINGX_API_SECRET=...
```

Make sure your BingX account is in **one-way** position mode and the symbols
you trade have leverage set to <= 2x. Keep credentials in the environment or a
`.env` you do not commit.

## Step 1 — refresh the daily safety context

The shadow gate needs a fresh `doctor_daily_packet.json`. Run once a day:

```bash
python -m production_replay.operator
```

## Step 2 — prove ONE real order manually (do this first)

```bash
export BINGX_EXECUTION_MODE=live_micro
export LIVE_TRADING_ACK=I_UNDERSTAND_THIS_CAN_LOSE_MONEY
python -m production_replay.live_auto_loop --once
```

- If it prints `EXECUTED — ... placed with stop + target`, check BingX: you
  should see the position **plus** an attached stop-loss and take-profit.
- If it prints `EXECUTOR_DO_NOT_EXECUTE — <reason>`, the reason names the gate
  that blocked (no signal, preflight, risk, etc.). No order was placed.
- If the entry filled but the stop could not be placed, the executor now
  **flattens** the position and logs `CRITICAL: NAKED POSITION` — if you ever
  see that, close the position on BingX immediately and stop.

## Step 3 — full automation

Once a single manual order behaves correctly:

```bash
export BINGX_EXECUTION_MODE=live_micro
export LIVE_TRADING_ACK=I_UNDERSTAND_THIS_CAN_LOSE_MONEY
python -m production_replay.live_auto_loop --interval 60
```

Run it under `tmux`/`screen` or `systemd` so it survives SSH disconnects. It
pursues a new entry only while the account is flat, so at most one position is
open at a time. To pause all new entries without killing the process:

```bash
python -m production_replay.kill_switch_on     # stop new entries
python -m production_replay.kill_switch_off     # resume
```

Leave `python -m production_replay.operator` on a daily cron to keep the safety
context fresh.

## Stopping

`Ctrl-C` stops the loop. Open positions are left as-is (their stop/target stay
on the exchange) — close them on BingX if you want out.
