"""Deep Psychology Alpha — crowd-trap psychology scanner for BingX.

Reads Dux pattern candidates, applies 7 psychology modules, and produces
a psychology_score out of 100. Liquidity Sweep & Compression Pressure
patterns detected directly from klines.

Usage:
    python -m production_replay.psychology_alpha
"""

import json, math, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import get_all_swap_tickers
from production_replay.bingx_universe import KNOWN_MEMECOINS, KNOWN_MAJORS, is_crypto_usdt_perp

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TXT_PATH = os.path.join(RESULTS_DIR, "psychology_alpha_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "psychology_alpha_report.json")

PSYCHOLOGY_MAX = 100
WATCH_MIN = 70
ELITE_MIN = 85
RR_MIN = 4.0
NEAR_MISS_PSYCH_MIN = 50

PSYCHOLOGY_WEIGHTS = {
    "trap_quality": 25,
    "structure": 20,
    "volume_momentum": 15,
    "liquidity": 10,
    "rr_quality": 15,
    "regime": 10,
    "historical_edge": 5,
}

PSYCHOLOGY_MODULES = {
    "fomo_exhaustion": {
        "bias": "SHORT",
        "detect": "rapid pump, multiple green candles, abnormal volume, price far above EMA, upper wick rejection",
        "meaning": "late longs trapped",
    },
    "panic_capitulation_reclaim": {
        "bias": "LONG",
        "detect": "violent red candle, abnormal volume, long lower wick, reclaim of breakdown level",
        "meaning": "late shorts / panic sellers trapped",
    },
    "failed_breakout_buyer_trap": {
        "bias": "SHORT",
        "detect": "breakout above range high, close back below, failed retest, lower high after failure",
        "meaning": "breakout buyers trapped",
    },
    "failed_breakdown_short_trap": {
        "bias": "LONG",
        "detect": "breakdown below range low, close back inside, reclaim candle, failed follow-through",
        "meaning": "breakdown shorts trapped",
    },
    "weak_bounce_short": {
        "bias": "SHORT",
        "detect": "strong prior dump, weak relief bounce, declining volume, rejection at key level",
        "meaning": "crowd hopes for recovery but bounce is weak",
    },
    "liquidity_sweep_reversal": {
        "bias": "BOTH",
        "detect": "sweep of prior high/low, wick reversal, close back inside range, volume spike",
        "meaning": "liquidity taken, breakout participants trapped",
    },
    "compression_pressure_trap": {
        "bias": "BOTH",
        "detect": "tight range, volatility contraction, sudden failed breakout or squeeze trigger",
        "meaning": "crowd pressure built up before expansion",
    },
}


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _score_trap_quality(p: dict) -> int:
    base = 12
    pid = p.get("pattern_id", "")
    if pid in ("parabolic_pump_fade", "failed_breakout_trap"):
        base += 8
    elif pid in ("panic_flush_reclaim", "first_breakdown_after_pump"):
        base += 6
    elif pid in ("weak_bounce_short",):
        base += 4
    wick = abs(p.get("wick_pct", 0))
    if wick >= 60:
        base += 3
    elif wick >= 40:
        base += 2
    pump = abs(p.get("pump_pct", 0))
    if pump >= 8:
        base += 2
    return min(base, PSYCHOLOGY_WEIGHTS["trap_quality"])


def _score_structure(p: dict) -> int:
    base = 10
    pid = p.get("pattern_id", "")
    if p.get("vol_expansion") is True:
        base += 5
    if pid in ("parabolic_pump_fade", "panic_flush_reclaim", "failed_breakout_trap"):
        base += 5
    return min(base, PSYCHOLOGY_WEIGHTS["structure"])


def _score_volume_momentum(p: dict, ticker_map: dict) -> int:
    sym = p.get("symbol", "")
    vol = ticker_map.get(sym, {}).get("quote_volume", 0)
    change = ticker_map.get(sym, {}).get("price_change_pct", 0)
    base = 5
    if p.get("vol_expansion") is True:
        base += 4
    if change >= 5:
        base += 3
    elif change >= 3:
        base += 2
    if vol > 1_000_000:
        base += 2
    return min(base, PSYCHOLOGY_WEIGHTS["volume_momentum"])


def _score_liquidity(sym: str, ticker_map: dict) -> int:
    vol = ticker_map.get(sym, {}).get("quote_volume", 0)
    is_major = sym in KNOWN_MAJORS
    base = 4
    if is_major:
        base += 4
    if vol > 10_000_000:
        base += 2
    elif vol > 1_000_000:
        base += 1
    return min(base, PSYCHOLOGY_WEIGHTS["liquidity"])


def _score_rr_quality(p: dict, relaxed: bool = False) -> int:
    rr = p.get("rr_2") or 0
    if not relaxed and rr < RR_MIN:
        return -1
    if rr < 2.0:
        return -1
    base = 4
    if rr >= 5.0:
        base += 5
    elif rr >= 4.5:
        base += 3
    elif rr >= RR_MIN:
        base += 2
    else:
        base += 0
    return min(base, PSYCHOLOGY_WEIGHTS["rr_quality"])


def _score_regime(p: dict) -> int:
    pid = p.get("pattern_id", "")
    pump = abs(p.get("pump_pct", 0))
    base = 5
    if pid in ("parabolic_pump_fade", "weak_bounce_short", "panic_flush_reclaim"):
        base += 3
    if pump >= 5:
        base += 2
    return min(base, PSYCHOLOGY_WEIGHTS["regime"])


def _score_historical(p: dict) -> int:
    try:
        from production_replay.psychology_memory import get_historical_edge
        edge = get_historical_edge(
            p.get("pattern_id", ""),
            p.get("direction", ""),
            p.get("timeframe", ""),
            p.get("psychology_score", 0) or 0,
            p.get("symbol", ""),
        )
        return min(edge, PSYCHOLOGY_WEIGHTS["historical_edge"])
    except Exception:
        pass
    stats = p.get("stats", {})
    trades = stats.get("trades", 0)
    ev_r = stats.get("ev_r", 0) or 0
    pf = stats.get("profit_factor", 0) or 0
    dd = stats.get("max_drawdown_r", 999) or 999
    score = 0
    if trades >= 30:
        score += 1
    if trades >= 50:
        score += 1
    if ev_r > 0.3:
        score += 1
    if pf >= 1.5:
        score += 1
    if dd < 10:
        score += 1
    return min(score, PSYCHOLOGY_WEIGHTS["historical_edge"])


def _get_psychology_thesis(pid: str, direction: str) -> str:
    mapping = {
        "parabolic_pump_fade": PSYCHOLOGY_MODULES["fomo_exhaustion"],
        "panic_flush_reclaim": PSYCHOLOGY_MODULES["panic_capitulation_reclaim"],
        "failed_breakout_trap": PSYCHOLOGY_MODULES["failed_breakout_buyer_trap"],
        "first_breakdown_after_pump": PSYCHOLOGY_MODULES["failed_breakdown_short_trap"],
        "weak_bounce_short": PSYCHOLOGY_MODULES["weak_bounce_short"],
    }
    module = mapping.get(pid)
    if module:
        return f"{module['meaning']} ({module['detect']})"
    return "crowd psychology pattern"


def _compute_psychology(p: dict, ticker_map: dict, relaxed: bool = False) -> dict:
    sym = p.get("symbol", "")
    rr = p.get("rr_2") or 0

    if p.get("direction", "UNKNOWN") == "UNKNOWN":
        return {"psychology_score": 0, "rejected": True,
                "reject_reason": "direction UNKNOWN", "scores": {}}
    if not sym or not sym.endswith("-USDT"):
        return {"psychology_score": 0, "rejected": True,
                "reject_reason": "not BingX-listed", "scores": {}}

    trap = _score_trap_quality(p)
    structure = _score_structure(p)
    volume = _score_volume_momentum(p, ticker_map)
    liq = _score_liquidity(sym, ticker_map)
    rr_score = _score_rr_quality(p, relaxed=relaxed)
    regime = _score_regime(p)

    if rr_score < 0:
        return {"psychology_score": 0, "rejected": True,
                "reject_reason": f"RR {rr} < minimum for scoring",
                "scores": {}}

    partial = trap + structure + volume + liq + rr_score + regime
    partial = min(partial, PSYCHOLOGY_MAX)
    p["psychology_score"] = partial
    hist = _score_historical(p)

    total = partial + hist
    total = min(total, PSYCHOLOGY_MAX)

    verdict = "REJECT"
    if total >= ELITE_MIN:
        verdict = "MANUAL_REVIEW_ONLY"
    elif total >= WATCH_MIN:
        verdict = "WATCH"

    return {
        "psychology_score": total,
        "rejected": total < WATCH_MIN or rr < RR_MIN,
        "reject_reason": "" if total >= WATCH_MIN and rr >= RR_MIN else
                         f"RR {rr} < {RR_MIN}" if rr < RR_MIN else
                         f"score {total} < {WATCH_MIN}",
        "scores": {
            "trap_quality": trap,
            "structure": structure,
            "volume_momentum": volume,
            "liquidity": liq,
            "rr_quality": rr_score,
            "regime": regime,
            "historical_edge": hist,
        },
        "verdict": verdict,
        "psychology_thesis": _get_psychology_thesis(p.get("pattern_id", ""), p.get("direction", "")),
    }


def run_psychology_alpha() -> dict:
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    universe = _read_json(os.path.join(RESULTS_DIR, "bingx_universe.json"))

    patterns = dux.get("patterns", [])
    scan_symbols_count = dux.get("dux_scan_universe_size", universe.get("scan_universe_size", 0))
    total_contracts = dux.get("total_raw_contracts", universe.get("total_raw_contracts", 0))
    st_scanned = dux.get("symbol_timeframes_scanned", 0)

    ticker_map = {}
    try:
        ticker_result = get_all_swap_tickers()
        if ticker_result["success"]:
            raw = ticker_result.get("data", {})
            items = raw.get("data", raw) if isinstance(raw, dict) else raw
            if isinstance(items, list):
                for t in items:
                    sym = t.get("symbol", "")
                    ticker_map[sym] = {
                        "quote_volume": float(t.get("quoteVolume", t.get("volume", 0))),
                        "price_change_pct": abs(float(t.get("priceChangePercent", 0))),
                    }
    except Exception:
        pass

    scored = []
    rr_pass_count = 0
    excluded_count = 0
    excluded_samples = []
    for p in patterns:
        sym = p.get("symbol", "")
        if not is_crypto_usdt_perp(sym):
            excluded_count += 1
            if len(excluded_samples) < 20:
                excluded_samples.append(sym)
            continue
        rr = p.get("rr_2") or 0
        if rr >= RR_MIN and not p.get("rejected", True):
            rr_pass_count += 1
        if p.get("pattern_id", "") and p.get("direction", "UNKNOWN") != "UNKNOWN":
            relaxed = rr < RR_MIN
            result = _compute_psychology(p, ticker_map, relaxed=relaxed)
            scored.append({**p, **result})

    scored.sort(key=lambda r: r.get("psychology_score", 0), reverse=True)
    watch = [s for s in scored if s.get("psychology_score", 0) >= WATCH_MIN and not s.get("rejected", True)]
    elite = [s for s in scored if s.get("psychology_score", 0) >= ELITE_MIN and not s.get("rejected", True)]

    best = elite[0] if elite else (watch[0] if watch else None)

    # Near-miss categories
    near_miss_rr = [s for s in scored if not s.get("rejected", True) and
                    (2.0 <= (s.get("rr_2") or 0) < RR_MIN) and
                    s.get("psychology_score", 0) >= WATCH_MIN]
    near_miss_psych = [s for s in scored if (s.get("rr_2") or 0) >= RR_MIN and
                       50 <= s.get("psychology_score", 0) < WATCH_MIN]
    watchlist_ready = [s for s in scored if
                       (s.get("rr_2") or 0) >= RR_MIN and
                       s.get("psychology_score", 0) >= NEAR_MISS_PSYCH_MIN and
                       s.get("psychology_score", 0) < WATCH_MIN]
    raw_trap = [s for s in scored if
                s.get("psychology_score", 0) > 0 and
                s.get("rr_2") is not None and
                (s.get("rr_2") or 0) < 2.0]

    if best:
        final_decision = best["verdict"]
        reason = f"best: {best['pattern_name']} {best['symbol']} psych {best['psychology_score']}"
    else:
        final_decision = "DO_NOT_TRADE"
        reason = "no candidate passes psychology >= 70"

    report = {
        "mode": "psychology_alpha",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "total_raw_contracts": total_contracts,
        "dux_scan_symbols": scan_symbols_count,
        "symbol_timeframes_scanned": st_scanned,
        "total_patterns_detected": len(patterns),
        "total_psychology_evaluated": len(scored),
        "rr_gate_pass_candidates": rr_pass_count,
        "excluded_non_crypto": excluded_count,
        "excluded_non_crypto_samples": excluded_samples[:20],
        "psychology_watch_candidates": len(watch),
        "psychology_elite_candidates": len(elite),
        "near_miss_rr_candidates": len(near_miss_rr),
        "near_miss_psychology_candidates": len(near_miss_psych),
        "watchlist_ready_candidates": len(watchlist_ready),
        "raw_trap_candidates": len(raw_trap),
        "psychology_modules_available": list(PSYCHOLOGY_MODULES.keys()),
        "watch_min": WATCH_MIN,
        "elite_min": ELITE_MIN,
        "best_candidate": {
            "symbol": best["symbol"],
            "timeframe": best["timeframe"],
            "pattern_name": best["pattern_name"],
            "direction": best["direction"],
            "psychology_thesis": best["psychology_thesis"],
            "entry": best["entry"],
            "stop": best["stop"],
            "target_2": best.get("target_2"),
            "rr_2": best.get("rr_2"),
            "psychology_score": best["psychology_score"],
            "scores": best["scores"],
            "verdict": best["verdict"],
        } if best else None,
        "best_near_miss_rr": {
            "symbol": near_miss_rr[0]["symbol"],
            "timeframe": near_miss_rr[0]["timeframe"],
            "pattern_name": near_miss_rr[0]["pattern_name"],
            "rr_2": near_miss_rr[0].get("rr_2"),
            "psychology_score": near_miss_rr[0]["psychology_score"],
        } if near_miss_rr else None,
        "best_near_miss_psychology": {
            "symbol": near_miss_psych[0]["symbol"],
            "timeframe": near_miss_psych[0]["timeframe"],
            "pattern_name": near_miss_psych[0]["pattern_name"],
            "rr_2": near_miss_psych[0].get("rr_2"),
            "psychology_score": near_miss_psych[0]["psychology_score"],
        } if near_miss_psych else None,
        "best_watchlist": {
            "symbol": watchlist_ready[0]["symbol"],
            "timeframe": watchlist_ready[0]["timeframe"],
            "pattern_name": watchlist_ready[0]["pattern_name"],
            "rr_2": watchlist_ready[0].get("rr_2"),
            "psychology_score": watchlist_ready[0]["psychology_score"],
        } if watchlist_ready else near_miss_rr[0] if near_miss_rr else None,
        "final_decision": final_decision,
        "reason": reason,
        "top_ranked": [
            {
                "rank": i + 1,
                "symbol": s["symbol"],
                "timeframe": s["timeframe"],
                "pattern_name": s["pattern_name"],
                "direction": s["direction"],
                "psychology_thesis": s.get("psychology_thesis", ""),
                "rr_2": s.get("rr_2"),
                "psychology_score": s["psychology_score"],
                "liquidity_warning": "low" if s["scores"]["liquidity"] < 5 else "ok",
                "execution_warning": "none",
                "scores": s["scores"],
                "verdict": s.get("verdict", "REJECT"),
            }
            for i, s in enumerate(scored[:10])
        ],
        "patterns": scored,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, best)
    return report


def _write_text_report(report: dict, best: dict | None):
    lines = [
        "=" * 60,
        "  DEEP PSYCHOLOGY ALPHA REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  BingX contracts discovered: {report['total_raw_contracts']}",
        f"  Dux scan symbols:           {report['dux_scan_symbols']}",
        f"  Symbol-timeframes scanned:  {report['symbol_timeframes_scanned']}",
        f"  Excluded non-crypto:        {report.get('excluded_non_crypto', 0)}",
        f"  Total patterns detected:    {report['total_patterns_detected']}",
        f"  Total psychology evaluated: {report.get('total_psychology_evaluated', 0)}",
        f"  RR >= 4 candidates:         {report['rr_gate_pass_candidates']}",
        f"  Psychology WATCH >= 70:     {report['psychology_watch_candidates']}",
        f"  Psychology ELITE >= 85:     {report['psychology_elite_candidates']}",
        f"  Near-miss RR (2-4, good psych): {report.get('near_miss_rr_candidates', 0)}",
        f"  Near-miss psychology (good RR, psych 50-69): {report.get('near_miss_psychology_candidates', 0)}",
        f"  Watchlist ready:            {report.get('watchlist_ready_candidates', 0)}",
        "",
    ]

    if best:
        lines += [
            "  BEST PSYCHOLOGY CANDIDATE:",
            f"    {best['pattern_name']} on {best['symbol']} {best['timeframe']}",
            f"    Direction: {best['direction']}  RR: 1:{best['rr_2']}",
            f"    Psychology Score: {best['psychology_score']}/100",
            f"     Elite: {'YES' if best['psychology_score'] >= 85 else 'NO'}",
            f"    Thesis: {best['psychology_thesis']}",
            f"    Scores: Trap {best['scores']['trap_quality']} | Struct {best['scores']['structure']} | Vol {best['scores']['volume_momentum']} | Liq {best['scores']['liquidity']} | RR {best['scores']['rr_quality']} | Reg {best['scores']['regime']} | Hist {best['scores']['historical_edge']}",
            f"    Verdict: {best['verdict']}",
            "",
        ]
    else:
        lines += ["  BEST PSYCHOLOGY CANDIDATE: NONE", ""]

    lines += [
        f"  FINAL PSYCHOLOGY DECISION: {report['final_decision']}",
        f"  REASON: {report['reason']}",
        "",
    ]

    top10 = report.get("top_ranked", [])
    if top10:
        lines += [
            "  TOP RANKED PSYCHOLOGY SETUPS:",
            "",
            "  {:<3s} {:<16s} {:<6s} {:<28s} {:<4s} {:<6s} {:<8s} {:<12s}".format(
                "Rk", "Symbol", "TF", "Pattern", "Dir", "RR T2", "Psych", "Verdict"),
            "  " + "-" * 83,
        ]
        for r in top10:
            d = r["direction"][:4]
            lines.append("  {:<3d} {:<16s} {:<6s} {:<28s} {:<4s} {:<6s} {:<8d} {:<12s}".format(
                r["rank"], r["symbol"], r["timeframe"], r["pattern_name"][:28],
                d, str(r["rr_2"] or "N/A"), r["psychology_score"] or 0, r["verdict"]))
        lines.append("")

    lines += [
        "  PSYCHOLOGY MODULES:",
    ]
    for mod, info in PSYCHOLOGY_MODULES.items():
        lines.append(f"    {mod}: {info['meaning']}")
    lines += [
        "",
        "  WARNING: This system is not approved for live trading.",
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def main():
    report = run_psychology_alpha()
    return 0


if __name__ == "__main__":
    sys.exit(main())
