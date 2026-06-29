"""Robust locked config loader for doctor-mode display only.

Parses config_locked.yaml with multiple schema support.
Never enables live or paper trading — display-only fallback.

Usage:
    from production_replay.locked_config_loader import load_allowed_configs
    configs, source, error = load_allowed_configs()
"""

import json, os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config_locked.yaml")


def _try_yaml(path: str) -> dict | None:
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _try_json(path: str) -> dict | None:
    """Fallback: try loading as JSON (some YAML is valid JSON)."""
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def _manual_parse(path: str) -> dict:
    """Simple key-value parser that collects list-of-dict structures."""
    result = {}
    stripped_lines = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            s = raw.rstrip("\n\r")
            stripped = s.strip()
            if not stripped or stripped.startswith("#"):
                stripped_lines.append("")
                continue
            stripped_lines.append(stripped)

    # Phase 1: collect all top-level keys with their raw values
    i = 0
    in_list_block = None
    list_accum = []
    while i < len(stripped_lines):
        line = stripped_lines[i]
        if not line:
            i += 1
            continue
        if line.startswith("- "):
            i += 1
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if not val:
                # Possible list block starting
                in_list_block = key
                # Collect following lines
                items = []
                j = i + 1
                while j < len(stripped_lines):
                    sub = stripped_lines[j]
                    if not sub:
                        j += 1
                        continue
                    if sub.startswith("- "):
                        # Parse inline: "- symbol: BTCUSDT" or multi-line
                        if ":" in sub[2:]:
                            parts = sub[2:].split(", ")
                            item = {}
                            for p in parts:
                                if ":" in p:
                                    k, _, v = p.partition(":")
                                    item[k.strip()] = v.strip()
                            items.append(item)
                        j += 1
                    elif sub.startswith("  ") or sub.startswith("\t"):
                        # continuation lines of a list item
                        if items:
                            if ":" in sub.strip():
                                k, _, v = sub.strip().partition(":")
                                items[-1][k.strip()] = v.strip()
                        j += 1
                    elif ":" in sub and not sub.startswith(" "):
                        break
                    else:
                        j += 1
                i = j
                if items:
                    result[key] = items
                continue
            else:
                # Simple key: value
                if val.lower() == "true":
                    result[key] = True
                elif val.lower() == "false":
                    result[key] = False
                else:
                    try:
                        result[key] = int(val)
                    except ValueError:
                        try:
                            result[key] = float(val)
                        except ValueError:
                            result[key] = val
                i += 1
        else:
            i += 1
    return result


def _extract_pairs(data: dict) -> list[tuple[str, str]]:
    """Extract (symbol, timeframe) pairs from any supported schema."""
    pairs = []

    # Try all possible key names for allowed configs
    possible_keys = [
        "allowed_configs",
        "allowed_symbol_timeframes",
        "allowed_pairs",
        "allowed",
        "configs",
    ]

    raw = None
    for k in possible_keys:
        v = data.get(k)
        if v is not None:
            raw = v
            break

    if raw is None:
        return []

    # List of dicts: [{"symbol": "BTCUSDT", "timeframe": "15m"}, ...]
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                sym = item.get("symbol") or item.get("Symbol") or item.get("pair") or item.get("Pair") or ""
                tf = item.get("timeframe") or item.get("Timeframe") or item.get("tf") or item.get("interval") or ""
                if sym and tf:
                    pairs.append((str(sym).strip(), str(tf).strip()))
            elif isinstance(item, str):
                parts = item.strip().split()
                if len(parts) >= 2:
                    pairs.append((parts[0], parts[1]))
                elif len(parts) == 1 and " " in item:
                    # tab or other whitespace
                    parts = item.split(None, 1)
                    if len(parts) >= 2:
                        pairs.append((parts[0], parts[1]))

    return pairs


def load_allowed_configs() -> tuple[list[tuple[str, str]], str, str | None]:
    """Load allowed configs from config_locked.yaml.

    Returns:
        (configs, source, error)
        configs: list of (symbol, timeframe) tuples
        source: "config_locked.yaml", "safe_display_fallback", or "error"
        error: None or error message string
    """
    if not os.path.exists(CONFIG_PATH):
        return _fallback("config file not found")

    # Try yaml
    data = _try_yaml(CONFIG_PATH)
    if data is None:
        data = _try_json(CONFIG_PATH)
    if data is None:
        data = _manual_parse(CONFIG_PATH)

    if not isinstance(data, dict):
        return _fallback(f"config parsing gave {type(data).__name__}, expected dict")

    # Check locked state
    live = data.get("live_trading", data.get("live", False))
    paper = data.get("paper_trading", data.get("paper", False))
    if live or paper:
        return _fallback("live or paper trading is enabled in config — unsafe")

    pairs = _extract_pairs(data)
    if pairs:
        return pairs, "config_locked.yaml", None

    # Try nested structures: symbol / timeframe inside each list item
    # Already handled by _extract_pairs

    # If we got here, allowed_configs are missing or malformed
    return _fallback("allowed_configs missing or malformed in config_locked.yaml")


def _fallback(reason: str) -> tuple[list[tuple[str, str]], str, str]:
    """Display-only fallback: always includes BTCUSDT 15m and BTCUSDT 30m.

    This fallback NEVER enables trading — it is only for doctor-mode display.
    """
    fallback = [
        ("BTCUSDT", "15m"),
        ("BTCUSDT", "30m"),
    ]
    return fallback, "safe_display_fallback", reason
