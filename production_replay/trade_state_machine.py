"""Trade state machine — governs the lifecycle of a single trade.

States:
  IDLE -> SIGNAL_FOUND -> SHADOW_READY -> LIVE_ARMED -> ENTRY_SENT
  -> ENTRY_FILLED -> PROTECTION_PENDING -> PROTECTED -> MONITORING
  -> (PARTIAL_TAKEN | BREAKEVEN_MOVED) -> MONITORING
  -> EXITED_TARGET | EXITED_STOP | EXITED_MANUAL | EMERGENCY_EXIT
  -> IDLE

  Any state -> ERROR_LOCKED (recovery required)

Usage:
    from production_replay.trade_state_machine import TradeStateMachine
"""

import json, os
from datetime import datetime

STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "runtime_state")
STATE_FILE = os.path.join(STATE_DIR, "trade_state.json")

STATES = [
    "IDLE",
    "SIGNAL_FOUND",
    "SHADOW_READY",
    "LIVE_ARMED",
    "ENTRY_SENT",
    "ENTRY_FILLED",
    "PROTECTION_PENDING",
    "PROTECTED",
    "MONITORING",
    "PARTIAL_TAKEN",
    "BREAKEVEN_MOVED",
    "EXITED_TARGET",
    "EXITED_STOP",
    "EXITED_MANUAL",
    "EMERGENCY_EXIT",
    "ERROR_LOCKED",
]

ALLOWED_TRANSITIONS = {
    "IDLE": ["SIGNAL_FOUND", "ERROR_LOCKED"],
    "SIGNAL_FOUND": ["SHADOW_READY", "ERROR_LOCKED", "IDLE"],
    "SHADOW_READY": ["LIVE_ARMED", "ERROR_LOCKED", "IDLE"],
    "LIVE_ARMED": ["ENTRY_SENT", "ERROR_LOCKED", "IDLE"],
    "ENTRY_SENT": ["ENTRY_FILLED", "EXITED_MANUAL", "EMERGENCY_EXIT", "ERROR_LOCKED", "IDLE"],
    "ENTRY_FILLED": ["PROTECTION_PENDING", "EMERGENCY_EXIT", "ERROR_LOCKED"],
    "PROTECTION_PENDING": ["PROTECTED", "EMERGENCY_EXIT", "ERROR_LOCKED"],
    "PROTECTED": ["MONITORING", "EMERGENCY_EXIT", "ERROR_LOCKED"],
    "MONITORING": ["PARTIAL_TAKEN", "BREAKEVEN_MOVED", "EXITED_TARGET", "EXITED_STOP",
                    "EXITED_MANUAL", "EMERGENCY_EXIT", "ERROR_LOCKED"],
    "PARTIAL_TAKEN": ["MONITORING", "EXITED_TARGET", "EXITED_STOP", "EXITED_MANUAL",
                       "EMERGENCY_EXIT", "ERROR_LOCKED"],
    "BREAKEVEN_MOVED": ["MONITORING", "EXITED_TARGET", "EXITED_STOP", "EXITED_MANUAL",
                         "EMERGENCY_EXIT", "ERROR_LOCKED"],
    "EXITED_TARGET": ["IDLE", "ERROR_LOCKED"],
    "EXITED_STOP": ["IDLE", "ERROR_LOCKED"],
    "EXITED_MANUAL": ["IDLE", "ERROR_LOCKED"],
    "EMERGENCY_EXIT": ["IDLE", "ERROR_LOCKED"],
    "ERROR_LOCKED": ["IDLE"],
}

TERMINAL_STATES = {"EXITED_TARGET", "EXITED_STOP", "EXITED_MANUAL", "EMERGENCY_EXIT"}
ACTIVE_TRADING_STATES = {"ENTRY_SENT", "ENTRY_FILLED", "PROTECTION_PENDING", "PROTECTED",
                          "MONITORING", "PARTIAL_TAKEN", "BREAKEVEN_MOVED"}


class TradeStateMachine:
    def __init__(self, state: str = "IDLE"):
        self.state = state

    def can_transition(self, new_state: str) -> bool:
        return new_state in ALLOWED_TRANSITIONS.get(self.state, [])

    def transition(self, new_state: str, reason: str = "") -> bool:
        if not self.can_transition(new_state):
            return False
        self.state = new_state
        self._persist(reason)
        return True

    def is_active(self) -> bool:
        return self.state in ACTIVE_TRADING_STATES

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def is_locked(self) -> bool:
        return self.state == "ERROR_LOCKED"

    def can_open_new_trade(self) -> bool:
        return self.state == "IDLE" or self.is_terminal()

    def _persist(self, reason: str = ""):
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "state": self.state,
                "timestamp": datetime.now().isoformat(),
                "reason": reason,
            }, f, indent=2)

    @classmethod
    def load(cls) -> "TradeStateMachine":
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            return cls(data.get("state", "IDLE"))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls("IDLE")

    def __repr__(self) -> str:
        return f"TradeStateMachine(state={self.state})"
