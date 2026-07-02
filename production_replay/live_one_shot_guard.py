"""One-shot live micro arming guard.

States:
  DISARMED  - default, no live execution
  ARMED_ONCE - allows exactly one live order attempt
  USED      - after any order attempt, blocks further execution
  BLOCKED   - manual override to block

Commands:
  python -m production_replay.live_one_shot_guard --arm
  python -m production_replay.live_one_shot_guard --status
  python -m production_replay.live_one_shot_guard --disarm

This module NEVER sets BINGX_EXECUTION_MODE or LIVE_TRADING_ACK.
"""

import json, os, sys

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
STATE_PATH = os.path.join(STATE_DIR, "live_one_shot_state.json")

DEFAULT_STATE = "DISARMED"
VALID_STATES = ("DISARMED", "ARMED_ONCE", "USED", "BLOCKED")


def _ensure_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def read_state() -> str:
    _ensure_dir()
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
            state = data.get("state", DEFAULT_STATE)
            return state if state in VALID_STATES else DEFAULT_STATE
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_STATE


def write_state(state: str):
    if state not in VALID_STATES:
        state = DEFAULT_STATE
    _ensure_dir()
    data = {"state": state}
    with open(STATE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def set_armed():
    write_state("ARMED_ONCE")


def set_used():
    write_state("USED")


def set_disarmed():
    write_state("DISARMED")


def set_blocked():
    write_state("BLOCKED")


def main():
    if "--arm" in sys.argv:
        set_armed()
        print("One-shot guard: ARMED_ONCE")
    elif "--status" in sys.argv:
        print(f"One-shot guard state: {read_state()}")
    elif "--disarm" in sys.argv:
        set_disarmed()
        print("One-shot guard: DISARMED")
    else:
        print(f"One-shot guard state: {read_state()}")
        print("Usage: python -m production_replay.live_one_shot_guard [--arm|--disarm|--status]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
