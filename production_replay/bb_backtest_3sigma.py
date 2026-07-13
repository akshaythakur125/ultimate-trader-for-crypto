"""BB Bounce v1 backtest - 3.0 sigma with $3M+ mcap/liquidity filter.

Reads cached 1h candles from runtime_state/candles_cache/.
Uses ccxt BingX to fetch market cap data for filtering.
Simulates BB Bounce v1 trades with std_mult=3.0.
"""
import json, os, sys, time
from datetime import datetime, timezone
from random import Random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from production_replay.breadwinner_strategy_library import detect_bb_bounce, simulate_trade

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")

BB_PERIOD = 15
BB_STD_MULT = 3.0
BB_RR_TARGET = 10.0
BB_MIN_ENTRY_VOL_RATIO = 1.5
RISK_PCT = 0.005
MIN_MCAPPING_USDT = 3_000_000
CAPITAL = 20.0
RISK_PER_TRADE = 1.0
MAX_TRADES = 3
MAX_HOLDING = 48

rng = Random(42)


def load_cached(cache_sym):
    path = os.path.join(CACHE_DIR, f"{cache_sym}_1h.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def get_market_caps():
    """Fetch market caps from BingX tickers to filter by $3M+."""
    import ccxt
    ex = ccxt.bingx()
    ex.load_markets()
    
    print("Fetching market data for mcap filtering...")
    tickers = ex.fetch_tickers()
    
    mcap_map = {}
    for sym, ticker in tickers.items():
        if not sym.endswith("/USDT"):
            continue
        base = sym.replace("/USDT", "")
        
        info = ticker.get("info", {})
        quote_vol = float(info.get("quoteVolume") or 0)
        
        mcap_proxy = quote_vol * 24
        last_price = float(info.get("lastPrice") or ticker.get("last") or 0)
        
        mcap_map[base] = {
            "mcap_proxy": mcap_proxy,
            "last_price": last_price,
            "quote_vol_24h": quote_vol,
        }
    
    return mcap_map, ex.markets


def run_backtest():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    mcap_data, markets = get_market_caps()
    
    cache_files = [f.replace("_1h.json", "") for f in os.listdir(CACHE_DIR) if f.endswith("_1h.json")]
    print(f"Found {len(cache_files)} symbols in cache")
    
    eligible_syms = []
    filtered_syms = []
    for cs in cache_files:
        lookup_key = cs.replace("_USDT", "")
        info = mcap_data.get(lookup_key, {})
        mcap = info.get("mcap_proxy", 0)
        if mcap >= MIN_MCAPPING_USDT:
            eligible_syms.append(cs)
        else:
            filtered_syms.append(cs)
    
    print(f"Eligible ($3M+ mcap): {len(eligible_syms)}")
    print(f"Filtered out: {len(filtered_syms)}")
    
    if filtered_syms:
        sample = rng.sample(filtered_syms, min(5, len(filtered_syms)))
        print(f"  Sample filtered: {', '.join(sample)}")
    
    all_trades = []
    all_signals = []
    symbols_with_signals = 0
    
    for idx, cs in enumerate(eligible_syms):
        candles = load_cached(cs)
        if not candles or len(candles) < BB_PERIOD + 10:
            continue
        
        sym_signals = 0
        check_idx = len(candles) - 3
        if check_idx < BB_PERIOD + 5:
            continue
        
        sig = detect_bb_bounce(
            candles, check_idx, period=BB_PERIOD, std_mult=BB_STD_MULT,
            rr_target=BB_RR_TARGET, min_entry_volume_ratio=BB_MIN_ENTRY_VOL_RATIO,
        )
        
        if sig:
            sig["symbol"] = cs
            sig["mcap_proxy"] = mcap_data.get(cs.replace("_USDT", ""), {}).get("mcap_proxy", 0)
            all_signals.append(sig)
            sym_signals += 1
        
        for i in range(BB_PERIOD + 5, len(candles) - 1):
            s = detect_bb_bounce(
                candles, i, period=BB_PERIOD, std_mult=BB_STD_MULT,
                rr_target=BB_RR_TARGET, min_entry_volume_ratio=BB_MIN_ENTRY_VOL_RATIO,
            )
            if s:
                s["symbol"] = cs
                s["mcap_proxy"] = mcap_data.get(cs.replace("_USDT", ""), {}).get("mcap_proxy", 0)
                all_signals.append(s)
                sym_signals += 1
        
        if sym_signals > 0:
            symbols_with_signals += 1
        
        if (idx + 1) % 50 == 0:
            print(f"  [{idx+1}/{len(eligible_syms)}] {len(all_signals)} signals so far...")
    
    print(f"\nTotal signals found: {len(all_signals)}")
    print(f"Symbols with signals: {symbols_with_signals}")
    
    if not all_signals:
        print("\nNo signals found with 3.0 sigma + $3M+ mcap filter.")
        return
    
    trade_results = []
    for sig in all_signals:
        cs = sig["symbol"]
        candles = load_cached(cs)
        if not candles:
            continue
        
        entry_idx = None
        for i in range(len(candles) - 1, -1, -1):
            if abs(float(candles[i].get("close", 0)) - sig["entry"]) < sig["entry"] * 0.001:
                entry_idx = i
                break
        
        if entry_idx is None:
            entry_idx = sig.get("candle_idx", len(candles) - 3)
        
        if entry_idx >= len(candles) - 1:
            continue
        
        result = simulate_trade(
            candles, entry_idx, sig["direction"],
            sig["entry"], sig["stop"], sig["target"],
            max_holding=MAX_HOLDING,
        )
        
        result["symbol"] = cs
        result["direction"] = sig["direction"]
        result["entry"] = sig["entry"]
        result["stop"] = sig["stop"]
        result["target"] = sig["target"]
        result["mcap_proxy"] = sig.get("mcap_proxy", 0)
        result["entry_volume_ratio"] = sig.get("entry_volume_ratio", 0)
        
        trade_results.append(result)
    
    if not trade_results:
        print("\nNo trades simulated.")
        return
    
    wins = [t for t in trade_results if t["r_result"] > 0]
    losses = [t for t in trade_results if t["r_result"] < 0]
    breakeven = [t for t in trade_results if t["r_result"] == 0]
    
    win_rate = len(wins) / len(trade_results) if trade_results else 0
    avg_r = sum(t["r_result"] for t in trade_results) / len(trade_results) if trade_results else 0
    avg_win_r = sum(t["r_result"] for t in wins) / len(wins) if wins else 0
    avg_loss_r = sum(t["r_result"] for t in losses) / len(losses) if losses else 0
    
    gross_profit = sum(t["r_result"] * RISK_PER_TRADE for t in wins)
    gross_loss = abs(sum(t["r_result"] * RISK_PER_TRADE for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    
    max_dd = 0
    peak = 0
    equity = CAPITAL
    for t in sorted(trade_results, key=lambda x: x.get("exit_idx", 0)):
        equity += t["r_result"] * RISK_PER_TRADE
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    
    target_hits = len([t for t in trade_results if t["outcome"] == "TARGET_HIT"])
    stop_hits = len([t for t in trade_results if t["outcome"] == "STOP_HIT"])
    expired = len([t for t in trade_results if t["outcome"] == "EXPIRED"])
    
    avg_holding = sum(t.get("holding", 0) for t in trade_results) / len(trade_results)
    
    long_signals = len([s for s in all_signals if s["direction"] == "LONG"])
    short_signals = len([s for s in all_signals if s["direction"] == "SHORT"])
    
    long_trades = [t for t in trade_results if t["direction"] == "LONG"]
    short_trades = [t for t in trade_results if t["direction"] == "SHORT"]
    
    long_wr = len([t for t in long_trades if t["r_result"] > 0]) / len(long_trades) if long_trades else 0
    short_wr = len([t for t in short_trades if t["r_result"] > 0]) / len(short_trades) if short_trades else 0
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "bb_period": BB_PERIOD,
            "bb_std_mult": BB_STD_MULT,
            "bb_rr_target": BB_RR_TARGET,
            "min_entry_vol_ratio": BB_MIN_ENTRY_VOL_RATIO,
            "risk_pct": RISK_PCT,
            "min_mcap_usdt": MIN_MCAPPING_USDT,
            "capital": CAPITAL,
            "risk_per_trade": RISK_PER_TRADE,
            "max_holding": 0,
        },
        "universe": {
            "total_cached": len(cache_files),
            "eligible": len(eligible_syms),
            "filtered_out": len(filtered_syms),
        },
        "signals": {
            "total": len(all_signals),
            "long": long_signals,
            "short": short_signals,
            "symbols_with_signals": symbols_with_signals,
        },
        "trades": {
            "total": len(trade_results),
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(breakeven),
        },
        "performance": {
            "win_rate": round(win_rate, 4),
            "avg_r": round(avg_r, 4),
            "avg_win_r": round(avg_win_r, 4),
            "avg_loss_r": round(avg_loss_r, 4),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown_usdt": round(max_dd, 2),
            "total_pnl_r": round(sum(t["r_result"] for t in trade_results), 4),
            "total_pnl_usdt": round(sum(t["r_result"] * RISK_PER_TRADE for t in trade_results), 2),
            "avg_holding_candles": round(avg_holding, 1),
        },
        "outcomes": {
            "target_hits": target_hits,
            "stop_hits": stop_hits,
            "expired": expired,
        },
        "direction_breakdown": {
            "long": {"trades": len(long_trades), "win_rate": round(long_wr, 4)},
            "short": {"trades": len(short_trades), "win_rate": round(short_wr, 4)},
        },
        "top_trades": sorted(
            [{"symbol": t["symbol"], "direction": t["direction"], "r": t["r_result"], "outcome": t["outcome"]}
             for t in trade_results],
            key=lambda x: x["r"], reverse=True,
        )[:10],
        "worst_trades": sorted(
            [{"symbol": t["symbol"], "direction": t["direction"], "r": t["r_result"], "outcome": t["outcome"]}
             for t in trade_results],
            key=lambda x: x["r"],
        )[:10],
    }
    
    with open(os.path.join(RESULTS_DIR, "bb_backtest_3sigma.json"), "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"  BB BOUNCE v1 BACKTEST - 3.0 sigma + $3M+ LIQUIDITY FILTER")
    print(f"{'='*70}")
    print(f"\n  Universe: {len(eligible_syms)} eligible / {len(cache_files)} total cached")
    print(f"  Filter:   ${MIN_MCAPPING_USDT:,.0f}+ 24h volume proxy")
    print(f"\n  Config:   period={BB_PERIOD}  sigma={BB_STD_MULT}  RR=1:{BB_RR_TARGET:.0f}")
    print(f"            stop={RISK_PCT*100:.1f}%  vol_filter={BB_MIN_ENTRY_VOL_RATIO}x  max_hold=none")
    print(f"\n  Signals:  {len(all_signals)} ({long_signals} LONG / {short_signals} SHORT)")
    print(f"  Symbols:  {symbols_with_signals} with signals out of {len(eligible_syms)} eligible")
    print(f"\n  Trades:   {len(trade_results)} total ({len(wins)} W / {len(losses)} L / {len(breakeven) } BE)")
    print(f"  Win Rate: {win_rate*100:.1f}%")
    print(f"  Avg R:    {avg_r:+.2f}R")
    print(f"  Avg Win:  {avg_win_r:+.2f}R  |  Avg Loss: {avg_loss_r:.2f}R")
    print(f"  PF:       {profit_factor:.2f}")
    print(f"  Total:    {sum(t['r_result'] for t in trade_results):+.2f}R  (${sum(t['r_result'] * RISK_PER_TRADE for t in trade_results):+.2f})")
    print(f"  Max DD:   ${max_dd:.2f}")
    print(f"  Hold:     {avg_holding:.1f} candles avg")
    print(f"\n  Outcomes: {target_hits} target / {stop_hits} stop / {expired} expired")
    print(f"  LONG WR:  {long_wr*100:.1f}% ({len(long_trades)} trades)")
    print(f"  SHORT WR: {short_wr*100:.1f}% ({len(short_trades)} trades)")
    print(f"\n  Top 5:")
    for t in report["top_trades"][:5]:
        print(f"    {t['symbol']:20s} {t['direction']:5s} {t['r']:+.2f}R  {t['outcome']}")
    print(f"\n  Worst 5:")
    for t in report["worst_trades"][:5]:
        print(f"    {t['symbol']:20s} {t['direction']:5s} {t['r']:+.2f}R  {t['outcome']}")
    print(f"\n  Report: {RESULTS_DIR}/bb_backtest_3sigma.json")
    
    return report


if __name__ == "__main__":
    run_backtest()
