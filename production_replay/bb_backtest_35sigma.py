"""BB Bounce v1 backtest - 3.5 sigma with $3M+ mcap/liquidity filter for comparison."""
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from production_replay.breadwinner_strategy_library import detect_bb_bounce, simulate_trade

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state", "candles_cache")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")

BB_PERIOD = 15
BB_STD_MULT = 3.5
BB_RR_TARGET = 10.0
BB_MIN_ENTRY_VOL_RATIO = 1.5
RISK_PCT = 0.005
MIN_MCAPPING_USDT = 3_000_000
CAPITAL = 20.0
RISK_PER_TRADE = 1.0
MAX_HOLDING = 48


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
    import ccxt
    ex = ccxt.bingx()
    ex.load_markets()
    tickers = ex.fetch_tickers()
    mcap_map = {}
    for sym, ticker in tickers.items():
        if not sym.endswith("/USDT"):
            continue
        base = sym.replace("/USDT", "")
        info = ticker.get("info", {})
        quote_vol = float(info.get("quoteVolume") or 0)
        mcap_map[base] = {"mcap_proxy": quote_vol * 24}
    return mcap_map


def run_backtest():
    mcap_data = get_market_caps()
    cache_files = [f.replace("_1h.json", "") for f in os.listdir(CACHE_DIR) if f.endswith("_1h.json")]

    eligible_syms = [cs for cs in cache_files if mcap_data.get(cs.replace("_USDT", ""), {}).get("mcap_proxy", 0) >= MIN_MCAPPING_USDT]

    all_signals = []
    for cs in eligible_syms:
        candles = load_cached(cs)
        if not candles or len(candles) < BB_PERIOD + 10:
            continue
        for i in range(BB_PERIOD + 5, len(candles) - 1):
            s = detect_bb_bounce(candles, i, period=BB_PERIOD, std_mult=BB_STD_MULT,
                                 rr_target=BB_RR_TARGET, min_entry_volume_ratio=BB_MIN_ENTRY_VOL_RATIO)
            if s:
                s["symbol"] = cs
                all_signals.append(s)

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
        result = simulate_trade(candles, entry_idx, sig["direction"],
                                sig["entry"], sig["stop"], sig["target"], max_holding=MAX_HOLDING)
        result["symbol"] = cs
        result["direction"] = sig["direction"]
        trade_results.append(result)

    wins = [t for t in trade_results if t["r_result"] > 0]
    losses = [t for t in trade_results if t["r_result"] < 0]
    win_rate = len(wins) / len(trade_results) if trade_results else 0
    avg_r = sum(t["r_result"] for t in trade_results) / len(trade_results) if trade_results else 0
    avg_win_r = sum(t["r_result"] for t in wins) / len(wins) if wins else 0
    avg_loss_r = sum(t["r_result"] for t in losses) / len(losses) if losses else 0
    gross_profit = sum(t["r_result"] * RISK_PER_TRADE for t in wins)
    gross_loss = abs(sum(t["r_result"] * RISK_PER_TRADE for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    long_trades = [t for t in trade_results if t["direction"] == "LONG"]
    short_trades = [t for t in trade_results if t["direction"] == "SHORT"]
    long_wr = len([t for t in long_trades if t["r_result"] > 0]) / len(long_trades) if long_trades else 0
    short_wr = len([t for t in short_trades if t["r_result"] > 0]) / len(short_trades) if short_trades else 0

    print(f"  BB 3.5 sigma: {len(trade_results)} trades  WR={win_rate*100:.1f}%  AvgR={avg_r:+.2f}  PF={pf:.2f}  Total={sum(t['r_result'] for t in trade_results):+.2f}R  LONG_WR={long_wr*100:.1f}%  SHORT_WR={short_wr*100:.1f}%")

    return {
        "sigma": 3.5,
        "trades": len(trade_results),
        "win_rate": round(win_rate, 4),
        "avg_r": round(avg_r, 4),
        "avg_win_r": round(avg_win_r, 4),
        "avg_loss_r": round(avg_loss_r, 4),
        "profit_factor": round(pf, 2),
        "total_r": round(sum(t["r_result"] for t in trade_results), 4),
        "long_wr": round(long_wr, 4),
        "short_wr": round(short_wr, 4),
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
    }


if __name__ == "__main__":
    r = run_backtest()
    with open(os.path.join(RESULTS_DIR, "bb_backtest_35sigma.json"), "w") as f:
        json.dump(r, f, indent=2)
