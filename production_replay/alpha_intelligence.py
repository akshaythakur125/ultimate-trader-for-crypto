"""Alpha Intelligence Layer — elite Dux-style ranking from 0 to 100.

Reads Dux pattern reports and BingX universe data, computes multi-factor
alpha scores across 8 dimensions, and outputs ranked candidates.

Usage:
    python -m production_replay.alpha_intelligence
"""

import json, math, os, sys
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import get_all_swap_tickers, load_credentials
from production_replay.bingx_universe import KNOWN_MEMECOINS, KNOWN_MAJORS

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TXT_PATH = os.path.join(RESULTS_DIR, "alpha_intelligence_report.txt")
JSON_PATH = os.path.join(RESULTS_DIR, "alpha_intelligence_report.json")

SCORE_PATTERN_MAX = 20
SCORE_RR_MAX = 15
SCORE_VOLUME_MAX = 15
SCORE_TRAP_MAX = 15
SCORE_LIQUIDITY_MAX = 10
SCORE_RS_MAX = 10
SCORE_REGIME_MAX = 10
SCORE_HISTORICAL_MAX = 5
ALPHA_MAX = 100
ALPHA_WATCH_MIN = 70
ALPHA_ELITE_MIN = 85

PATTERN_QUALITY = {
    "parabolic_pump_fade": 18,
    "failed_breakout_trap": 17,
    "first_breakdown_after_pump": 16,
    "panic_flush_reclaim": 16,
    "weak_bounce_short": 15,
    "crowd_trap": 14,
}


def _read_json(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _score_pattern(p: dict) -> int:
    pid = p.get("pattern_id", "")
    base = PATTERN_QUALITY.get(pid, 10)
    has_vol = p.get("vol_expansion") is True
    wick_pct = p.get("wick_pct") or 0
    pump_pct = abs(p.get("pump_pct") or 0)
    if has_vol:
        base += 2
    if wick_pct >= 50:
        base += 1
    if pump_pct >= 5:
        base += 1
    return min(base, SCORE_PATTERN_MAX)


def _score_rr(p: dict) -> int:
    rr = p.get("rr_2") or 0
    if rr < 4.0:
        return -1
    base = 10
    if rr >= 5.0:
        base += 3
    elif rr >= 4.5:
        base += 2
    else:
        base += 1
    return min(base, SCORE_RR_MAX)


def _score_volume(p: dict, ticker_map: dict) -> int:
    sym = p.get("symbol", "")
    vol = ticker_map.get(sym, {}).get("quote_volume", 0)
    is_meme = sym in KNOWN_MEMECOINS
    vol_exp = p.get("vol_expansion")
    score = 5
    if vol_exp:
        score += 4
    if is_meme:
        score += 2
    if vol > 1_000_000:
        score += 2
    elif vol > 100_000:
        score += 1
    return min(score, SCORE_VOLUME_MAX)


def _score_trap(p: dict, ticker_map: dict) -> int:
    sym = p.get("symbol", "")
    pid = p.get("pattern_id", "")
    wick = p.get("wick_pct") or 0
    pump = abs(p.get("pump_pct") or 0)
    score = 5
    if pid in ("parabolic_pump_fade", "failed_breakout_trap"):
        score += 4
    if wick >= 50:
        score += 2
    if pump >= 5:
        score += 2
    if sym in KNOWN_MEMECOINS:
        score += 2
    return min(score, SCORE_TRAP_MAX)


def _score_liquidity(sym: str, ticker_map: dict) -> int:
    vol = ticker_map.get(sym, {}).get("quote_volume", 0)
    is_meme = sym in KNOWN_MEMECOINS
    is_major = sym in KNOWN_MAJORS
    score = 4
    if is_major:
        score += 4
    if vol > 10_000_000:
        score += 2
    elif vol > 1_000_000:
        score += 1
    if is_meme:
        score += 1
    return min(score, SCORE_LIQUIDITY_MAX)


def _score_relative_strength(sym: str, ticker_map: dict) -> int:
    is_meme = sym in KNOWN_MEMECOINS
    change_pct = ticker_map.get(sym, {}).get("price_change_pct", 0)
    score = 4
    if is_meme:
        score += 4
    if change_pct > 5:
        score += 2
    elif change_pct > 2:
        score += 1
    return min(score, SCORE_RS_MAX)


def _score_regime(p: dict) -> int:
    pid = p.get("pattern_id", "")
    pump = abs(p.get("pump_pct") or 0)
    score = 5
    if pid in ("parabolic_pump_fade", "weak_bounce_short", "panic_flush_reclaim"):
        score += 3
    if pump >= 5:
        score += 2
    return min(score, SCORE_REGIME_MAX)


def _score_historical(p: dict) -> int:
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
    return min(score, SCORE_HISTORICAL_MAX)


def _compute_alpha(p: dict, ticker_map: dict) -> dict:
    sym = p.get("symbol", "")
    rr = p.get("rr_2") or 0

    # Hard rejections
    if rr < 4.0:
        return {"alpha_score": 0, "rejected": True, "reject_reason": "RR < 4.0",
                "scores": {}}
    if p.get("direction", "UNKNOWN") == "UNKNOWN":
        return {"alpha_score": 0, "rejected": True, "reject_reason": "direction UNKNOWN",
                "scores": {}}
    if not sym or not sym.endswith("-USDT"):
        return {"alpha_score": 0, "rejected": True, "reject_reason": "not BingX-listed",
                "scores": {}}

    pattern_score = _score_pattern(p)
    rr_score = _score_rr(p)
    vol_score = _score_volume(p, ticker_map)
    trap_score = _score_trap(p, ticker_map)
    liq_score = _score_liquidity(sym, ticker_map)
    rs_score = _score_relative_strength(sym, ticker_map)
    regime_score = _score_regime(p)
    hist_score = _score_historical(p)

    if rr_score < 0:
        return {"alpha_score": 0, "rejected": True, "reject_reason": "RR < 4.0",
                "scores": {}}

    alpha = pattern_score + rr_score + vol_score + trap_score + liq_score + rs_score + regime_score + hist_score
    alpha = min(alpha, ALPHA_MAX)

    verdict = "REJECT"
    if alpha >= ALPHA_ELITE_MIN:
        verdict = "MANUAL_REVIEW_ONLY"
    elif alpha >= ALPHA_WATCH_MIN:
        verdict = "WATCH"

    return {
        "alpha_score": alpha,
        "rejected": alpha < ALPHA_WATCH_MIN,
        "reject_reason": "" if alpha >= ALPHA_WATCH_MIN else f"alpha {alpha} < {ALPHA_WATCH_MIN}",
        "scores": {
            "pattern": pattern_score,
            "risk_reward": rr_score,
            "volume_momentum": vol_score,
            "crowd_trap": trap_score,
            "liquidity": liq_score,
            "relative_strength": rs_score,
            "regime": regime_score,
            "historical_edge": hist_score,
        },
        "verdict": verdict,
    }


def run_alpha_intelligence() -> dict:
    dux = _read_json(os.path.join(RESULTS_DIR, "dux_pattern_report.json"))
    universe = _read_json(os.path.join(RESULTS_DIR, "bingx_universe.json"))

    patterns = dux.get("patterns", [])
    scan_symbols_count = dux.get("dux_scan_universe_size", universe.get("scan_universe_size", 0))
    total_contracts = dux.get("total_raw_contracts", universe.get("total_raw_contracts", 0))
    st_scanned = dux.get("symbol_timeframes_scanned", 0)

    # Load ticker data for volume/liquidity scoring
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
    for p in patterns:
        if not p.get("rejected", True):
            rr_pass_count += 1
            result = _compute_alpha(p, ticker_map)
            scored.append({**p, **result})

    scored.sort(key=lambda r: r.get("alpha_score", 0), reverse=True)
    alpha_watch = [s for s in scored if s.get("alpha_score", 0) >= ALPHA_WATCH_MIN and not s.get("rejected", True)]
    alpha_elite = [s for s in scored if s.get("alpha_score", 0) >= ALPHA_ELITE_MIN and not s.get("rejected", True)]

    best = alpha_elite[0] if alpha_elite else (alpha_watch[0] if alpha_watch else None)

    if best:
        final_decision = best["verdict"]
        reason = f"best: {best['pattern_name']} {best['symbol']} alpha {best['alpha_score']}"
    else:
        final_decision = "DO_NOT_TRADE"
        reason = "no candidate passes alpha >= 70"

    report = {
        "mode": "alpha_intelligence",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "total_raw_contracts": total_contracts,
        "dux_scan_symbols": scan_symbols_count,
        "symbol_timeframes_scanned": st_scanned,
        "total_patterns_detected": len(patterns),
        "rr_gate_pass_candidates": rr_pass_count,
        "alpha_watch_candidates": len(alpha_watch),
        "alpha_elite_candidates": len(alpha_elite),
        "alpha_watch_min": ALPHA_WATCH_MIN,
        "alpha_elite_min": ALPHA_ELITE_MIN,
        "best_candidate": {
            "symbol": best["symbol"],
            "timeframe": best["timeframe"],
            "pattern_name": best["pattern_name"],
            "direction": best["direction"],
            "entry": best["entry"],
            "stop": best["stop"],
            "target_2": best.get("target_2"),
            "rr_2": best.get("rr_2"),
            "alpha_score": best["alpha_score"],
            "scores": best["scores"],
            "verdict": best["verdict"],
        } if best else None,
        "final_decision": final_decision,
        "reason": reason,
        "top_ranked": [
            {
                "rank": i + 1,
                "symbol": s["symbol"],
                "timeframe": s["timeframe"],
                "pattern_name": s["pattern_name"],
                "direction": s["direction"],
                "rr_2": s.get("rr_2"),
                "alpha_score": s["alpha_score"],
                "scores": s["scores"],
                "verdict": s.get("verdict", "REJECT"),
            }
            for i, s in enumerate(scored[:10])
        ],
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(report, f, indent=2)

    _write_text_report(report, best)
    return report


def _write_text_report(report: dict, best: dict | None):
    lines = [
        "=" * 60,
        "  ALPHA INTELLIGENCE REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  BingX contracts discovered: {report['total_raw_contracts']}",
        f"  Dux scan symbols:           {report['dux_scan_symbols']}",
        f"  Symbol-timeframes scanned:  {report['symbol_timeframes_scanned']}",
        f"  Total patterns detected:    {report['total_patterns_detected']}",
        f"  RR >= 4 candidates:         {report['rr_gate_pass_candidates']}",
        f"  Alpha WATCH >= 70:          {report['alpha_watch_candidates']}",
        f"  Alpha ELITE >= 85:          {report['alpha_elite_candidates']}",
        "",
    ]

    if best:
        lines += [
            "  BEST ALPHA CANDIDATE:",
            f"    {best['pattern_name']} on {best['symbol']} {best['timeframe']}",
            f"    Direction: {best['direction']}  RR: 1:{best['rr_2']}",
            f"    Alpha Score: {best['alpha_score']}/100",
            f"     Elite: {'YES' if best['alpha_score'] >= 85 else 'NO'}",
            f"    Scores:  Pattern {best['scores']['pattern']} | RR {best['scores']['risk_reward']} | Vol {best['scores']['volume_momentum']} | Trap {best['scores']['crowd_trap']} | Liq {best['scores']['liquidity']} | RS {best['scores']['relative_strength']} | Reg {best['scores']['regime']} | Hist {best['scores']['historical_edge']}",
            f"    Verdict: {best['verdict']}",
            "",
        ]
    else:
        lines += ["  BEST ALPHA CANDIDATE: NONE", ""]

    lines += [
        f"  FINAL ALPHA DECISION: {report['final_decision']}",
        f"  REASON: {report['reason']}",
        "",
    ]

    top10 = report.get("top_ranked", [])
    if top10:
        lines += [
            "  TOP RANKED CANDIDATES:",
            "",
            "  {:<3s} {:<15s} {:<6s} {:<25s} {:<4s} {:<6s} {:<6s} {:<8s}".format(
                "Rk", "Symbol", "TF", "Pattern", "Dir", "RR T2", "Alpha", "Verdict"),
            "  " + "-" * 73,
        ]
        for r in top10:
            d = r["direction"][:4]
            lines.append("  {:<3d} {:<15s} {:<6s} {:<25s} {:<4s} {:<6s} {:<6d} {:<8s}".format(
                r["rank"], r["symbol"], r["timeframe"], r["pattern_name"][:25],
                d, str(r["rr_2"] or "N/A"), r["alpha_score"] or 0, r["verdict"]))
        lines.append("")

    lines += [
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
    report = run_alpha_intelligence()
    return 0


if __name__ == "__main__":
    sys.exit(main())
