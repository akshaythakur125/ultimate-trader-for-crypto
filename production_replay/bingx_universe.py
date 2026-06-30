"""BingX tradable universe — USDT perpetual futures only.

Fetches available swap contracts from BingX API.
Falls back to a known curated list if API is unreachable.

Usage:
    from production_replay.bingx_universe import load_universe, is_bingx_listed
"""

import os, sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from production_replay.bingx_client import load_credentials

KNOWN_MEMECOINS = {
    "DOGE-USDT", "SHIB-USDT", "PEPE-USDT", "BONK-USDT", "WIF-USDT",
    "FLOKI-USDT", "MEME-USDT", "TURBO-USDT", "PEOPLE-USDT", "1000PEPE-USDT",
    "1000BONK-USDT", "ORDI-USDT", "SATS-USDT", "RATS-USDT",
}

KNOWN_MAJORS = {"BTC-USDT", "ETH-USDT", "SOL-USDT"}

FALLBACK_UNIVERSE: list[dict[str, Any]] = [
    {"symbol": s, "base": s.split("-")[0], "quote": "USDT", "contract_type": "perpetual"}
    for s in sorted(KNOWN_MEMECOINS | KNOWN_MAJORS)
]


def _parse_contracts(raw: list[dict]) -> list[dict[str, Any]]:
    result = []
    for c in raw:
        sym = c.get("symbol", "")
        if sym.endswith("-USDT"):
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


def load_universe() -> dict[str, Any]:
    """Load BingX swap universe. Returns dict with success, contracts, source, error."""
    creds = load_credentials()
    base_url = creds["base_url"]
    try:
        import requests
        resp = requests.get(f"{base_url}/openApi/swap/v2/quote/contracts", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0:
            raw = data.get("data", [])
            contracts = _parse_contracts(raw)
            return {"success": True, "contracts": contracts, "source": "api", "error": None}
    except Exception as e:
        pass
    return {"success": False, "contracts": FALLBACK_UNIVERSE, "source": "fallback",
            "error": "API unreachable, using fallback list"}


def is_bingx_listed(symbol: str, universe: list[dict] | None = None) -> bool:
    if universe is None:
        result = load_universe()
        universe = result["contracts"]
    return any(c["symbol"] == symbol for c in universe)


def get_memecoin_symbols(universe: list[dict]) -> list[str]:
    """Return symbols matching known memecoin names from the BingX universe."""
    available = {c["symbol"] for c in universe}
    return sorted(available & KNOWN_MEMECOINS)


def get_major_symbols(universe: list[dict]) -> list[str]:
    available = {c["symbol"] for c in universe}
    return sorted(available & KNOWN_MAJORS)
