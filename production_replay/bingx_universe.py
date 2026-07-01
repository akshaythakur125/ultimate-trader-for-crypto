"""BingX tradable universe — expanded to 100+ ranked symbols.

Fetches all active BingX USDT perpetual contracts from API.
Ranks by 24h quote volume for the Dux scan universe.
Outputs deploy_results/bingx_universe.json and .txt.

Usage:
    python -m production_replay.bingx_universe
"""

import json, os, sys, time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import load_credentials, get_all_swap_tickers

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "deploy_results")
JSON_PATH = os.path.join(RESULTS_DIR, "bingx_universe.json")
TXT_PATH = os.path.join(RESULTS_DIR, "bingx_universe.txt")

SCAN_UNIVERSE_TARGET = 200
KNOWN_MEMECOINS = {
    "DOGE-USDT", "SHIB-USDT", "PEPE-USDT", "BONK-USDT", "WIF-USDT",
    "FLOKI-USDT", "MEME-USDT", "TURBO-USDT", "PEOPLE-USDT", "1000PEPE-USDT",
    "1000BONK-USDT", "ORDI-USDT", "SATS-USDT", "RATS-USDT",
}
KNOWN_MAJORS = {"BTC-USDT", "ETH-USDT", "SOL-USDT"}

# Non-crypto / synthetic symbol filters
KNOWN_NON_CRYPTO_PREFIXES = {
    "NCSK", "NCCO", "NCSI", "NCFX",
    "SOXL", "TSLA", "TSL", "NVDA", "NBIS",
    "AMD", "DRAM", "AAPL", "META", "MSFT", "GOOGL", "AMZN", "MSTR",
    "COIN", "MARA", "EUR", "GBP", "JPY", "XAU", "XAG", "XPT", "XPD",
}
KNOWN_NON_CRYPTO_SYMBOLS = {
    "SOXL-USDT", "TSLA-USDT", "TSL-USDT", "NVDA-USDT", "NBIS-USDT",
    "AMD-USDT", "DRAM-USDT", "AAPL-USDT", "META-USDT", "MSFT-USDT",
    "GOOGL-USDT", "AMZN-USDT", "MSTR-USDT", "COIN-USDT", "MARA-USDT",
    "EURUSDT", "GBPUSDT", "JPYUSDT", "XAUUSDT", "XAGUSDT",
}

KNOWN_STOCK_PATTERNS = [
    "NCSK", "NCCO", "NCSI", "SOXL", "TSLA", "TSL", "NVDA", "NBIS",
    "AMD", "DRAM", "AAPL", "META", "MSFT", "GOOGL", "AMZN", "MSTR",
    "COIN", "MARA", "EUR", "GBP", "JPY", "XAU", "XAG",
]


def _is_crypto_symbol(symbol: str) -> bool:
    """Check if a symbol is a real crypto USDT perpetual (not stock/forex/commodity synthetic)."""
    base = symbol.replace("-USDT", "").replace("USDT", "")
    # Check exact non-crypto list
    if symbol in KNOWN_NON_CRYPTO_SYMBOLS:
        return False
    # Check prefixes that are known non-crypto
    for prefix in KNOWN_NON_CRYPTO_PREFIXES:
        if base.startswith(prefix):
            # Skip BTC prefix check — it's valid crypto
            if prefix == "BTC":
                continue
            return False
    # Check stock patterns
    for pat in KNOWN_STOCK_PATTERNS:
        if base.startswith(pat):
            return False
    return True


def _filter_crypto_only(contracts: list[dict]) -> tuple[list[dict], int]:
    """Filter contracts to crypto-only USDT perpetuals. Returns (filtered, excluded_count)."""
    crypto = []
    excluded = 0
    for c in contracts:
        sym = c.get("symbol", "")
        if _is_crypto_symbol(sym):
            crypto.append(c)
        else:
            excluded += 1
    return crypto, excluded

FALLBACK_UNIVERSE: list[dict[str, Any]] = [
    {"symbol": s, "base": s.split("-")[0], "quote": "USDT", "contract_type": "perpetual"}
    for s in sorted(KNOWN_MEMECOINS | KNOWN_MAJORS)
]


def _parse_contracts(raw: list[dict]) -> list[dict[str, Any]]:
    result = []
    for c in raw:
        sym = c.get("symbol", "")
        currency = c.get("currency", "")
        status = c.get("status", 0)
        if sym.endswith("-USDT") and currency == "USDT" and status == 1:
            result.append({
                "symbol": sym,
                "base": sym.split("-")[0],
                "quote": "USDT",
                "contract_type": "perpetual",
                "contract_id": str(c.get("contractId", "")),
                "min_qty": float(c.get("tradeMinLimit", 0)),
                "price_precision": int(c.get("pricePrecision", 2)),
                "qty_precision": int(c.get("quantityPrecision", 4)),
            })
    return result


def _rank_by_volume(contracts: list[dict]) -> list[dict]:
    """Attach volume data and rank descending by quoteVolume using batch ticker."""
    creds = load_credentials()
    base_url = creds["base_url"]
    try:
        ticker_result = get_all_swap_tickers(base_url)
        ticker_map = {}
        if ticker_result["success"]:
            raw = ticker_result.get("data", {})
            items = raw.get("data", raw) if isinstance(raw, dict) else raw
            if isinstance(items, list):
                for t in items:
                    sym = t.get("symbol", "")
                    vol = float(t.get("quoteVolume", t.get("volume", 0)))
                    change = abs(float(t.get("priceChangePercent", 0)))
                    ticker_map[sym] = {"quote_volume": vol, "price_change_pct": change}
    except Exception:
        pass

    ranked = []
    for c in contracts:
        t = ticker_map.get(c["symbol"], {"quote_volume": 0.0, "price_change_pct": 0.0})
        ranked.append({**c, **t})
    ranked.sort(key=lambda x: x.get("quote_volume", 0), reverse=True)
    return ranked


def load_universe() -> dict[str, Any]:
    """Load BingX swap universe, ranked by volume. Returns dict with success, contracts, source."""
    creds = load_credentials()
    base_url = creds["base_url"]
    try:
        import requests
        resp = requests.get(f"{base_url}/openApi/swap/v2/quote/contracts", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0:
            raw = data.get("data", [])
            parsed = _parse_contracts(raw)
            ranked = _rank_by_volume(parsed)
            return {"success": True, "contracts": ranked, "source": "api", "error": None,
                    "total_raw": len(raw), "active_usdt": len(parsed)}
    except Exception as e:
        pass
    return {"success": False, "contracts": FALLBACK_UNIVERSE, "source": "fallback",
            "error": "API unreachable, using fallback list",
            "total_raw": 0, "active_usdt": len(FALLBACK_UNIVERSE)}


def build_scan_universe(contracts: list[dict], crypto_only: bool = True) -> dict[str, Any]:
    """Build ranked scan universe of at least SCAN_UNIVERSE_TARGET symbols."""
    if crypto_only:
        contracts, _ = _filter_crypto_only(contracts)
    memecoin_syms = sorted({c["symbol"] for c in contracts if c["symbol"] in KNOWN_MEMECOINS})
    major_syms = sorted({c["symbol"] for c in contracts if c["symbol"] in KNOWN_MAJORS})
    priority = set(memecoin_syms + major_syms)

    scan = []
    seen = set()

    # First pass: memecoins + majors
    for c in contracts:
        if c["symbol"] in priority and c["symbol"] not in seen:
            scan.append(c)
            seen.add(c["symbol"])
        if len(scan) >= SCAN_UNIVERSE_TARGET:
            break

    # Second pass: top volume fill
    if len(scan) < SCAN_UNIVERSE_TARGET:
        for c in contracts:
            if c["symbol"] not in seen:
                scan.append(c)
                seen.add(c["symbol"])
            if len(scan) >= SCAN_UNIVERSE_TARGET:
                break

    return {
        "symbols": [c["symbol"] for c in scan],
        "contracts": scan,
        "size": len(scan),
        "memecoins": memecoin_syms,
        "majors": major_syms,
        "target": SCAN_UNIVERSE_TARGET,
    }


def build_adaptive_universe(contracts: list[dict], crypto_only: bool = True) -> dict[str, Any]:
    """Build adaptive 3-tier scan universe from ranked contracts.
    
    Tier A:  Top 200 by volume      → 5m, 15m, 30m, 1h
    Tier B:  Next 200 by volume     → 15m, 30m, 1h
    Tier C:  Remaining valid perps  → 30m, 1h only
    
    Returns dict with tier breakdown, timeframes, and symbol list.
    Minimum target: 400 symbols. Falls back gracefully if fewer contracts exist.
    """
    if crypto_only:
        contracts, excluded_count = _filter_crypto_only(contracts)
    else:
        excluded_count = 0
    memecoin_syms = sorted({c["symbol"] for c in contracts if c["symbol"] in KNOWN_MEMECOINS})
    major_syms = sorted({c["symbol"] for c in contracts if c["symbol"] in KNOWN_MAJORS})
    priority = set(memecoin_syms + major_syms)

    # Rank is already sorted desc by volume from _rank_by_volume
    tier_a_raw = []
    tier_b_raw = []
    tier_c_raw = []
    seen = set()

    # First pass: memecoins + majors go to tier A (up to 200)
    for c in contracts:
        if c["symbol"] in priority and c["symbol"] not in seen:
            tier_a_raw.append(c)
            seen.add(c["symbol"])
        if len(tier_a_raw) >= 200:
            break

    # Fill tier A to 200 with top volume
    if len(tier_a_raw) < 200:
        for c in contracts:
            if c["symbol"] not in seen:
                tier_a_raw.append(c)
                seen.add(c["symbol"])
            if len(tier_a_raw) >= 200:
                break

    # Tier B: next 200 by volume
    for c in contracts:
        if c["symbol"] not in seen:
            tier_b_raw.append(c)
            seen.add(c["symbol"])
        if len(tier_b_raw) >= 200:
            break

    # Tier C: all remaining
    for c in contracts:
        if c["symbol"] not in seen:
            tier_c_raw.append(c)
            seen.add(c["symbol"])

    all_symbols = [c["symbol"] for c in tier_a_raw + tier_b_raw + tier_c_raw]
    all_contracts = tier_a_raw + tier_b_raw + tier_c_raw

    return {
        "symbols": all_symbols,
        "contracts": all_contracts,
        "size": len(all_symbols),
        "memecoins": memecoin_syms,
        "majors": major_syms,
        "target": 400,
        "excluded_non_crypto": excluded_count,
        "tier_a": {
            "symbols": [c["symbol"] for c in tier_a_raw],
            "size": len(tier_a_raw),
            "timeframes": ["5m", "15m", "30m", "1h"],
        },
        "tier_b": {
            "symbols": [c["symbol"] for c in tier_b_raw],
            "size": len(tier_b_raw),
            "timeframes": ["15m", "30m", "1h"],
        },
        "tier_c": {
            "symbols": [c["symbol"] for c in tier_c_raw],
            "size": len(tier_c_raw),
            "timeframes": ["30m", "1h"],
        },
    }


def is_bingx_listed(symbol: str, universe: list[dict] | None = None) -> bool:
    if universe is None:
        result = load_universe()
        universe = result["contracts"]
    return any(c["symbol"] == symbol for c in universe)


def get_memecoin_symbols(universe: list[dict]) -> list[str]:
    available = {c["symbol"] for c in universe}
    return sorted(available & KNOWN_MEMECOINS)


def get_major_symbols(universe: list[dict]) -> list[str]:
    available = {c["symbol"] for c in universe}
    return sorted(available & KNOWN_MAJORS)


def write_reports(universe_result: dict, scan: dict, adaptive: dict | None = None):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    tier_a = adaptive.get("tier_a", {}) if adaptive else {}
    tier_b = adaptive.get("tier_b", {}) if adaptive else {}
    tier_c = adaptive.get("tier_c", {}) if adaptive else {}

    excluded_count = adaptive.get("excluded_non_crypto", 0) if adaptive else 0
    json_report = {
        "mode": "bingx_universe",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "source": universe_result["source"],
        "total_raw_contracts": universe_result.get("total_raw", 0),
        "active_usdt_perps": universe_result.get("active_usdt", 0),
        "excluded_non_crypto": excluded_count,
        "scan_universe_size": scan["size"],
        "scan_universe_target": scan["target"],
        "memecoin_count": len(scan["memecoins"]),
        "major_count": len(scan["majors"]),
        "scan_symbols": scan["symbols"],
        "memecoin_symbols": scan["memecoins"],
        "major_symbols": scan["majors"],
        "adaptive_mode": adaptive is not None,
        "tier_a_size": tier_a.get("size", 0),
        "tier_b_size": tier_b.get("size", 0),
        "tier_c_size": tier_c.get("size", 0),
        "tier_a_timeframes": tier_a.get("timeframes", []),
        "tier_b_timeframes": tier_b.get("timeframes", []),
        "tier_c_timeframes": tier_c.get("timeframes", []),
    }
    with open(JSON_PATH, "w") as f:
        json.dump(json_report, f, indent=2)

    excluded_count = adaptive.get("excluded_non_crypto", 0) if adaptive else 0
    lines = [
        "=" * 60,
        "  BINGX TRADABLE UNIVERSE",
        f"  {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
        f"  Source:                  {universe_result['source']}",
        f"  Total raw contracts:     {universe_result.get('total_raw', 0)}",
        f"  Active USDT perps:       {universe_result.get('active_usdt', 0)}",
        f"  Excluded non-crypto:     {excluded_count}",
        f"  Crypto USDT perps:       {universe_result.get('active_usdt', 0) - excluded_count}",
        f"  Scan target:             {scan['target']}+",
        f"  Scan universe:           {scan['size']}",
        f"  Memecoin candidates:     {len(scan['memecoins'])}",
        f"  Major controls:          {len(scan['majors'])}",
        "",
    ]
    if adaptive:
        total_st = (tier_a.get("size", 0) * len(tier_a.get("timeframes", [])) +
                     tier_b.get("size", 0) * len(tier_b.get("timeframes", [])) +
                     tier_c.get("size", 0) * len(tier_c.get("timeframes", [])))
        lines += [
            "  ADAPTIVE 3-TIER UNIVERSE:",
            f"    Tier A (5m/15m/30m/1h): {tier_a.get('size', 0)} symbols",
            f"    Tier B (15m/30m/1h):    {tier_b.get('size', 0)} symbols",
            f"    Tier C (30m/1h):         {tier_c.get('size', 0)} symbols",
            f"    Total symbol-TFs:       {total_st}",
            "",
        ]
    lines += ["  Top 20 by volume:"]
    for i, s in enumerate(scan["symbols"][:20]):
        lines.append(f"    {i + 1:>3}. {s}")
    lines += [
        "",
        "=" * 60,
    ]

    with open(TXT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n[JSON] {JSON_PATH}")
    print(f"[TXT]  {TXT_PATH}")


def main():
    result = load_universe()
    if result["source"] == "fallback":
        print(f"  WARNING: {result.get('error', '')}")
    contracts = result["contracts"]
    scan = build_scan_universe(contracts)
    adaptive = build_adaptive_universe(contracts)
    write_reports(result, scan, adaptive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
