"""Strategy Tournament Engine — research-only.

Tests multiple known strategy families against each configured symbol/timeframe,
ranks them by evidence, and outputs a structured report.

Usage:
    python -m production_replay.strategy_tournament
"""

import csv, json, math, os, sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.setup_compute import load_candles

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
TXT_REPORT = os.path.join(RESULTS_DIR, "strategy_tournament_report.txt")
JSON_REPORT = os.path.join(RESULTS_DIR, "strategy_tournament_report.json")

STRATEGY_NAMES = {
    "ema_trend_pullback": "EMA Trend Pullback",
    "donchian_breakout": "Donchian Breakout",
    "atr_volatility_breakout": "ATR Volatility Breakout",
    "rsi_mean_reversion": "RSI Mean Reversion",
    "liquidity_sweep_reversal": "Liquidity Sweep Reversal",
    "bollinger_squeeze": "Bollinger Squeeze",
}

CONFIGS = [
    ("BTCUSDT", "15m"), ("BTCUSDT", "30m"), ("BTCUSDT", "1h"),
    ("ETHUSDT", "15m"), ("ETHUSDT", "30m"),
    ("SOLUSDT", "15m"), ("SOLUSDT", "30m"),
]

# Acceptance gates
MIN_TRADES = 50
MIN_EV_R = 0.20
MIN_PF = 1.30
MAX_DD_R = 10.0
MAX_CONSECUTIVE_LOSSES = 6
MIN_RR = 1.5  # preferred

# Hard reject thresholds (below these = always REJECT)
HARD_MIN_TRADES = 5
HARD_MIN_EV_R = 0.0
HARD_MIN_PF = 0.9
HARD_MAX_DD_R = 15.0
HARD_MAX_CONSECUTIVE_LOSSES = 8


def compute_ema(closes: list[float], period: int) -> list[float | None]:
    n = len(closes)
    if n < period:
        return [None] * n
    multiplier = 2.0 / (period + 1)
    ema: list[float | None] = [None] * n
    s = sum(closes[:period]) / period
    ema[period - 1] = s
    for i in range(period, n):
        ema[i] = (closes[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


def compute_rsi(candles: list[dict], period: int = 14) -> list[float | None]:
    n = len(candles)
    if n < period + 1:
        return [None] * n
    rsi: list[float | None] = [None] * n
    gains = losses = 0.0
    for i in range(1, period + 1):
        diff = candles[i]["close"] - candles[i - 1]["close"]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period if losses > 0 else 1e-10
    rs = avg_gain / avg_loss
    rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        diff = candles[i]["close"] - candles[i - 1]["close"]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else 1e10
        rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_bb(candles: list[dict], period: int = 20, std: float = 2.0):
    n = len(candles)
    if n < period:
        return [None] * n, [None] * n, [None] * n
    upper: list[float | None] = [None] * n
    middle: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = [c["close"] for c in candles[i - period + 1 : i + 1]]
        m = sum(window) / period
        variance = sum((x - m) ** 2 for x in window) / period
        sd = math.sqrt(variance)
        middle[i] = m
        upper[i] = m + std * sd
        lower[i] = m - std * sd
    return upper, middle, lower


def compute_donchian(candles: list[dict], period: int = 20):
    n = len(candles)
    if n < period:
        return [None] * n, [None] * n, [None] * n
    d_high: list[float | None] = [None] * n
    d_low: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = candles[i - period + 1 : i + 1]
        d_high[i] = max(c["high"] for c in window)
        d_low[i] = min(c["low"] for c in window)
    d_mid = [
        None if h is None or l is None else (h + l) / 2 for h, l in zip(d_high, d_low)
    ]
    return d_high, d_mid, d_low


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    n = len(candles)
    if n < 2:
        return [None] * n
    tr: list[float | None] = [None] * n
    for i in range(1, n):
        tr[i] = max(
            candles[i]["high"] - candles[i]["low"],
            abs(candles[i]["high"] - candles[i - 1]["close"]),
            abs(candles[i]["low"] - candles[i - 1]["close"]),
        )
    atr: list[float | None] = [None] * n
    for i in range(period, n):
        vals = [t for t in tr[i - period + 1 : i + 1] if t is not None]
        atr[i] = sum(vals) / max(len(vals), 1)
    return atr


def _simulate_trade(
    candles: list[dict],
    idx: int,
    direction: str,
    atr_val: float,
    atr_mult: float = 1.5,
    max_lookahead: int = 48,
) -> tuple[float, float]:
    if idx >= len(candles) - 1 or atr_val <= 0:
        return (0.0, 0.0)
    entry_price = candles[idx]["close"]
    risk = atr_val * atr_mult
    if direction == "LONG":
        stop = entry_price - risk
        t1 = entry_price + risk * 1.5
        t2 = entry_price + risk * 3.0
    else:
        stop = entry_price + risk
        t1 = entry_price - risk * 1.5
        t2 = entry_price - risk * 3.0

    for j in range(idx + 1, min(idx + max_lookahead + 1, len(candles))):
        c = candles[j]
        if direction == "LONG":
            if c["low"] <= stop:
                return (-1.0, 1.0)
            if c["high"] >= t2:
                return (3.0, 3.0)
            if c["high"] >= t1:
                return (1.5, 1.5)
        else:
            if c["high"] >= stop:
                return (-1.0, 1.0)
            if c["low"] <= t2:
                return (3.0, 3.0)
            if c["low"] <= t1:
                return (1.5, 1.5)
    return (0.0, 0.0)


def _ema_trend_pullback(candles: list[dict]) -> list[tuple[float, float]]:
    n = len(candles)
    if n < 60:
        return []
    closes = [c["close"] for c in candles]
    ema20 = compute_ema(closes, 20)
    ema50 = compute_ema(closes, 50)
    atr = atr_series(candles)
    signals: list[tuple[float, float]] = []
    for i in range(55, n - 5):
        if ema20[i] is None or ema50[i] is None or atr[i] is None or atr[i] <= 0:
            continue
        if ema20[i] > ema50[i]:
            if abs(candles[i]["close"] - ema20[i]) / atr[i] < 1.0:
                for j in range(i + 1, min(i + 6, n - 1)):
                    if (
                        candles[j]["close"] > candles[j - 1]["close"]
                        and candles[j]["close"] > ema20[j]
                    ):
                        signals.append(_simulate_trade(candles, j, "LONG", atr[j]))
                        break
        elif ema20[i] < ema50[i]:
            if abs(candles[i]["close"] - ema20[i]) / atr[i] < 1.0:
                for j in range(i + 1, min(i + 6, n - 1)):
                    if (
                        candles[j]["close"] < candles[j - 1]["close"]
                        and candles[j]["close"] < ema20[j]
                    ):
                        signals.append(_simulate_trade(candles, j, "SHORT", atr[j]))
                        break
    return signals


def _donchian_breakout(candles: list[dict]) -> list[tuple[float, float]]:
    n = len(candles)
    if n < 25:
        return []
    d_high, _, d_low = compute_donchian(candles, 20)
    atr = atr_series(candles)
    signals: list[tuple[float, float]] = []
    for i in range(25, n - 5):
        if d_high[i] is None or d_low[i] is None or atr[i] is None or atr[i] <= 0:
            continue
        vol = candles[i].get("volume", 1)
        prev_vol = candles[i - 1].get("volume", 1) if i > 0 else 1
        vol_ok = prev_vol > 0 and vol / prev_vol > 1.2
        if candles[i]["high"] > d_high[i - 1] and vol_ok:
            signals.append(_simulate_trade(candles, i, "LONG", atr[i]))
        elif candles[i]["low"] < d_low[i - 1] and vol_ok:
            signals.append(_simulate_trade(candles, i, "SHORT", atr[i]))
    return signals


def _atr_volatility_breakout(candles: list[dict]) -> list[tuple[float, float]]:
    n = len(candles)
    if n < 25:
        return []
    atr = atr_series(candles)
    signals: list[tuple[float, float]] = []
    for i in range(25, n - 5):
        if atr[i] is None or atr[i] <= 0:
            continue
        hist = [a for a in atr[i - 20 : i] if a is not None]
        if len(hist) < 10:
            continue
        avg_atr = sum(hist) / len(hist)
        if atr[i] < avg_atr * 0.8:
            body = abs(candles[i]["close"] - candles[i]["open"])
            candle_range = candles[i]["high"] - candles[i]["low"]
            if candle_range > 0 and body / candle_range > 0.6:
                if candles[i]["close"] > candles[i]["open"]:
                    signals.append(
                        _simulate_trade(candles, i, "LONG", atr[i])
                    )
                else:
                    signals.append(
                        _simulate_trade(candles, i, "SHORT", atr[i])
                    )
    return signals


def _rsi_mean_reversion(candles: list[dict]) -> list[tuple[float, float]]:
    n = len(candles)
    if n < 25:
        return []
    rs = compute_rsi(candles, 14)
    atr = atr_series(candles)
    signals: list[tuple[float, float]] = []
    for i in range(20, n - 5):
        if rs[i] is None or atr[i] is None or atr[i] <= 0:
            continue
        if rs[i] < 28:
            signals.append(_simulate_trade(candles, i, "LONG", atr[i]))
        elif rs[i] > 72:
            signals.append(_simulate_trade(candles, i, "SHORT", atr[i]))
    return signals


def _liquidity_sweep_reversal(candles: list[dict]) -> list[tuple[float, float]]:
    n = len(candles)
    if n < 30:
        return []
    atr = atr_series(candles)
    signals: list[tuple[float, float]] = []
    lookback = 10
    for i in range(lookback + 1, n - 5):
        if atr[i] is None or atr[i] <= 0:
            continue
        window = candles[i - lookback : i]
        recent_high = max(c["high"] for c in window)
        recent_low = min(c["low"] for c in window)
        c = candles[i]
        if c["high"] >= recent_high and c["low"] > recent_low:
            # Swept high, closed back inside — short reversal
            signals.append(_simulate_trade(candles, i, "SHORT", atr[i]))
        elif c["low"] <= recent_low and c["high"] < recent_high:
            # Swept low, closed back inside — long reversal
            signals.append(_simulate_trade(candles, i, "LONG", atr[i]))
    return signals


def _bollinger_squeeze(candles: list[dict]) -> list[tuple[float, float]]:
    n = len(candles)
    if n < 25:
        return []
    upper, middle, lower = compute_bb(candles, 20)
    atr = atr_series(candles)
    signals: list[tuple[float, float]] = []
    for i in range(25, n - 5):
        if (
            upper[i] is None
            or lower[i] is None
            or middle[i] is None
            or atr[i] is None
            or atr[i] <= 0
        ):
            continue
        bw = upper[i] - lower[i]
        hist_bw = [
            upper[j] - lower[j]
            for j in range(i - 20, i)
            if upper[j] is not None and lower[j] is not None
        ]
        if not hist_bw:
            continue
        avg_bw = sum(hist_bw) / len(hist_bw)
        if bw < avg_bw * 0.5 and candles[i]["close"] > upper[i]:
            signals.append(_simulate_trade(candles, i, "LONG", atr[i]))
        elif bw < avg_bw * 0.5 and candles[i]["close"] < lower[i]:
            signals.append(_simulate_trade(candles, i, "SHORT", atr[i]))
    return signals


STRATEGY_FUNCS = {
    "ema_trend_pullback": _ema_trend_pullback,
    "donchian_breakout": _donchian_breakout,
    "atr_volatility_breakout": _atr_volatility_breakout,
    "rsi_mean_reversion": _rsi_mean_reversion,
    "liquidity_sweep_reversal": _liquidity_sweep_reversal,
    "bollinger_squeeze": _bollinger_squeeze,
}


def _compute_stats(signals: list[tuple[float, float]]) -> dict:
    trades = len(signals)
    if trades == 0:
        return {
            "trades": 0, "win_rate": 0.0, "ev_r": 0.0, "profit_factor": 0.0,
            "max_drawdown_r": 0.0, "max_consecutive_losses": 0, "avg_rr": 0.0,
            "recent_30d_ev_r": 0.0,
        }
    wins = [r for r in signals if r[0] > 0]
    losses = [r for r in signals if r[0] < 0]
    win_rate = len(wins) / trades if trades > 0 else 0.0
    ev_r = sum(r[0] for r in signals) / trades
    gross_profit = sum(r[0] for r in wins)
    gross_loss = abs(sum(r[0] for r in losses)) if losses else 1e-10
    pf = gross_profit / gross_loss if gross_loss > 0 else 0.0
    avg_rr = sum(r[1] for r in signals) / trades if trades > 0 else 0.0

    # Max consecutive losses
    max_consec = cur_consec = 0
    for r in signals:
        if r[0] < 0:
            cur_consec += 1
            max_consec = max(max_consec, cur_consec)
        else:
            cur_consec = 0

    # Running equity curve for max drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in signals:
        equity += r[0]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Recent 30-day EV (last third of signals)
    third = max(trades // 3, 1)
    recent_signals = signals[-third:]
    recent_ev = sum(r[0] for r in recent_signals) / len(recent_signals) if recent_signals else 0.0

    return {
        "trades": trades, "win_rate": round(win_rate, 4), "ev_r": round(ev_r, 4),
        "profit_factor": round(pf, 4), "max_drawdown_r": round(max_dd, 2),
        "max_consecutive_losses": max_consec, "avg_rr": round(avg_rr, 4),
        "recent_30d_ev_r": round(recent_ev, 4),
    }


def _compute_verdict(stats: dict, hard: bool = False) -> str:
    if hard:
        if stats["trades"] < HARD_MIN_TRADES:
            return "REJECT"
        if stats["ev_r"] <= HARD_MIN_EV_R:
            return "REJECT"
        if stats["profit_factor"] < HARD_MIN_PF:
            return "REJECT"
        if stats["max_drawdown_r"] > HARD_MAX_DD_R:
            return "REJECT"
        if stats["max_consecutive_losses"] > HARD_MAX_CONSECUTIVE_LOSSES:
            return "REJECT"
        if stats["recent_30d_ev_r"] <= 0:
            return "REJECT"
        return None  # passed hard gates

    h = _compute_verdict(stats, hard=True)
    if h:
        return h

    gates_pass = (
        stats["trades"] >= MIN_TRADES
        and stats["ev_r"] > MIN_EV_R
        and stats["profit_factor"] >= MIN_PF
        and stats["max_drawdown_r"] <= MAX_DD_R
        and stats["max_consecutive_losses"] <= MAX_CONSECUTIVE_LOSSES
        and stats["recent_30d_ev_r"] > 0
    )
    if gates_pass and stats["avg_rr"] >= MIN_RR:
        return "PASS"
    if gates_pass:
        return "WATCH"
    marginal = (
        stats["trades"] >= MIN_TRADES - 20
        and stats["ev_r"] > 0
        and stats["profit_factor"] >= 1.0
        and stats["max_drawdown_r"] <= MAX_DD_R + 5
        and stats["max_consecutive_losses"] <= MAX_CONSECUTIVE_LOSSES + 2
        and stats["recent_30d_ev_r"] > 0
    )
    if marginal:
        return "WATCH"
    return "REJECT"


def run_tournament() -> list[dict]:
    results: list[dict] = []
    for symbol, tf in CONFIGS:
        candles = load_candles(symbol, tf)
        if len(candles) < 30:
            results.append({
                "symbol": symbol, "timeframe": tf, "strategy_id": "all",
                "display_name": "All Strategies",
                "trades": 0, "win_rate": 0.0, "ev_r": 0.0, "profit_factor": 0.0,
                "max_drawdown_r": 0.0, "max_consecutive_losses": 0, "avg_rr": 0.0,
                "recent_30d_ev_r": 0.0, "verdict": "SKIP",
                "reason": "no data", "config_label": f"{symbol} {tf}",
            })
            continue

        # Run each strategy on this config's candles
        config_results = []
        for strat_id, strat_func in STRATEGY_FUNCS.items():
            signals = strat_func(candles)
            stats = _compute_stats(signals)
            verdict = _compute_verdict(stats)
            config_results.append({
                "symbol": symbol, "timeframe": tf,
                "strategy_id": strat_id,
                "display_name": STRATEGY_NAMES[strat_id],
                "config_label": f"{symbol} {tf}",
                **stats,
                "verdict": verdict,
                "reason": "" if verdict == "PASS" else _verdict_reason(verdict, stats),
            })

        results.extend(config_results)
    return results


def _verdict_reason(verdict: str, stats: dict) -> str:
    if verdict == "PASS":
        return ""
    if verdict == "SKIP":
        return "insufficient data"
    if verdict == "REJECT":
        reasons = []
        if stats["trades"] < HARD_MIN_TRADES:
            reasons.append(f"trades {stats['trades']}<{HARD_MIN_TRADES}")
        if stats["ev_r"] <= HARD_MIN_EV_R:
            reasons.append(f"EV {stats['ev_r']}<={HARD_MIN_EV_R}")
        if stats["profit_factor"] < HARD_MIN_PF:
            reasons.append(f"PF {stats['profit_factor']}<{HARD_MIN_PF}")
        if stats["max_drawdown_r"] > HARD_MAX_DD_R:
            reasons.append(f"DD {stats['max_drawdown_r']}>{HARD_MAX_DD_R}")
        if stats["max_consecutive_losses"] > HARD_MAX_CONSECUTIVE_LOSSES:
            reasons.append(f"consec {stats['max_consecutive_losses']}>{HARD_MAX_CONSECUTIVE_LOSSES}")
        if stats["recent_30d_ev_r"] <= 0:
            reasons.append(f"recent EV {stats['recent_30d_ev_r']}<=0")
        return "; ".join(reasons) if reasons else "gates not met"
    if verdict == "WATCH":
        reasons = []
        if stats["trades"] < MIN_TRADES:
            reasons.append(f"trades {stats['trades']}<{MIN_TRADES}")
        if stats["ev_r"] <= MIN_EV_R:
            reasons.append(f"EV {stats['ev_r']}<={MIN_EV_R}")
        if stats["profit_factor"] < MIN_PF:
            reasons.append(f"PF {stats['profit_factor']}<{MIN_PF}")
        if stats["max_drawdown_r"] > MAX_DD_R:
            reasons.append(f"DD {stats['max_drawdown_r']}>{MAX_DD_R}")
        if stats["avg_rr"] < MIN_RR:
            reasons.append(f"RR {stats['avg_rr']}<{MIN_RR}")
        if not reasons:
            reasons.append("marginal gates")
        return "; ".join(reasons)
    return "unknown"


def _build_report(results: list[dict]) -> dict:
    passing = [r for r in results if r["verdict"] == "PASS"]
    watching = [r for r in results if r["verdict"] == "WATCH"]
    rejected = [r for r in results if r["verdict"] == "REJECT"]
    skipped = [r for r in results if r["verdict"] == "SKIP"]

    # Rank passing by EV descending
    passing.sort(key=lambda r: r["ev_r"], reverse=True)
    watching.sort(key=lambda r: r["ev_r"], reverse=True)

    top = passing[0] if passing else (watching[0] if watching else None)

    return {
        "mode": "strategy_tournament",
        "research_only": True,
        "live_trading_enabled": False,
        "paper_trading_enabled": False,
        "timestamp": datetime.now().isoformat(),
        "total_results": len(results),
        "passing": len(passing),
        "watching": len(watching),
        "rejected": len(rejected),
        "skipped": len(skipped),
        "top_strategy": {
            "config_label": top["config_label"],
            "display_name": top["display_name"],
            "strategy_id": top["strategy_id"],
            "ev_r": top["ev_r"],
            "pf": top["profit_factor"],
            "win_rate": top["win_rate"],
            "verdict": top["verdict"],
        } if top else None,
        "strategies": results,
    }


def _write_report(report: dict):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(JSON_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    lines = [
        "=" * 60,
        "  STRATEGY TOURNAMENT REPORT",
        f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Total results:   {report['total_results']}",
        f"  PASS:            {report['passing']}",
        f"  WATCH:           {report['watching']}",
        f"  REJECT:          {report['rejected']}",
        f"  SKIP:            {report['skipped']}",
        "",
    ]

    top = report["top_strategy"]
    if top:
        lines += [
            f"  TOP STRATEGY:    {top['display_name']} on {top['config_label']}",
            f"    EV:            {top['ev_r']}R",
            f"    PF:            {top['pf']}",
            f"    Win Rate:      {top['win_rate']:.1%}",
            f"    Verdict:       {top['verdict']}",
            "",
        ]
    else:
        lines += ["  TOP STRATEGY: NONE (no passing strategy)", ""]

    lines += ["  " + "-" * 88]
    lines.append(
        "  {:<22s} {:<22s} {:<6s} {:<6s} {:<6s} {:<6s} {:<5s} {:<8s}".format(
            "Config",
            "Strategy",
            "Trades",
            "WR",
            "EV(R)",
            "PF",
            "DD(R)",
            "Verdict",
        )
    )
    lines.append("  " + "-" * 88)
    for r in report["strategies"]:
        if r["verdict"] == "SKIP":
            wr_s = "N/A"
            ev_s = "N/A"
            pf_s = "N/A"
            dd_s = "N/A"
        else:
            wr_s = f"{r['win_rate']:.0%}" if r["trades"] > 0 else "N/A"
            ev_s = f"{r['ev_r']:.2f}" if r["trades"] > 0 else "N/A"
            pf_s = f"{r['profit_factor']:.2f}" if r["trades"] > 0 else "N/A"
            dd_s = f"{r['max_drawdown_r']:.1f}" if r["trades"] > 0 else "N/A"
        lines.append(
            "  {:<22s} {:<22s} {:<6s} {:<6s} {:<6s} {:<6s} {:<5s} {:<8s}".format(
                r["config_label"],
                r["display_name"][:22],
                str(r["trades"]),
                wr_s,
                ev_s,
                pf_s,
                dd_s,
                r["verdict"],
            )
        )
    lines.append("  " + "-" * 88)

    # Detail per strategy
    for r in report["strategies"]:
        if r["verdict"] != "SKIP" and r["trades"] > 0:
            lines += [
                "",
                f"  {r['display_name']} on {r['config_label']}:",
                f"    Trades: {r['trades']}  WR: {r['win_rate']:.0%}  EV: {r['ev_r']:.2f}R  "
                f"PF: {r['profit_factor']:.2f}  DD: {r['max_drawdown_r']:.1f}R  "
                f"Cons: {r['max_consecutive_losses']}  AvgRR: {r['avg_rr']:.2f}  "
                f"30dEV: {r['recent_30d_ev_r']:.2f}R",
                f"    Verdict: {r['verdict']}" + (f"  ({r['reason']})" if r.get("reason") else ""),
            ]

    lines += [
        "",
        "=" * 60,
    ]

    with open(TXT_REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print(f"\n[JSON] {JSON_REPORT}")
    print(f"[TXT]  {TXT_REPORT}")


def main():
    results = run_tournament()
    report = _build_report(results)
    _write_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
